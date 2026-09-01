"""Unit tests for the UA factory."""

from torcrawl.ua import UserAgentFactory


def test_ua_is_tor_browser_shaped():
    f = UserAgentFactory()
    ua = f.next()
    assert "Firefox/" in ua
    assert "Gecko/20100101" in ua
    assert "rv:" in ua


def test_ua_factory_distinct():
    f = UserAgentFactory(seed=0)
    seen = {f.next() for _ in range(50)}
    # with seed=0 faker is deterministic, but we still want no catastrophic collisions
    assert len(seen) > 1
