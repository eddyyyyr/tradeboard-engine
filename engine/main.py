# engine/main.py
from __future__ import annotations

import csv
from pathlib import Path

from .load_config import load_config
from .symbols import fed_funds_symbol_to_month


CSV_PATH = Path("data/futures/fed_funds.csv")


def main():
    fed = load_config("FED")

    print("✅ FED loaded")
    print("Bank:", fed["bank"]["name"])
    print("Current rate:", fed["current_rate"]["value"])

    # 1) Lire le CSV Barchart
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"CSV not found: {CSV_PATH}")

    rows = []
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            symbol = (r.get("Symbol") or "").strip()
            month = fed_funds_symbol_to_month(symbol)

            if month is None:
                continue  # on ignore ce qu’on ne comprend pas

            try:
                price = float(r.get("Latest"))
            except (TypeError, ValueError):
                continue

            volume = int(r.get("Volume") or 0)

            rows.append(
                {
                    "symbol": symbol,
                    "month": month,
                    "price": price,
                    "volume": volume,
                }
            )

    print(f"\n📄 Loaded CSV: {CSV_PATH} ({len(rows)} rows)")
    print("🔎 Preview parsed futures (first 10):")
    for r in rows[:10]:
        print(r)

    # 2) Conversion prix → taux implicite (100 - price)
    print("\n📈 Implied rates (first 10):")
    for r in rows[:10]:
        implied = round(100.0 - r["price"], 4)
        print(f"{r['month']} → {implied} %")


if __name__ == "__main__":
    main()
