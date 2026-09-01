"""
Rich TUI dashboard. Live status of queue depth, RPS, fail ratio, current
exit fingerprint. No external state — fed by the orchestrator.
"""

from __future__ import annotations

import time
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Deque, Optional

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table


@dataclass
class Dashboard:
    console: Console = field(default_factory=Console)
    started_at: float = field(default_factory=time.time)
    probes_total: int = 0
    probes_alive: int = 0
    probes_dead: int = 0
    queue_depth: int = 0
    newnyms_sent: int = 0
    rt_window: Deque[float] = field(default_factory=lambda: deque(maxlen=200))
    last_exit_fpr: str = "(unknown)"

    def tick(self, *, alive: bool, response_time_ms: float) -> None:
        self.probes_total += 1
        if alive:
            self.probes_alive += 1
        else:
            self.probes_dead += 1
        self.rt_window.append(response_time_ms)

    def render(self) -> Table:
        elapsed = time.time() - self.started_at
        rps = (self.probes_total / elapsed) if elapsed > 0 else 0.0
        avg_rt = (sum(self.rt_window) / len(self.rt_window)) if self.rt_window else 0.0
        fail_ratio = (
            (self.probes_dead / self.probes_total) if self.probes_total else 0.0
        )
        t = Table.grid(padding=(0, 1))
        t.add_column(style="bold")
        t.add_column()
        t.add_row("elapsed", f"{elapsed:6.1f}s")
        t.add_row("queue", f"{self.queue_depth}")
        t.add_row("probes", f"{self.probes_total}  (alive={self.probes_alive}, dead={self.probes_dead})")
        t.add_row("rps", f"{rps:5.2f}")
        t.add_row("avg rt", f"{avg_rt:6.1f} ms")
        t.add_row("fail", f"{fail_ratio:6.2%}")
        t.add_row("newnyms", f"{self.newnyms_sent}")
        t.add_row("exit fpr", f"{self.last_exit_fpr}")
        return t

    @contextmanager
    def live(self):
        with Live(Panel(self.render(), title="TORCrawl"), refresh_per_second=4) as live:
            yield live
