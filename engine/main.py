# engine/main.py

from __future__ import annotations

import csv
import json
from pathlib import Path

from .load_config import load_config

# ----------------------------
# ✅ 1 CSV global (watchlist)
# ----------------------------
CSV_PATH = Path("data/futures/watchlist.csv")
OUT_DIR = Path("data/output")

# Filtrage par banque via la colonne "Name" du CSV
# (ajuste ECB si besoin selon le libellé exact dans ton fichier)
NAME_FILTERS = {
    "FED": ["30-Day Fed Funds"],
    "BOE": ["3-Month SONIA"],
    "ECB": ["€STR", "ESTR", "Euribor", "EURIBOR"],  # fallback: à affiner si besoin
    # Exemples si tu ajoutes après :
    # "SNB": ["3-Month SARON"],
    # "BOC": ["CORRA 3-Month", "CORRA 3-Month"],
    # "BOJ": ["3-Month TONA", "TONA"],
}

# Mapping des codes mois futures (H=Mar, M=Jun, U=Sep, Z=Dec, etc.)
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


def load_csv_rows(csv_path: Path) -> list[dict]:
    """
    Lit le CSV Barchart (Symbol, Name, Latest, Volume, ...)
    et retourne une liste de rows normalisées.
    """
    raw: list[dict] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            symbol = (r.get("Symbol") or "").strip()
            name = (r.get("Name") or "").strip()
            latest = to_float(r.get("Latest") or "")
            volume = to_int(r.get("Volume") or "")

            month = parse_month_from_symbol(symbol)
            if month is None or latest is None:
                continue

            raw.append(
                {
                    "symbol": symbol,
                    "name": name,
                    "month": month,
                    "price": latest,
                    "volume": volume or 0,
                }
            )
    return raw


def pick_one_per_month_max_volume(rows: list[dict]) -> list[dict]:
    """
    OPTION 1: garder 1 contrat par mois (celui au plus gros volume).
    """
    best_by_month: dict[str, dict] = {}
    for r in rows:
        m = r["month"]
        if (m not in best_by_month) or (r["volume"] > best_by_month[m]["volume"]):
            best_by_month[m] = r
    return [best_by_month[m] for m in sorted(best_by_month.keys())]


def build_curve(picked: list[dict], price_formula: str) -> list[dict]:
    curve: list[dict] = []
    for r in picked:
        rate = implied_rate_from_price(r["price"], price_formula)
        curve.append(
            {
                "month": r["month"],      # "2026-06"
                "rate": round(rate, 4),   # 3.51
                "symbol": r["symbol"],    # "ZQM26"
                "price": r["price"],      # 96.49
                "volume": r["volume"],    # 4308
                "name": r.get("name", ""),  # utile debug
            }
        )
    return curve


def filter_rows_for_bank(rows: list[dict], bank_code: str) -> list[dict]:
    filters = NAME_FILTERS.get(bank_code, [])
    if not filters:
        return []

    filters_l = [f.lower() for f in filters]

    filtered: list[dict] = []
    for r in rows:
        nm = (r.get("name") or "").lower()
        if any(f in nm for f in filters_l):
            filtered.append(r)
    return filtered


def run_bank(bank_code: str, all_rows: list[dict]) -> None:
    cfg = load_config(bank_code)

    bank_name = cfg["bank"]["name"]
    current_rate = cfg["current_rate"]["value"]
    futures_cfg = cfg.get("futures", {})
    price_formula = futures_cfg.get("price_formula", "100_minus_rate")

    code_lower = bank_code.lower()
    out_path = OUT_DIR / f"{code_lower}_implied_curve.json"

    print(f"\n==============================")
    print(f"✅ {bank_code} loaded")
    print(f"Bank: {bank_name}")
    print(f"Current rate: {current_rate}")
    print(f"CSV: {CSV_PATH}")
    print(f"Price formula: {price_formula}")
    print(f"Name filters: {NAME_FILTERS.get(bank_code)}")

    filtered = filter_rows_for_bank(all_rows, bank_code)
    print(f"✅ Filtered rows: {len(filtered)}")

    if len(filtered) == 0:
        print(f"⚠️ No rows matched for {bank_code}. JSON will be empty.")
        curve: list[dict] = []
    else:
        picked = pick_one_per_month_max_volume(filtered)
        curve = build_curve(picked, price_formula)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(curve, indent=2), encoding="utf-8")

    print("\n📈 Implied curve (1 per month, max volume):")
    for p in curve[:12]:
        print(
            f"{p['month']} | {p['symbol']} | price={p['price']} | vol={p['volume']} -> {p['rate']} %"
        )

    print(f"\n💾 Wrote JSON: {out_path} ({len(curve)} points)")


def main():
    # Banque(s) activées pour l’instant
    bank_codes = ["FED", "ECB", "BOE"]

    if not CSV_PATH.exists():
        raise FileNotFoundError(f"CSV not found: {CSV_PATH} (check path + commit)")

    all_rows = load_csv_rows(CSV_PATH)
    print(f"✅ Parsed total rows: {len(all_rows)}")

    for code in bank_codes:
        run_bank(code, all_rows)


if __name__ == "__main__":
    main()
