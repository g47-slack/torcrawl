"""
Tor control — stem wrapper.

v1 used the cookie file directly which is mode-600 owned by the
`debian-tor` system user; only that user (or root) can read it. The
cleanest portable auth is **HashedControlPassword**, which stem accepts
as a regular string.

We also normalise the control handle so the rest of the codebase can
trust the password is correct at construction time. The handle exposes
a `ping()` that returns a structured status instead of bare exceptions.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from stem import Signal  # type: ignore
from stem.control import Controller  # type: ignore


@dataclass
class TorStatus:
    ok: bool
    version: Optional[str] = None
    error: Optional[str] = None
    circuit_established: Optional[bool] = None
    bootstrap_phase: Optional[str] = None


class TorController:
    def __init__(self, *, control_port: int = 9051, password: str = "") -> None:
        self.control_port = control_port
        self.password = password

    # -- low-level ---------------------------------------------------------

    def _open(self) -> Controller:
        return Controller.from_port(port=self.control_port)

    def _auth(self, c: Controller) -> None:
        if self.password:
            c.authenticate(password=self.password)
        else:
            # Default: read /var/lib/tor/control_auth_cookie (only works if
            # the running user can read it). This is the v1 path.
            c.authenticate()

    # -- public API --------------------------------------------------------

    def ping(self) -> TorStatus:
        """Best-effort liveness + bootstrap report. Never raises."""
        try:
            with self._open() as c:
                self._auth(c)
                version = c.get_version()
                ce = c.get_info("status/circuit-established")
                boot = c.get_info("status/bootstrap-phase")
                return TorStatus(
                    ok=True,
                    version=version,
                    circuit_established=(ce == "1"),
                    bootstrap_phase=boot,
                )
        except Exception as exc:
            return TorStatus(ok=False, error=f"{type(exc).__name__}: {exc}")

    def wait_for_circuit(self, *, timeout: int = 180, poll: float = 3.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                with self._open() as c:
                    self._auth(c)
                    if c.get_info("status/circuit-established") == "1":
                        return True
            except Exception:
                pass
            time.sleep(poll)
        return False

    def signal_newnym(self) -> bool:
        try:
            with self._open() as c:
                self._auth(c)
                c.signal(Signal.NEWNYM)
            return True
        except Exception:
            return False
