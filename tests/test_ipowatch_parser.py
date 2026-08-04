"""Parser test against a captured real IPOWatch fixture (offline, deterministic)."""

from pathlib import Path

import pytest
from selectolax.parser import HTMLParser

from ipo_watch.sources.ipowatch import IpoWatch
from ipo_watch.util import clean, parse_money, parse_pct
from ipo_watch.sources.base import compute_gmp_pct
from ipo_watch.models import Ipo

FIXTURE = Path(__file__).parent / "fixtures" / "ipowatch.html"


def _parse_fixture() -> list[Ipo]:
    """Mirror IpoWatch.fetch() parsing on the saved HTML (no network)."""
    tree = HTMLParser(FIXTURE.read_text(encoding="utf-8"))
    out: list[Ipo] = []
    for table in tree.css("table"):
        rows = table.css("tr")
        if len(rows) < 2:
            continue
        header = [clean(c.text()).lower() for c in rows[0].css("th,td")]
        if not (any("ipo" in h for h in header) and any("gmp" in h for h in header)):
            continue
        idx = {h: i for i, h in enumerate(header)}

        def col(cells, *keys):
            for k in keys:
                for h, i in idx.items():
                    if k in h and i < len(cells):
                        return clean(cells[i].text())
            return ""

        for row in rows[1:]:
            cells = row.css("td")
            if len(cells) < 2:
                continue
            name = clean(cells[0].text())
            if not name:
                continue
            est = col(cells, "est. listing", "est listing", "listing")
            ipo = Ipo(
                name=name,
                gmp=parse_money(col(cells, "gmp")),
                gmp_pct=parse_pct(est),
                price_band=col(cells, "price"),
                source="ipowatch",
            )
            compute_gmp_pct(ipo)
            out.append(ipo)
        break
    return out


@pytest.mark.skipif(not FIXTURE.exists(), reason="fixture not captured")
def test_ipowatch_parses_rows():
    ipos = _parse_fixture()
    assert len(ipos) >= 5, "should parse multiple rows"
    named = [i for i in ipos if i.name]
    assert len(named) == len(ipos)


@pytest.mark.skipif(not FIXTURE.exists(), reason="fixture not captured")
def test_ipowatch_gmp_pct_present():
    ipos = _parse_fixture()
    with_pct = [i for i in ipos if i.gmp_pct is not None]
    assert len(with_pct) >= 3, "several rows should carry a GMP%"
    # all percentages are sane numbers
    for i in with_pct:
        assert -50 <= i.gmp_pct <= 500
