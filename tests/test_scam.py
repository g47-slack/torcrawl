"""Unit tests for the scam filter."""

from torcrawl.scam import ScamFilter


def test_builtin_blocks_known():
    sf = ScamFilter(denylist=set())
    # built-in baseline
    assert sf.is_scam("darkfailllnkf4vf.onion")


def test_filter_drops_matches():
    sf = ScamFilter(denylist={"known.onion", "another.onion"})
    assert sf.filter({"good.onion", "known.onion", "another.onion"}) == {"good.onion"}


def test_is_scam_case_insensitive():
    sf = ScamFilter(denylist={"A.onion"})
    assert sf.is_scam("a.onion")
    assert sf.is_scam("A.ONION")
