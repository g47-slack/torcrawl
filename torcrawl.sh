#!/usr/bin/env bash
# Convenience launcher: brings up Tor (if not running) and runs TORCrawl.
# Usage:
#   ./torcrawl.sh probe-clearnet
#   ./torcrawl.sh crawl
#   ./torcrawl.sh stats
#   ./torcrawl.sh newnym

set -euo pipefail

cd "$(dirname "$0")"

# Ensure deps.
python3 -c "import aiohttp, aiohttp_socks, faker, rich, stem, yaml" 2>/dev/null || {
  echo "Missing Python deps. Install with: pip3 install --user -r requirements.txt"
  exit 1
}

# Ensure Tor control port is up.
if ! ss -tlnp 2>/dev/null | grep -q ':9051 '; then
  echo "Tor control port 9051 not listening. Start tor or update config."
  exit 2
fi

case "${1:-crawl}" in
  probe-clearnet|smoke)
    exec python3 -m torcrawl --mode probe-clearnet
    ;;
  crawl)
    exec python3 -m torcrawl --mode crawl
    ;;
  stats)
    exec python3 -m torcrawl --mode stats
    ;;
  newnym)
    exec python3 -m torcrawl --mode newnym
    ;;
  *)
    echo "unknown mode: $1"
    echo "usage: $0 [probe-clearnet|crawl|stats|newnym]"
    exit 1
    ;;
esac
