# TORCrawl — Architecture

TORCrawl is a small package with a clear data path. Each module owns
one concern; cross-module state is minimised.

```
                        seeds/indexes.txt
                              │
                              ▼
              ┌──────────────────────────────┐
              │       torcrawl/extract       │   multi-strategy onion regex
              │                              │   href / data-href / noscript /
              └──────────────────────────────┘   textarea / JSON-LD
                              │ set[str]
                              ▼
              ┌──────────────────────────────┐
              │       torcrawl/scam          │   built-in denylist + scam_list.txt
              └──────────────────────────────┘
                              │ set[str]
                              ▼
              ┌──────────────────────────────┐         ┌─────────────────────┐
              │       torcrawl/state         │ ◀────── │    torcrawl/tor_ctrl │  NEWNYM
              │  SQLite (WAL) + provenance   │         │  stem 9051            │
              │  graph + GraphML export      │         └─────────────────────┘
              └──────────────────────────────┘
                              │ set[str] (candidates)
                              ▼
              ┌──────────────────────────────┐
              │        torcrawl/net          │  aiohttp via SOCKS9052
              │   HEAD->GET probe + UA        │
              └──────────────────────────────┘
                              │ (alive, rt)
                              ▼
                       out/{txt,json,graphml}
```

## Key design decisions

- **SQLite WAL** for crash-resumable state. Every probe writes through
  one connection guarded by an RLock; readers can attach new
  connections and stream-aggregate.
- **Provenance graph** in a second table `edges(source_url, target_onion, hit_count)`.
  The `in_degree` column on `onions` is a materialised counter — cheap
  to read, fed by an `UPDATE onions SET in_degree = in_degree + 1` on
  edge insertion. The next version will materialise an actual GraphML
  adjacency in memory if `in_degree` exceeds 5k.
- **Stem control** is wrapped in `TorController` so the rest of the
  codebase gets a structured `TorStatus` instead of catching
  exceptions. Auth is HashedControlPassword (portable, not cookie-file
  bound). The control port is the only thing stem needs.
- **aiohttp SOCKS** via `aiohttp_socks.ProxyConnector(rdns=True)`.
  Resolving `.onion` over Tor needs `rdns=True` so the resolution
  happens inside the Tor proxy, not on the local resolver.
- **Per-onion UA** from faker. Tor-Browser-shaped only.
- **Smart dead-marking** at the end of a run: any onion previously
  marked `alive` that didn't appear in this run's `verified_alive`
  set is `UPDATE`d to `dead`. This catches the case where a domain
  was up last week and dropped off the indexers.
- **CLI** is `python3 -m torcrawl --mode {crawl,probe-clearnet,stats,newnym,smoke}`.
  The `probe-clearnet` mode is the safety valve: it exercises every
  non-Tor path so you can validate the build on a sandbox VM that
  can't reach the public Tor network.

## Out of scope (v2)

- Per-domain SOCKS isolation (Tor's `IsolateClientAddr` +
  per-stream credentials) — useful for avoiding correlation if you
  re-use circuits across many onions, but adds significant complexity.
  Planned for v3.
- I2P eepsite discovery via the SAM bridge. v3.
- Live Ahmia.fi integration with proper rate limiting. v3.
- Browser-headless onion screenshotting. v3.
- A `crawl-daemon` mode that maintains a long-lived NEWNYM loop
  with Prometheus metrics. v3.
