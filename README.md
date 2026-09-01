# TORCrawl

Persistent, stateful, multi-strategy **Tor hidden-service cartographer**.

TORCrawl discovers `.onion` addresses from seed indexes, verifies each
candidate over Tor, records provenance (which seed reported which
onion), exports the full link graph as GraphML, and never forgets an
onion it has ever seen.

## Features

- **SQLite state** — every onion ever seen, status, response time, failure
  count, in-degree (how many other onions link to it), first/last seen.
  WAL mode for crash-resilience. No amnesia across runs.
- **Provenance graph** — when seed A links to onion B, that's a typed
  edge. yEd/Gephi can render it.
- **Multi-strategy extraction** — bare v3 onion regex + attribute href/src/
  data-href + `<noscript>` blocks + `<textarea>` content + JSON-LD
  `url`/`@id` fields. No more missed addresses from split lines or
  attribute-wrapped links.
- **Adaptive NEWNYM** — automatic circuit rotation after configurable
  probe count, on demand from CLI/TUI, and on failure clustering.
- **Rotating User-Agents** — fresh plausible Tor-Browser UA per session
  via faker.
- **Smart dead-marking** — any onion marked `alive` that wasn't seen in
  this run is auto-marked `dead` at the end.
- **Resumable** — WAL + per-run ledger means a crash mid-crawl is
  recoverable.
- **Live Rich TUI** — queue depth, RPS, fail ratio, avg response time,
  current exit fingerprint.
- **Multiple output formats** — TXT, JSON, JSONL, **GraphML** for
  yEd/Gephi.
- **Scam list filter** — built-in baseline + external `scam_list.txt`.
- **`--probe-clearnet` smoke mode** — exercise every non-Tor code path
  in any environment, no live darknet required.

## Install

```bash
sudo apt install -y tor python3-pip
pip3 install --user -r requirements.txt
```

## Tor control setup

Add to `/etc/tor/torrc`:

```
SocksPort 9052
ControlPort 9051
HashedControlPassword <output of `tor --hash-password "yourpw"`>
```

Restart Tor:

```bash
sudo systemctl restart tor
```

The password is read by stem; you can also pass it via the
`TORCRAWL_TOR_PASSWORD` env var.

## Usage

```bash
# Validate every non-Tor code path (no live darknet needed)
python3 -m torcrawl --mode probe-clearnet

# Real crawl
python3 -m torcrawl --mode crawl --seeds seeds/indexes.txt

# State stats
python3 -m torcrawl --mode stats

# Force-rotate Tor circuit
python3 -m torcrawl --mode newnym
```

The convenience launcher `./torcrawl.sh` does the same.

## What you get

- `out/live_onions_<timestamp>.txt` — one URL per line
- `out/live_onions_<timestamp>.json` — JSON array
- `out/provenance_<timestamp>.graphml` — full onion-provenance graph
  for yEd/Gephi

## Architecture

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md). Short version:

```
seeds → extract → state (SQLite) → verify (over Tor) → output
                                 ↑
                       tor_ctrl (NEWNYM)
```

Each module is small and focused. Tests live in `tests/`.

## Ethics

This tool is for **research, forensic mapping, and personal
intelligence-gathering about the darknet topology**. Don't use it to:

- Plan or execute attacks against people
- Distribute illegal material
- Bypass law enforcement

See [`docs/ETHICAL_USE.md`](docs/ETHICAL_USE.md).

## License

MIT — see [LICENSE](LICENSE).
