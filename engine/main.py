# engine/main.py

from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, Any, List, Optional

from .load_config import load_config
from .calc_implied import implied_rate_from_price


CSV_PATH = Path("data/futures/fed_funds.csv")


def _to_int(x: Any) -> int:
    try:
        return int(str(x).strip())
    except Exception:
        return 0


def _to_float(x: Any) -> Optional[float]:
    try:
        return float(str(x).strip())
    except Exception:
        return None


def main():
    fed = load_config("FED")

    print("✅ FED loaded")
    print("Bank:", fed["bank"]["name"])
    print("Current rate:", fed["current_rate"]["value"])

    # 1) Lire le CSV Barchart
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"CSV not found: {CSV_PATH} (check path + commit)")

    raw = []
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            raw.append(
                {
                    "symbol": (r.get("Symbol") or "").strip(),
                    "name": (r.get("Name") or "").strip(),
                    "latest": (r.get("Latest") or "").strip(),
                    "volume": (r.get("Volume") or "").strip(),
                    "time": (r.get("Time") or "").strip(),
                }
            )

    print(f"\n📄 Loaded CSV: {CSV_PATH} ({len(raw)} rows)")

    # 2) Parser -> {symbol, month, price, volume}
    parsed: List[Dict[str, Any]] = []
    for r in raw:
        sym = r["symbol"]
        month = None
        price = _to_float(r["latest"])
        vol = _to_int(r["volume"])

        # on ne garde que les symboles type ZQX25
        if len(sym) == 5 and sym.startswith("ZQ"):
            # mapping mois lettre (CME)
            m = sym[2].upper()
            y = sym[3:5]
            month_map = {
                "F": "01",
                "G": "02",
                "H": "03",
                "J": "04",
                "K": "05",
                "M": "06",
                "N": "07",
                "Q": "08",
                "U": "09",
                "V": "10",
                "X": "11",
                "Z": "12",
            }
            if m in month_map:
                month = f"20{y}-{month_map[m]}"

        if month and price is not None:
            parsed.append({"symbol": sym, "month": month, "price": price, "volume": vol})

    parsed.sort(key=lambda x: (x["month"], x["symbol"]))
    print(f"🧾 Parsed rows: {len(parsed)}")
    print("🔎 Preview parsed (first 10):")
    for r in parsed[:10]:
        print(r)

    # 3) Agrégation: 1 ligne par mois -> max volume
    best_by_month: Dict[str, Dict[str, Any]] = {}
    for r in parsed:
        m = r["month"]
        if m not in best_by_month or r["volume"] > best_by_month[m]["volume"]:
            best_by_month[m] = r

    curve = [best_by_month[m] for m in sorted(best_by_month.keys())]

    # 4) Taux implicites (100 - price) via config
    price_formula = (
        fed.get("futures", {}).get("price_formula", "100_minus_rate")
        if isinstance(fed, dict)
        else "100_minus_rate"
    )

    print("\n📈 Implied curve (1 per month, max volume):")
    for r in curve:
        implied = implied_rate_from_price(r["price"], price_formula)
        print(
            f"{r['month']} | {r['symbol']} | price={r['price']} | vol={r['volume']} -> {round(implied, 4)} %"
        )


if __name__ == "__main__":
    main()
