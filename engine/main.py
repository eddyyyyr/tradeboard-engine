# engine/main.py

from __future__ import annotations

import csv
import json
import calendar
from datetime import datetime, timezone
from pathlib import Path

from .load_config import load_config
from .meeting_expected import compute_after_meeting_curve


# -------------------------------------------------
# CONFIG
# -------------------------------------------------

CSV_PATH = Path("data/futures/watchlist.csv")
OUT_DIR = Path("data/output")

NAME_FILTERS = {
    "FED": ["30-Day Fed Funds"],
    "BOE": ["3-Month SONIA"],
    "ECB": ["3-Month Euribor"],  # ✅ Euribor ONLY
}

MONTH_CODE = {
    "F": 1, "G": 2, "H": 3, "J": 4,
    "K": 5, "M": 6, "N": 7, "Q": 8,
    "U": 9, "V": 10, "X": 11, "Z": 12,
}


# -------------------------------------------------
# HELPERS
# -------------------------------------------------

def now_month_utc() -> str:
    dt = datetime.now(timezone.utc)
    return f"{dt.year:04d}-{dt.month:02d}"


def month_to_index(month: str) -> int:
    y = int(month[0:4])
    m = int(month[5:7])
    return y * 12 + (m - 1)


def index_to_month(idx: int) -> str:
    y = idx // 12
    m = (idx % 12) + 1
    return f"{y:04d}-{m:02d}"


def parse_month_from_symbol(symbol: str) -> str | None:
    symbol = symbol.strip().upper()
    if len(symbol) < 4:
        return None

    month_letter = symbol[-3]
    yy = symbol[-2:]

    if month_letter not in MONTH_CODE or not yy.isdigit():
        return None

    year = 2000 + int(yy)
    month = MONTH_CODE[month_letter]
    return f"{year:04d}-{month:02d}"


def to_float(x: str) -> float | None:
    try:
        return float(x.strip())
    except:
        return None


def to_int(x: str) -> int | None:
    try:
        return int(float(x.strip()))
    except:
        return None


def implied_rate_from_price(price: float, formula: str) -> float:
    if formula == "100_minus_rate":
        return 100.0 - float(price)
    if formula == "rate_direct":
        return float(price)
    raise ValueError("Unknown price_formula")


# -------------------------------------------------
# CSV LOADING
# -------------------------------------------------

def load_csv_rows(csv_path: Path) -> list[dict]:
    rows = []
    with csv_path.open("r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            symbol = (r.get("Symbol") or "").strip()
            name = (r.get("Name") or "").strip()
            latest = to_float(r.get("Latest") or "")
            volume = to_int(r.get("Volume") or "") or 0

            month = parse_month_from_symbol(symbol)
            if month and latest is not None:
                rows.append({
                    "symbol": symbol,
                    "name": name,
                    "month": month,
                    "price": latest,
                    "volume": volume,
                })
    return rows


def filter_rows_for_bank(rows: list[dict], bank_code: str) -> list[dict]:
    filters = [f.lower() for f in NAME_FILTERS.get(bank_code, [])]
    return [r for r in rows if any(f in r["name"].lower() for f in filters)]


def pick_one_per_month_max_volume(rows: list[dict]) -> list[dict]:
    best = {}
    for r in rows:
        m = r["month"]
        if m not in best or r["volume"] > best[m]["volume"]:
            best[m] = r
    return [best[m] for m in sorted(best.keys())]


def build_curve(picked: list[dict], price_formula: str) -> list[dict]:
    curve = []
    for r in picked:
        rate = implied_rate_from_price(r["price"], price_formula)
        curve.append({
            "month": r["month"],
            "rate": round(rate, 4),
            "symbol": r["symbol"],
            "price": r["price"],
            "volume": r["volume"],
            "name": r["name"],
            "synthetic": False,
        })
    return curve


def strip_past_months(curve: list[dict]) -> list[dict]:
    cutoff = now_month_utc()
    return [p for p in curve if p["month"] >= cutoff]


# -------------------------------------------------
# DENSIFICATION
# -------------------------------------------------

def densify_monthly_linear(curve: list[dict]) -> list[dict]:
    if len(curve) < 2:
        return curve

    curve = sorted(curve, key=lambda x: x["month"])
    idx_points = [(month_to_index(p["month"]), p) for p in curve]

    out = {idx: p for idx, p in idx_points}

    for i in range(len(idx_points) - 1):
        idx0, p0 = idx_points[i]
        idx1, p1 = idx_points[i + 1]
        gap = idx1 - idx0

        if gap <= 1:
            continue

        r0 = float(p0["rate"])
        r1 = float(p1["rate"])

        for k in range(1, gap):
            idxk = idx0 + k
            mk = index_to_month(idxk)
            rk = r0 + (r1 - r0) * (k / gap)

            out[idxk] = {
                "month": mk,
                "rate": round(rk, 4),
                "symbol": "",
                "price": None,
                "volume": 0,
                "name": "synthetic",
                "synthetic": True,
            }

    return [out[i] for i in sorted(out.keys())]


# -------------------------------------------------
# ECB MEETING CURVE (OPTION RAPIDE PRO)
# -------------------------------------------------

def compute_ecb_meeting_curve(monthly_curve: list[dict]) -> list[dict]:

    meeting_dates = [
        "2026-03-19",
        "2026-04-30",
        "2026-06-11",
        "2026-07-23",
        "2026-09-10",
        "2026-10-29",
        "2026-12-17",
    ]

    month_rates = {p["month"]: float(p["rate"]) for p in monthly_curve}
    meeting_curve = []

    for date_str in meeting_dates:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        month_key = f"{dt.year:04d}-{dt.month:02d}"

        if month_key not in month_rates:
            continue

        monthly_rate = month_rates[month_key]
        days_in_month = calendar.monthrange(dt.year, dt.month)[1]

        weight_before = dt.day / days_in_month
        weight_after = 1 - weight_before

        next_month_key = index_to_month(month_to_index(month_key) + 1)
        next_rate = month_rates.get(next_month_key, monthly_rate)

        rate_after = (
            monthly_rate * (1 - weight_before)
            + next_rate * weight_after
        )

        meeting_curve.append({
            "meetingDate": date_str,
            "rateAfter": round(rate_after, 4),
            "month": month_key,
        })

    return meeting_curve


# -------------------------------------------------
# CORE
# -------------------------------------------------

def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def run_bank(bank_code: str, all_rows: list[dict]):

    cfg = load_config(bank_code)
    current_rate = float(cfg["current_rate"]["value"])
    price_formula = cfg.get("futures", {}).get("price_formula", "100_minus_rate")

    filtered = filter_rows_for_bank(all_rows, bank_code)

    if not filtered:
        curve = []
        meetings_curve = []
    else:
        picked = pick_one_per_month_max_volume(filtered)
        curve = build_curve(picked, price_formula)
        curve = strip_past_months(curve)

        if bank_code == "ECB":
            curve = densify_monthly_linear(curve)
            meetings_curve = compute_ecb_meeting_curve(curve)
        else:
            meetings_curve = []

    write_json(OUT_DIR / f"{bank_code.lower()}_implied_curve.json", curve)
    write_json(OUT_DIR / f"{bank_code.lower()}_implied_meetings.json", meetings_curve)


def main():

    if not CSV_PATH.exists():
        raise FileNotFoundError("CSV not found")

    all_rows = load_csv_rows(CSV_PATH)

    for code in ["FED", "ECB", "BOE"]:
        run_bank(code, all_rows)


if __name__ == "__main__":
    main()
