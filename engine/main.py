# engine/main.py

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from .load_config import load_config
from .meeting_expected import compute_after_meeting_curve

# ----------------------------
# ✅ 1 CSV global (watchlist)
# ----------------------------
CSV_PATH = Path("data/futures/watchlist.csv")
OUT_DIR = Path("data/output")

# Filtrage par banque via la colonne "Name" du CSV
NAME_FILTERS = {
    "FED": ["30-Day Fed Funds"],
    "BOE": ["3-Month SONIA"],
    # ECB : Euribor / €STR / ESTR etc.
    "ECB": ["3-Month Euribor", "€STR", "ESTR", "Euribor", "EURIBOR"],
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


# ----------------------------
# ✅ Helpers dates mois
# ----------------------------
def now_month_utc() -> str:
    """Retourne le mois courant en UTC au format 'YYYY-MM'."""
    dt = datetime.now(timezone.utc)
    return f"{dt.year:04d}-{dt.month:02d}"


def month_to_index(month: str) -> int:
    """'YYYY-MM' -> index linéaire (année*12 + mois-1)"""
    y = int(month[0:4])
    m = int(month[5:7])
    return y * 12 + (m - 1)


def index_to_month(idx: int) -> str:
    """index linéaire -> 'YYYY-MM'"""
    y = idx // 12
    m = (idx % 12) + 1
    return f"{y:04d}-{m:02d}"


def parse_month_from_symbol(symbol: str) -> str | None:
    """
    Ex: ZQX25 -> month code X=Nov, year=2025 -> "2025-11"
    """
    symbol = symbol.strip().upper()
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
        return int(float(x))
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


def pick_one_per_month_max_volume(rows: list[dict]) -> list[dict]:
    """
    Garde 1 contrat par mois (celui au plus gros volume).
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
                "month": r["month"],
                "rate": round(rate, 4),
                "symbol": r["symbol"],
                "price": r["price"],
                "volume": r["volume"],
                "name": r.get("name", ""),
                "synthetic": False,
            }
        )
    return curve


def strip_past_months(curve: list[dict]) -> list[dict]:
    """
    Supprime les mois passés (strictement < mois courant UTC).
    """
    cutoff = now_month_utc()
    return [p for p in curve if (p.get("month") or "") >= cutoff]


# ----------------------------
# ✅ NOUVEAU : interpolation mensuelle
# ----------------------------
def densify_monthly_linear(curve: list[dict]) -> list[dict]:
    """
    Si la courbe a des trous (ex: Mar, Jun, Sep, Dec),
    on ajoute les mois manquants par interpolation linéaire des rates.

    Les points interpolés auront:
      - synthetic=True
      - symbol/price/volume/name vides (ou 0)
    """
    if len(curve) < 2:
        return curve

    # Assure tri
    curve_sorted = sorted(curve, key=lambda x: x["month"])

    # Indexer les points d'origine
    idx_points = [(month_to_index(p["month"]), p) for p in curve_sorted]

    out_by_idx: dict[int, dict] = {}
    for idx, p in idx_points:
        out_by_idx[idx] = p

    for i in range(len(idx_points) - 1):
        idx0, p0 = idx_points[i]
        idx1, p1 = idx_points[i + 1]
        gap = idx1 - idx0
        if gap <= 1:
            continue

        r0 = float(p0["rate"])
        r1 = float(p1["rate"])

        # Remplit les mois entre
        for k in range(1, gap):
            t = k / gap
            rk = r0 + (r1 - r0) * t
            idxk = idx0 + k
            mk = index_to_month(idxk)

            if idxk in out_by_idx:
                continue

            out_by_idx[idxk] = {
                "month": mk,
                "rate": round(rk, 4),
                "symbol": "",
                "price": None,
                "volume": 0,
                "name": "synthetic",
                "synthetic": True,
            }

    # Retour trié
    out = [out_by_idx[idx] for idx in sorted(out_by_idx.keys())]
    return out


def meeting_months_from_config(cfg: dict) -> list[str]:
    """
    Accepte:
    meetings:
      days:
        - "2026-02-05"
        - "2026-03-19"
    ou
    meetings:
      dates: [...]
    """
    meetings = cfg.get("meetings", {})
    if not isinstance(meetings, dict):
        return []

    dates = meetings.get("days") or meetings.get("dates") or []
    if not isinstance(dates, list):
        return []

    out: list[str] = []
    for d in dates:
        if isinstance(d, str) and len(d) >= 10:
            out.append(d)
    return sorted(out)


def filter_curve_to_meetings(
    curve: list[dict],
    meeting_dates: list[str],
    current_rate: float,
    increment_bp: int,
) -> list[dict]:
    """
    OPTION B: points après réunion (pondération jours avant/après) à partir de la courbe mensuelle.
    """
    if not meeting_dates:
        return []
    return compute_after_meeting_curve(
        monthly_curve=curve,
        meeting_dates=meeting_dates,
        current_rate=current_rate,
        increment_bp=increment_bp,
    )


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def run_bank(bank_code: str, all_rows: list[dict]) -> None:
    cfg = load_config(bank_code)

    bank_name = cfg["bank"]["name"]
    current_rate = float(cfg["current_rate"]["value"])
    increment_bp = int(cfg.get("current_rate", {}).get("increment_bp", 25))

    futures_cfg = cfg.get("futures", {})
    price_formula = futures_cfg.get("price_formula", "100_minus_rate")

    code_lower = bank_code.lower()

    out_curve_path = OUT_DIR / f"{code_lower}_implied_curve.json"
    out_meetings_path = OUT_DIR / f"{code_lower}_implied_meetings.json"

    print(f"\n==============================")
    print(f"✅ {bank_code} loaded")
    print(f"Bank: {bank_name}")
    print(f"Current rate: {current_rate}")
    print(f"CSV: {CSV_PATH}")
    print(f"Price formula: {price_formula}")
    print(f"Name filters: {NAME_FILTERS.get(bank_code)}")
    print(f"Increment bp: {increment_bp}")

    filtered = filter_rows_for_bank(all_rows, bank_code)
    print(f"✅ Filtered rows: {len(filtered)}")

    if len(filtered) == 0:
        print(f"⚠️ No rows matched for {bank_code}. JSON will be empty.")
        curve: list[dict] = []
        meetings_curve: list[dict] = []
    else:
        picked = pick_one_per_month_max_volume(filtered)
        curve = build_curve(picked, price_formula)

        # 1) supprime les dates passées
        curve = strip_past_months(curve)

        # 2) ✅ ECB (Euribor IMM) : densifie en mensuel pour une courbe “Financial Source-like”
        if bank_code == "ECB":
            curve = densify_monthly_linear(curve)

        # 3) OPTION B: meetings (si dates présentes)
        meeting_dates = meeting_months_from_config(cfg)
        meetings_curve = filter_curve_to_meetings(
            curve=curve,
            meeting_dates=meeting_dates,
            current_rate=current_rate,
            increment_bp=increment_bp,
        )

    write_json(out_curve_path, curve)
    write_json(out_meetings_path, meetings_curve)

    print("\n📈 Monthly curve (future months only):")
    for p in curve[:24]:
        syn = " (synthetic)" if p.get("synthetic") else ""
        print(f"{p['month']} -> {p['rate']}%{syn}")
    print(f"\n💾 Wrote JSON: {out_curve_path} ({len(curve)} points)")

    print("\n📅 Meeting curve (Option B):")
    for p in meetings_curve[:12]:
        print(
            f"{p.get('meetingDate')} | rateAfter={p.get('rateAfter')} | moveAfterBps={p.get('moveAfterBps')} | w_after={p.get('weightAfter')}"
        )
    print(f"\n💾 Wrote JSON: {out_meetings_path} ({len(meetings_curve)} points)")


def main():
    bank_codes = ["FED", "ECB", "BOE"]

    if not CSV_PATH.exists():
        raise FileNotFoundError(f"CSV not found: {CSV_PATH} (check path + commit)")

    all_rows = load_csv_rows(CSV_PATH)
    print(f"✅ Parsed total rows: {len(all_rows)}")

    for code in bank_codes:
        run_bank(code, all_rows)


if __name__ == "__main__":
    main()
