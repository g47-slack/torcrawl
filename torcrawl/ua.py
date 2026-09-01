"""
User-Agent factory. Each session pulls a fresh plausible Tor-Browser UA
from faker so we never re-use the same fingerprint inside a single
run. The "tor browser" profile (Firefox ESR + Gecko) is the only
sane choice for `.onion` fetches — sites routinely 403 on Chrome UA.
"""

from __future__ import annotations

from faker import Faker


class UserAgentFactory:
    def __init__(self, seed: int = 0) -> None:
        self._faker = Faker()
        self._faker.seed_instance(seed)

    def next(self) -> str:
        rv = self._faker.random_int(min=100, max=115)
        return (
            f"Mozilla/5.0 (Windows NT 10.0; rv:{rv}.0) "
            f"Gecko/20100101 Firefox/{rv}.0"
        )
