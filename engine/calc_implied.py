from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any, List, Optional


@dataclass
class FutureRow:
    month: str            # "2026-03" etc.
    price: float          # future price (ex 95.25)
    open_interest: Optional[int] = None
    volume: Optional[int] = None
    bid_ask_spread_bp: Optional[float] = None


def implied_rate_from_price(price: float, price_formula: str) -> float:
    """
    Convertit un prix future en taux implicite.
    - "100_minus_rate" : implied = 100 - price
    - "rate_direct"    : implied = price
    """
    if price_formula == "100_minus_rate":
        return 100.0 - float(price)
    if price_formula == "rate_direct":
        return float(price)
    raise ValueError(f"Unknown price_formula: {price_formula}")


def assess_quality(
    row: FutureRow,
    thresholds: Dict[str, Any],
    ignore_missing_spread: bool = True,
) -> str:
    """
    Reprise directe de l'idée de Claude:
    - OI + volume = critères obligatoires
    - spread optionnel si absent
    """
    oi = row.open_interest or 0
    vol = row.volume or 0
    spread = row.bid_ask_spread_bp

    def ok_spread(level: str) -> bool:
        if spread is None:
            return True if ignore_missing_spread else False
        max_spread = thresholds[level].get("max_bid_ask_spread_bp")
        if max_spread is None:
            return True
        return spread <= float(max_spread)

    # high
    if (
        oi >= int(thresholds["high"]["min_open_interest"])
        and vol >= int(thresholds["high"]["min_daily_volume"])
        and ok_spread("high")
    ):
        return "high"

    # medium
    if (
        oi >= int(thresholds["medium"]["min_open_interest"])
        and vol >= int(thresholds["medium"]["min_daily_volume"])
        and ok_spread("medium")
    ):
        return "medium"

    return "low"


def compute_implied_curve_from_rows(
    config: Dict[str, Any],
    rows: List[FutureRow],
) -> List[Dict[str, Any]]:
    """
    V1: calcule une courbe de taux implicites à partir de rows futures.
    Output simple: [{month, implied_rate, quality}]
    """
    futures_cfg = config.get("futures", {})
    price_formula = futures_cfg.get("price_formula", "100_minus_rate")

    thresholds = config.get("data_quality_thresholds", {
        "high": {"min_open_interest": 0, "min_daily_volume": 0},
        "medium": {"min_open_interest": 0, "min_daily_volume": 0},
    })
    ignore_missing_spread = bool(thresholds.get("ignore_missing_spread", True))

    out = []
    for r in rows:
        implied = implied_rate_from_price(r.price, price_formula)
        q = assess_quality(r, thresholds, ignore_missing_spread=ignore_missing_spread)
        out.append({"month": r.month, "implied_rate": round(implied, 4), "quality": q})
    return out
