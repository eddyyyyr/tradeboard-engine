# engine/main.py

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .load_config import load_config

# ✅ Change ça uniquement pour tester une banque
BANK_CODE = "ECB"  # "FED", "ECB", ...

DATA_FUTURES_DIR = Path("data/futures")
DATA_OUTPUT_DIR = Path("data/output")

# Convention fichiers (comme tu fais déjà)
# ex: FED -> fed_funds.csv / ecb_funds.csv
CSV_PATH = DATA_FUTURES_DIR / f"{BANK_CODE.lower()}_funds.csv"
OUT_PATH = DATA_OUTPUT_DIR / f"{BANK_CODE.lower()}_implied_curve.json"

# Mapping codes mois futures (H=Mar, M=Jun, U=Sep, Z=Dec, etc.)
MONTH_CODE = {
    "F": 1,   # Jan
    "G": 2,   # Feb
    "H": 3,   # Mar
    "J": 4,   # Apr
    "K": 5,   # May
    "M": 6,   # Jun
    "N": 7,   # Jul
    "Q": 8,   # Aug
    "U": 9,   # Sep
    "V": 10,  # Oct
    "X": 11,  # Nov
    "Z": 12,  # Dec
}


def parse_month_from_symbol(symbol: str) -> Optional[str]:
    """
    Ex: ZQX25 -> month code X=Nov, year=2025 -> "2025-11"
    """
    symbol = (symbol or "").strip().upper()
    if len(symbol) < 4:
        return None

    month_letter = symbol[-3]
    yy = symbol[-2:]

    if month_letter not in MONTH_CODE:
        return None
    if not yy.isdigit():
        return None

    year = 2000 + int(yy)
    month = MONTH_CODE[month_letter]
    return f"{year:04d}-{month:02d}"


def to_float(x: str) -> Optional[float]:
    x = (x or "").strip()
    if not x:
        return None
    try:
        return float(x)
    except ValueError:
        return None


def to_int(x: str) -> Optional[int]:
    x = (x or "").strip()
    if not x:
        return None
    try:
        # au cas où le CSV contient "20674.0"
        return int(float(x))
    except ValueError:
        return None


def implied_rate_from_price(price: float, price_formula: str) -> float:
    """
    Convertit un prix future en taux implicite selon la config.
    - "100_minus_rate" : implied = 100 - price
    - "rate_direct"    : implied = price
    """
    if price_formula == "100_minus_rate":
        return 100.0 - float(price)
    if price_formula == "rate_direct":
        return float(price)
    raise ValueError(f"Unknown price_formula: {price_formula}")


def load_barchart_csv(csv_path: Path) -> List[Dict[str, Any]]:
    """
    Lit le CSV Barchart watchlist.
    Colonnes attendues : Symbol, Name, Latest, Change, %Change, Open, High, Low, Volume, Time
    """
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path} (check path + commit)")

    raw: List[Dict[str, Any]] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            symbol = (r.get("Symbol") or "").strip()
            latest = to_float(r.get("Latest") or "")
            volume = to_int(r.get("Volume") or "")

            month = parse_month_from_symbol(symbol)
            if month is None or latest is None:
                continue

            raw.append(
                {
                    "symbol": symbol,
                    "month": month,
                    "price": latest,
                    "volume": volume or 0,
                }
            )

    return raw


def pick_one_per_month_max_volume(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    OPTION 1: garder 1 contrat par mois (celui au plus gros volume)
    """
    best_by_month: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        m = r["month"]
        if (m not in best_by_month) or (r["volume"] > best_by_month[m]["volume"]):
            best_by_month[m] = r

    return [best_by_month[m] for m in sorted(best_by_month.keys())]


def main():
    cfg = load_config(BANK_CODE)

    print(f"✅ {BANK_CODE} loaded")
    print("Bank:", cfg["bank"]["name"])
    print("Current rate:", cfg["current_rate"]["value"])

    futures_cfg = cfg.get("futures", {})
    price_formula = futures_cfg.get("price_formula", "100_minus_rate")

    # 1) Lire le CSV
    raw = load_barchart_csv(CSV_PATH)
    print(f"\n📄 Loaded CSV: {CSV_PATH}")
    print(f"✅ Parsed rows: {len(raw)}")

    # 2) Garder 1 contrat par mois (max volume)
    picked = pick_one_per_month_max_volume(raw)

    # 3) Construire la courbe implicite propre
    curve: List[Dict[str, Any]] = []
    for r in picked:
        rate = implied_rate_from_price(r["price"], price_formula)
        curve.append(
            {
                "month": r["month"],          # "2026-06"
                "rate": round(rate, 4),       # 3.51
                "symbol": r["symbol"],        # "ZQM26"
                "price": r["price"],          # 96.49
                "volume": r["volume"],        # 4308
            }
        )

    # 4) Écrire le JSON
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(curve, indent=2), encoding="utf-8")

    print("\n📈 Implied curve (1 per month, max volume):")
    for p in curve[:12]:
        print(
            f"{p['month']} | {p['symbol']} | price={p['price']} | "
            f"vol={p['volume']} -> {p['rate']} %"
        )

    print(f"\n💾 Wrote JSON: {OUT_PATH} ({len(curve)} points)")


if __name__ == "__main__":
    main()
