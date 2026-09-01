# Ethical Use

TORCrawl is a **research tool**. It discovers and verifies public
`.onion` addresses from publicly-indexed sources. It does not interact
with hidden services beyond issuing a single `HEAD`/`GET` to confirm
they respond.

## What this tool IS for

- Mapping the topology of the Tor hidden-service space for academic
  research.
- Forensic identification of known-scam onion addresses (so they can
  be added to denylists).
- Personal monitoring of which `.onion` services are alive or dead.
- Defensive security research — tracking how the phishing landscape
  evolves.

## What this tool is NOT for

- **Attacking people.** Don't use TORCrawl to plan, coordinate, or
  execute illegal activity against any person or system.
- **Distributing illegal material.** TORCrawl does not distribute,
  host, or serve any content.
- **Bypassing law enforcement.** If you're being investigated by law
  enforcement, this tool will not help you.
- **Scraping at abusive rates.** The default 12-concurrency cap and
  3s inter-index delay are designed to be polite. If you crank these
  up, you will get rate-limited and you will not get good data.

## The transparency principle

Every onion you discover through TORCrawl is discovered because a
**publicly-indexed seed** chose to link to it. TORCrawl does not
guess, generate, or enumerate addresses. The anonymity guarantees of
Tor are not affected by TORCrawl.

## Reporting abuse

If you find an onion that is hosting child sexual abuse material,
contact the Tor Project or the relevant national authority. TORCrawl
is not a reporting tool; it is a research tool.
