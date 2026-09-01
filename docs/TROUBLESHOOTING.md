# Troubleshooting

## `Authentication failed: Wrong length on authentication cookie`

stem 1.8.2 (the version shipped with apt) hardcodes the cookie path
to `/var/lib/tor/control_auth_cookie` which is mode 600, owned by
`debian-tor`. It also doesn't accept `TOR_COOKIE` env var. The fix
is one of:

- Use **HashedControlPassword** instead. Generate with
  `tor --hash-password "yourpw"`, put the output in `torrc` as
  `HashedControlPassword 16:...`. Stem accepts this as a regular
  string via `c.authenticate(password="yourpw")`. This is the
  default in TORCrawl.
- Or chmod the cookie: `sudo chmod 644 /var/lib/tor/control_auth_cookie`
  (less secure).

## `CIRCUIT TIMEOUT after 180s`

The Tor daemon starts but never reaches `Bootstrapped 100%`. The
`notices.log` is stuck at `Bootstrapped 0% (starting): Starting` and
`Starting with guard context "default"`. This means **the host
cannot reach the public Tor network** — the relay handshake is
blocked at the firewall or NAT level.

TORCrawl's `--probe-clearnet` mode is exactly for this case. Use it
to verify the rest of the pipeline without Tor egress.

## aiohttp via SOCKS times out at 60s

This is the same root cause: the SOCKS port accepts the connection
but no working circuit exists, so the request is queued forever by
Tor until your client timeout. Always gate on
`status/circuit-established == 1` before any HTTP.

## `pip install` fails inside WSL with `[Errno -3] Temporary failure in name resolution`

WSL's default resolver doesn't reach `pypi.org`. Either:

- Run `pip install` from the **Windows** side (`py -m pip download`)
  and `cp` the wheel into WSL via `/mnt/c/...`.
- Configure WSL DNS: `sudo tee /etc/resolv.conf <<<'nameserver 1.1.1.1'`.

## `gh: command not found` when pushing

Install GitHub CLI: `sudo apt install -y gh` then `gh auth login`.
