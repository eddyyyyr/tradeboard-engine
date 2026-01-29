# engine/main.py

from __future__ import annotations

import csv
import json
from pathlib import Path

from .load_config import load_config


# Tu as uploadé: data/futures/fed_funds.csv
CSV_PATH = Path("data/futures/fed_funds.csv")

# On écrit le résultat ici (committable ou non, comme tu veux)
OUT_PATH = Path("data/output/fed_implied_curve.json")


# Mapping des codes mois futures (H=Mar, M=Jun, U=Sep, Z=Dec, etc.)
MONTH_CODE = {
    "F": 1,  # Jan
    "G": 2,  # Feb
    "H": 3,  # Mar
    "J": 4,  # Apr
    "K": 5,  # May
    "M": 6,  # Jun
    "N": 7,  # Jul
    "Q": 8,  # Aug
    "U": 9,  # Sep
    "V": 10, # Oct
    "X": 11, # Nov
    "Z": 12, # Dec
}


def parse_month_from_symbol(symbol: str) -> str | None:
    """
    Ex: ZQX25 -> month code X=Nov, year=2025 -> "2025-11"
    """
    symbol = symbol.strip().upper()
    if len(symbol) < 4:
        return None

    # Attend un format type ZQX25 (root + monthLetter + yy)
    month_letter = symbol[-3]
    yy = symbol[-2:]

    if month_letter not in MONTH_CODE:
        return None
    if not yy.isdigit():
        return None

    year = 2000 + int(yy)
    month = MONTH_CODE[month_letter]
    return f"{year:04d}-{month:02d}"


def to_float(x: str) -> float | None:
    x = (x or "").strip()
    if not x:
        return None
    try:
        return float(x)
    except ValueError:
        return None


def to_int(x: str) -> int | None:
    x = (x or "").strip()
    if not x:
        return None
    try:
        return int(float(x))  # au cas où c'est "20674.0"
    except ValueError:
        return None


def implied_rate_from_price(price: float) -> float:
    # Fed Funds futures: implied rate = 100 - price
    return 100.0 - float(price)


def main():
    fed = load_config("FED")

    print("✅ FED loaded")
    print("Bank:", fed["bank"]["name"])
    print("Current rate:", fed["current_rate"]["value"])

    if not CSV_PATH.exists():
        raise FileNotFoundError(f"CSV not found: {CSV_PATH} (check path + commit)")

    # 1) Lire le CSV brut
    raw = []
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            symbol = (r.get("Symbol") or "").strip()
            latest = to_float(r.get("Latest") or "")
            volume = to_int(r.get("Volume") or "")

            month = parse_month_from_symbol(symbol)
            if month is None or latest is None:
                continue  # on skip tout ce qui est inexploitable

            raw.append(
                {
                    "symbol": symbol,
                    "month": month,
                    "price": latest,
                    "volume": volume or 0,
                }
            )

    print(f"\n📄 Loaded CSV: {CSV_PATH}")
    print(f"✅ Parsed rows: {len(raw)}")

    # 2) OPTION 1: garder 1 contrat par mois (celui au plus gros volume)
    best_by_month: dict[str, dict] = {}
    for r in raw:
        m = r["month"]
        if (m not in best_by_month) or (r["volume"] > best_by_month[m]["volume"]):
            best_by_month[m] = r

    picked = [best_by_month[m] for m in sorted(best_by_month.keys())]

    # 3) Construire la courbe implicite propre (JSON-friendly)
    curve = []
    for r in picked:
        rate = implied_rate_from_price(r["price"])
        curve.append(
            {
                "month": r["month"],           # "2026-06"
                "rate": round(rate, 4),        # 3.51
                "symbol": r["symbol"],         # "ZQM26"
                "price": r["price"],           # 96.49
                "volume": r["volume"],         # 4308
            }
        )

    # 4) Écrire le JSON sur disque + afficher un aperçu
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(curve, indent=2), encoding="utf-8")

    print("\n📈 Implied curve (1 per month, max volume):")
    for p in curve[:12]:
        print(f"{p['month']} | {p['symbol']} | price={p['price']} | vol={p['volume']} -> {p['rate']} %")

    print(f"\n💾 Wrote JSON: {OUT_PATH} ({len(curve)} points)")


if __name__ == "__main__":
    main()
