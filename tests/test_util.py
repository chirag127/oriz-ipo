"""Unit tests for util parsing helpers."""

from ipo_watch.util import parse_money, parse_pct, upper_band, slugify, clean


def test_parse_money():
    assert parse_money("₹245") == 245.0
    assert parse_money("1,116") == 1116.0
    assert parse_money("₹- (Ni)") is None
    assert parse_money("") is None
    assert parse_money(None) is None
    assert parse_money("0") == 0.0


def test_parse_pct():
    assert parse_pct("₹1,116 (28.13%)") == 28.13
    assert parse_pct("30.51%") == 30.51
    assert parse_pct("₹- (0.00%)") == 0.0
    assert parse_pct("no percent here") is None
    assert parse_pct(None) is None


def test_upper_band():
    assert upper_band("829–871") == 871.0
    assert upper_band("₹151–159") == 159.0
    assert upper_band("100 to 108") == 108.0
    assert upper_band("") is None
    assert upper_band(None) is None


def test_slugify():
    assert slugify("Dhoot Transmission Ltd. (Mainboard)") == "dhoot-transmission-ltd-mainboard"
    assert slugify("LEAP India") == "leap-india"
    assert slugify("") == "ipo"


def test_clean():
    assert clean("  a\n  b\t c ") == "a b c"
    assert clean(None) == ""
