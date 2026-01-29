# engine/main.py

from __future__ import annotations

import csv
from pathlib import Path

from .load_config import load_config


CSV_PATH = Path("data/futures/fed_funds.csv")


def main():
    fed = load_config("FED")

    print("✅ FED loaded")
    print("Bank:", fed["bank"]["name"])
    print("Current rate:", fed["current_rate"]["value"])

    # 1) Lire le CSV Barchart (uploadé sur GitHub)
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"CSV not found: {CSV_PATH} (check path + commit)")

    rows = []
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            # Colonnes Barchart: Symbol, Name, Latest, Change, %Change, Open, High, Low, Volume, Time
            rows.append(
                {
                    "symbol": (r.get("Symbol") or "").strip(),
                    "name": (r.get("Name") or "").strip(),
                    "latest": (r.get("Latest") or "").strip(),
                    "volume": (r.get("Volume") or "").strip(),
                    "time": (r.get("Time") or "").strip(),
                }
            )

    print(f"\n📄 Loaded CSV: {CSV_PATH} ({len(rows)} rows)")
    print("🔎 Preview (first 10 rows):")
    for r in rows[:10]:
        print(r)


if __name__ == "__main__":
    main()
