"""
Scam list filter.

The v1 prototype hard-coded a small denylist inline. v2 keeps the
hard-coded baseline (well-known long-dead takedown targets) and
extends it from a `scam_list.txt` file at runtime. A simple
brand-impersonation heuristic is a v3 add (page-title matches a
banking brand but the body has credential-form fields -> flag).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Set


_BUILTIN_SCAM = {
    "darkfailenbsdla5mal2mxn2uz66od5vtzd5qozslagrfzachha3f3id.onion",
    "darkfailllnkf4vf.onion",
    "torbox3uiot6wchz.onion",
    "pwoah7foa6au2pul.onion",
    "empiremarketdarknwz.onion",
    "alphabay2ie4j2zs7.onion",
    "agorahooawayyfoe.onion",
    "dreammarketb7j2w5.onion",
    "abacusjrx4dlcsp6.onion",   # fake Abacus
    "hydraruzxpnew4af.onion",     # old hydra mirror
}


class ScamFilter:
    def __init__(self, *, denylist: Set[str]) -> None:
        self.denylist = {o.strip().lower() for o in denylist if o.strip()}

    @classmethod
    def from_files(cls, *paths: Path) -> "ScamFilter":
        merged: Set[str] = set(_BUILTIN_SCAM)
        for p in paths:
            try:
                for line in Path(p).read_text(encoding="utf-8").splitlines():
                    line = line.strip().lower()
                    if line and not line.startswith("#"):
                        merged.add(line)
            except FileNotFoundError:
                continue
        return cls(denylist=merged)

    def filter(self, onions: Iterable[str]) -> Set[str]:
        return {o for o in onions if o.lower() not in self.denylist}

    def is_scam(self, onion: str) -> bool:
        return onion.lower() in self.denylist
