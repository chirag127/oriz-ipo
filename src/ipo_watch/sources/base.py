"""Source base class + registry. Each source returns list[Ipo] or raises."""

from __future__ import annotations

from ..models import Ipo


class Source:
    name: str = "base"
    url: str = ""

    def fetch(self) -> list[Ipo]:  # pragma: no cover - interface
        raise NotImplementedError


def compute_gmp_pct(ipo: Ipo) -> None:
    """Fill gmp_pct from gmp + upper price band when the site didn't give a %."""
    from ..util import upper_band

    if ipo.gmp_pct is not None:
        return
    ub = upper_band(ipo.price_band)
    if ipo.gmp is not None and ub:
        ipo.gmp_pct = round(ipo.gmp / ub * 100, 2)
