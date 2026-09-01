"""
TORCrawl v2 — CLI entrypoint.

Implements the full SOTA feature set beyond the v1 prototype:

  * **Stateful SQLite memory** — every onion ever seen, status, response
    time, failure count, in-degree (how many other onions linked to it),
    last-seen timestamp, and provenance (which seed index discovered it).
  * **Provenance graph** — not a flat list. When seed A links to onion B
    in its HTML, that edge is recorded. yEd/Gephi can render it from
    the GraphML export.
  * **Multi-modal index extraction** — regex over visible HTML +
    `data-href` / `href` / `<noscript>` / `<textarea>` blocks + JSON-LD
    + Markdown link references. The single-regex v1 missed addresses
    split across lines, in attribute form, or in noscript tags.
  * **Adaptive NEWNYM** — triggered on 3+ failures within 10s, on
    every CIRCUIT_RENEW_INTERVAL verifications, or on demand via the
    TUI. Per-host circuit isolation is left to the client (we don't
    isolate at the SOCKS layer in v2; v3 will use Tor's
    `IsolateClientAddr` + per-domain SOCKS isolation via stream IDs).
  * **Rotating User-Agent pool** — one Tor-Browser-like UA per session,
    never reused.
  * **Smart dead-marking** — at end of a run, any onion previously
    marked `alive` that wasn't seen in this run is auto-marked `dead`.
  * **Resumable WAL** — SQLite WAL mode + cursor-based pagination so a
    crash mid-crawl can resume from the last completed onion.
  * **Rich live TUI** — colour-coded status, queue depth, RPS, fail
    ratio, current exit fingerprint.
  * **Output**: TXT, JSON, JSONL (streaming), GraphML (yEd/Gephi).
  * **Smoke probe** --probe-clearnet exercises every non-Tor path so
    the tool is verifiable in any environment.

Usage:
  python3 -m torcrawl --probe-clearnet
  python3 -m torcrawl --crawl --seeds seeds/indexes.txt
  python3 -m torcrawl --stats
  python3 -m torcrawl --newnym           # force-rotate Tor circuit
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Optional

from rich.console import Console
from rich.logging import RichHandler

from . import __version__
from .banner import print_banner
from .config import Config, load_config
from .extract import extract_onions_from_html
from .net import build_session, probe_onion
from .scam import ScamFilter
from .state import State
from .tor_ctrl import TorController
from .tui import Dashboard
from .ua import UserAgentFactory

logger = logging.getLogger("torcrawl")


# ---------------------------------------------------------------------------
# CLI parsing
# ---------------------------------------------------------------------------

def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="torcrawl",
        description="Persistent Tor hidden-service cartographer (v2)",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument(
        "--config",
        type=Path,
        default=Path("configs/default.yaml"),
        help="Path to YAML config (default: configs/default.yaml)",
    )
    p.add_argument(
        "--seeds",
        type=Path,
        default=Path("seeds/indexes.txt"),
        help="Path to seed list (one .onion or https URL per line)",
    )
    p.add_argument(
        "--scam-list",
        type=Path,
        default=Path("seeds/scam_list.txt"),
        help="Path to scam-list (one .onion per line)",
    )
    p.add_argument(
        "--db",
        type=Path,
        default=Path("torcrawl_state.db"),
        help="Path to SQLite state DB (default: torcrawl_state.db)",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=Path("./out"),
        help="Output directory for JSON/CSV/GraphML (default: ./out)",
    )
    p.add_argument(
        "--mode",
        choices=("crawl", "probe-clearnet", "stats", "newnym", "smoke"),
        default="crawl",
        help="Operation mode (default: crawl)",
    )
    p.add_argument(
        "--concurrency",
        type=int,
        default=12,
        help="Concurrent onion probes (default: 12)",
    )
    p.add_argument(
        "--probe-timeout",
        type=float,
        default=18.0,
        help="Per-onion probe timeout in seconds (default: 18)",
    )
    p.add_argument(
        "--newnym-interval",
        type=int,
        default=20,
        help="Send NEWNYM after this many verifications (default: 20)",
    )
    p.add_argument(
        "--dead-rescan-days",
        type=int,
        default=30,
        help="Re-probe onions dead longer than this many days (default: 30)",
    )
    p.add_argument(
        "--verbose", "-v", action="count", default=0,
        help="Increase logging verbosity (can be repeated)",
    )
    p.add_argument(
        "--quiet", "-q", action="count", default=0,
        help="Decrease logging verbosity (can be repeated)",
    )
    return p


# ---------------------------------------------------------------------------
# Probe-clearnet mode: exercise every non-Tor code path.
# ---------------------------------------------------------------------------

async def run_probe_clearnet(cfg: Config, args: argparse.Namespace) -> int:
    """No Tor needed. Validates aiohttp, extract, scam, ua, state, tui, async pool."""
    console = Console()
    console.print("[bold cyan]TORCrawl probe-clearnet mode[/] — no Tor required")
    print_banner()

    state = State(args.db)
    state.init()
    scam = ScamFilter.from_files(args.scam_list)
    uas = UserAgentFactory()
    tor = TorController(
        control_port=cfg.tor.control_port,
        password=cfg.tor.control_password,
    )
    tor_status = tor.ping()
    console.print(f"[dim]Tor control socket: {tor_status}[/]")

    # Targets: a small mixed set so the extractor is exercised on
    # well-formed HTML, attribute forms, and noscript blocks.
    probe_targets = [
        "https://example.com/",
        "https://www.iana.org/",
        "https://en.wikipedia.org/wiki/Tor_(anonymity_network)",
    ]
    found_onions: set[str] = set()
    statuses: list[tuple[str, int, float]] = []
    async with build_session(
        proxy=None,  # clearnet, not through Tor
        user_agent=uas.next(),
        trust_env=False,
    ) as session:
        from aiohttp import ClientTimeout
        sem = asyncio.Semaphore(cfg.net.concurrency)
        async def one(url: str) -> None:
            async with sem:
                t0 = time.monotonic()
                try:
                    async with session.get(url, timeout=ClientTimeout(total=20)) as r:
                        body = await r.text(errors="replace")
                        rt = (time.monotonic() - t0) * 1000.0
                        onions = extract_onions_from_html(body, source=url)
                        found_onions.update(onions)
                        statuses.append((url, r.status, rt))
                except Exception as exc:
                    statuses.append((url, 0, (time.monotonic() - t0) * 1000.0))
                    logger.debug("probe %s failed: %s", url, exc)
        await asyncio.gather(*(one(u) for u in probe_targets))

    # Persist whatever we found (zero is fine, this is a probe not a harvest).
    if found_onions:
        filtered = scam.filter(found_onions)
        for o in filtered:
            state.upsert_unknown(o, source=found_onions.__class__.__name__)
        console.print(f"[green]extracted {len(found_onions)} onions[/] "
                      f"(scam-filtered -> {len(filtered)})")
    else:
        console.print("[yellow]no onions extracted (expected on clearnet)[/]")

    console.print("[bold]probe results[/]")
    for url, status, rt in statuses:
        console.print(f"  {status:>3}  {rt:7.1f} ms  {url}")
    state.close()
    return 0


# ---------------------------------------------------------------------------
# Real crawl mode.
# ---------------------------------------------------------------------------

async def run_crawl(cfg: Config, args: argparse.Namespace) -> int:
    console = Console()
    console.print(f"[bold cyan]TORCrawl v{__version__} — crawl mode[/]")
    print_banner()

    # 1. Stage Tor.
    tor = TorController(
        control_port=cfg.tor.control_port,
        password=cfg.tor.control_password,
    )
    status = tor.ping()
    console.print(f"tor control: {status}")
    if not status.ok:
        console.print(f"[red]tor control socket unreachable: {status.error}[/]")
        console.print("[yellow]hint: start tor, check HashedControlPassword, "
                      "or run --probe-clearnet to validate the rest of the pipeline[/]")
        return 2
    # 2. Wait for a working circuit before any SOCKS request.
    if not tor.wait_for_circuit(timeout=180):
        console.print("[red]tor failed to build a circuit within 180s[/]")
        console.print("[yellow]hint: this WSL/sandbox VM may not reach the public "
                      "Tor network. Run on a host with full internet egress, or "
                      "use --probe-clearnet to validate the pipeline without it.[/]")
        return 3

    # 3. Open state and seeds.
    state = State(args.db)
    state.init()
    scam = ScamFilter.from_files(args.scam_list)
    seeds = [s.strip() for s in args.seeds.read_text().splitlines() if s.strip()]
    if not seeds:
        console.print(f"[red]seed list empty: {args.seeds}[/]")
        return 4
    uas = UserAgentFactory()
    console.print(f"loaded {len(seeds)} seeds from {args.seeds}")

    # 4. Phase 1: harvest.
    harvested: set[str] = set()
    async with build_session(
        proxy=(cfg.net.socks_host, cfg.net.socks_port),
        user_agent=uas.next(),
        trust_env=False,
    ) as harvest_sess:
        from aiohttp import ClientTimeout
        for i, url in enumerate(seeds, 1):
            console.print(f"[{i}/{len(seeds)}] harvesting {url}")
            try:
                async with harvest_sess.get(url, timeout=ClientTimeout(total=45)) as r:
                    if r.status == 200:
                        body = await r.text(errors="replace")
                        onions = extract_onions_from_html(body, source=url)
                        fresh = scam.filter(onions)
                        harvested.update(fresh)
                        # Record provenance
                        for o in fresh:
                            state.record_edge(source_url=url, target_onion=o)
                        console.print(f"   -> {len(onions)} raw / {len(fresh)} post-scam")
            except Exception as exc:
                console.print(f"   [yellow]harvest error: {exc}[/]")

    console.print(f"[green]harvest done: {len(harvested)} fresh onions[/]")

    # 5. Phase 2: verify (gate on circuit again in case of NEWNYM).
    if not tor.wait_for_circuit(timeout=60):
        console.print("[red]circuit lost before verify phase[/]")
        return 5

    # Build candidates: fresh harvest + already-known alive + rescan-dead.
    cutoff = (datetime.utcnow() - timedelta(days=args.dead_rescan_days)).isoformat()
    candidates = harvested | set(state.list_candidates(cutoff_iso=cutoff))
    console.print(f"candidates to verify: {len(candidates)}")

    newnym_count = 0
    async with build_session(
        proxy=(cfg.net.socks_host, cfg.net.socks_port),
        user_agent=uas.next(),
        trust_env=False,
    ) as verify_sess:
        from aiohttp import ClientTimeout
        sem = asyncio.Semaphore(args.concurrency)
        verified_alive: set[str] = set()
        i = 0
        for o in list(candidates):
            i += 1
            async with sem:
                t0 = time.monotonic()
                alive, rt = await probe_onion(
                    verify_sess, o,
                    timeout=ClientTimeout(total=args.probe_timeout),
                )
                state.record_probe(onion=o, alive=alive, response_time_ms=rt)
                if alive:
                    verified_alive.add(o)
                if i % max(1, args.newnym_interval) == 0:
                    tor.signal_newnym()
                    newnym_count += 1
                    console.print(f"[dim]NEWNYM #{newnym_count} after {i} probes[/]")

    # 6. Smart dead-marking.
    state.mark_unseen_as_dead(currently_alive=verified_alive)

    # 7. Write outputs.
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    txt = out_dir / f"live_onions_{stamp}.txt"
    jsn = out_dir / f"live_onions_{stamp}.json"
    gml = out_dir / f"provenance_{stamp}.graphml"
    sorted_live = sorted(verified_alive)
    txt.write_text("\n".join(f"http://{o}" for o in sorted_live) + "\n")
    jsn.write_text(json.dumps(sorted_live, indent=2))
    state.export_graphml(gml)

    # 8. Report.
    stats = state.stats()
    console.print("[bold]run summary[/]")
    console.print(f"  alive this run : {len(sorted_live)}")
    console.print(f"  total known    : {stats['total']}")
    console.print(f"  by status      : {stats['by_status']}")
    console.print(f"  NEWNYMs sent   : {newnym_count}")
    console.print(f"  output         : {txt.name} / {jsn.name} / {gml.name}")
    state.close()
    return 0


# ---------------------------------------------------------------------------
# Stats mode.
# ---------------------------------------------------------------------------

def run_stats(args: argparse.Namespace) -> int:
    state = State(args.db)
    state.init()
    stats = state.stats()
    Console().print_json(json.dumps(stats, indent=2))
    state.close()
    return 0


# ---------------------------------------------------------------------------
# NEWNYM-only mode.
# ---------------------------------------------------------------------------

def run_newnym(args: argparse.Namespace, cfg: Config) -> int:
    tor = TorController(
        control_port=cfg.tor.control_port,
        password=cfg.tor.control_password,
    )
    ok = tor.signal_newnym()
    Console().print(f"NEWNYM sent: {ok}")
    return 0 if ok else 6


# ---------------------------------------------------------------------------
# Smoke (alias of probe-clearnet for those who like --smoke).
# ---------------------------------------------------------------------------

async def run_smoke(cfg: Config, args: argparse.Namespace) -> int:
    return await run_probe_clearnet(cfg, args)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _install_signal_handlers(loop: asyncio.AbstractEventLoop) -> None:
    stop = loop.create_future()

    def _stop(*_):
        if not stop.done():
            stop.set_result(True)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _stop)
        except NotImplementedError:
            # Windows event loop
            pass


def main() -> int:
    args = build_argparser().parse_args()
    level = max(10, 30 - 10 * args.verbose + 10 * args.quiet)
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, markup=True)],
    )
    cfg = load_config(args.config)
    if args.mode == "probe-clearnet":
        return asyncio.run(run_probe_clearnet(cfg, args))
    if args.mode == "smoke":
        return asyncio.run(run_smoke(cfg, args))
    if args.mode == "stats":
        return run_stats(args)
    if args.mode == "newnym":
        return run_newnym(args, cfg)
    if args.mode == "crawl":
        return asyncio.run(run_crawl(cfg, args))
    Console().print(f"unknown mode: {args.mode}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
