"""
Network layer.

Two entry points:

  * `build_session()` — async context manager that yields a configured
    aiohttp.ClientSession. Pass `proxy=None` for clearnet (no Tor);
    pass `proxy=(host, port)` to route through a SOCKS5 proxy.

  * `probe_onion()` — async function that attempts a HEAD then GET
    against `http://<onion>/` and returns (alive, response_ms).
"""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional, Tuple

import aiohttp
from aiohttp_socks import ProxyConnector, ProxyType


@asynccontextmanager
async def build_session(
    *,
    proxy: Optional[Tuple[str, int]] = None,
    user_agent: str,
    trust_env: bool = False,
) -> AsyncIterator[aiohttp.ClientSession]:
    """Build a configured aiohttp session.

    `proxy=None` -> direct clearnet.
    `proxy=(host, port)` -> SOCKS5 through the Tor daemon.
    """
    if proxy is not None:
        host, port = proxy
        connector = ProxyConnector(
            proxy_type=ProxyType.SOCKS5, host=host, port=port, rdns=True
        )
    else:
        connector = aiohttp.TCPConnector()

    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
                  "image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    async with aiohttp.ClientSession(
        connector=connector, headers=headers, trust_env=trust_env
    ) as session:
        yield session


async def probe_onion(
    session: aiohttp.ClientSession, onion: str, *, timeout: aiohttp.ClientTimeout
) -> Tuple[bool, float]:
    """Try HEAD then GET against http://<onion>/. Returns (alive, response_ms).

    We start with HEAD (cheap) and fall back to GET if the server
    doesn't support HEAD. The fetch body is discarded after a tiny read
    so we don't pay for the full page.
    """
    url = f"http://{onion}/"
    start = time.monotonic()
    try:
        async with session.head(url, timeout=timeout, ssl=False) as resp:
            if 200 <= resp.status < 400:
                return True, (time.monotonic() - start) * 1000.0
    except Exception:
        pass
    # fallback GET
    start = time.monotonic()
    try:
        async with session.get(
            url, timeout=timeout, ssl=False, allow_redirects=False
        ) as resp:
            await resp.content.read(512)
            return True, (time.monotonic() - start) * 1000.0
    except Exception:
        return False, 0.0
