"""Unit tests for the multi-strategy onion extractor."""

from torcrawl.extract import extract_onions_from_html

ONION = "a" * 56 + ".onion"
OTHER = "b" * 56 + ".onion"


def test_bare_in_text():
    html = f"hello {ONION} world"
    assert ONION in extract_onions_from_html(html)


def test_in_href_attr():
    html = f'<a href="http://{ONION}/page">x</a>'
    out = extract_onions_from_html(html)
    assert ONION in out


def test_in_noscript():
    html = f"<noscript><a href='http://{ONION}'>x</a></noscript>"
    out = extract_onions_from_html(html)
    assert ONION in out


def test_in_textarea():
    html = f"<textarea>{ONION}</textarea>"
    assert ONION in extract_onions_from_html(html)


def test_in_data_href():
    html = f'<div data-href="http://{ONION}/x">x</div>'
    assert ONION in extract_onions_from_html(html)


def test_split_across_html():
    html = f"<p>the address is {ONION[:30]}<br>{ONION[30:]}</p>"
    assert ONION in extract_onions_from_html(html)


def test_invalid_garbage():
    html = "no onion here, just 64base lowercase nonsense aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.onion"
    assert "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.onion" not in extract_onions_from_html(html)


def test_multiple():
    html = f"{ONION} and {OTHER}"
    out = extract_onions_from_html(html)
    assert {ONION, OTHER} <= out
