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

# ✅ Filtrage par banque via la colonne "Name" du CSV (fallback)
NAME_FILTERS = {
    "FED": ["30-Day Fed Funds"],
    "BOE": ["3-Month SONIA"],
    # ECB : on ne s'en sert plus si SYMBOL_PREFIX_FILTERS["ECB"] est défini
    "ECB": ["Euribor", "EURIBOR", "€STR", "ESTR", "Euribor"],
}

# ✅ Filtre STRICT par préfixe de "Symbol" (recommandé pour éviter les mixes)
# Euribor 3M (ICE) sur Barchart apparaît souvent en "IMH26, IMM26, IMU26, IMZ26..."
SYMBOL_PREFIX_FILTERS = {
    "ECB": ["IM"],  # ✅ Euribor only
    # Si tu veux plus tard :
    # "FED": ["ZQ"],
    # "BOE": ["J8"],
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


def now_month_utc() -> str:
    """Retourne le mois courant en UTC au format 'YYYY-MM'."""
    dt = datetime.now(timezone.utc)
    return f"{dt.year:04d}-{dt.month:02d}"


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
            symbol = (r.get("Symbol") or "").strip().upper()
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
    """
    ✅ Priorité 1 : filtre strict par préfixe (si défini)
    ✅ Sinon : fallback par Name contains (ancien système)
    """
    prefixes = SYMBOL_PREFIX_FILTERS.get(bank_code, []) or []
    if prefixes:
        prefixes_u = [p.upper() for p in prefixes]
        filtered = []
        for r in rows:
            sym = (r.get("symbol") or "").upper()
            if any(sym.startswith(p) for p in prefixes_u):
                filtered.append(r)
        return filtered

    filters = NAME_FILTERS.get(bank_code, []) or []
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
                "month": r["month"],      # "2026-06"
                "rate": round(rate, 4),   # 3.51
                "symbol": r["symbol"],    # "ZQM26"
                "price": r["price"],      # 96.49
                "volume": r["volume"],    # 4308
                "name": r.get("name", ""),  # utile debug
            }
        )
    return curve


def strip_past_months(curve: list[dict]) -> list[dict]:
    """
    Supprime les mois passés (strictement < mois courant UTC).
    """
    cutoff = now_month_utc()
    return [p for p in curve if (p.get("month") or "") >= cutoff]


def meeting_months_from_config(cfg: dict) -> tuple[set[str], dict[str, str]]:
    """
    Lit les dates de réunions depuis config si présentes.

    Format attendu :
    meetings:
      dates:
        - "2026-02-05"
        - "2026-03-18"
    """
    meetings = cfg.get("meetings", {})
    if not isinstance(meetings, dict):
        return set(), {}

    # ⚠️ Dans tes configs, tu utilises parfois "dates" ou "days"
    dates = meetings.get("dates") or meetings.get("days") or []
    months: set[str] = set()
    month_to_date: dict[str, str] = {}

    for d in dates:
        if not isinstance(d, str) or len(d) < 7:
            continue
        try:
            y = int(d[0:4])
            m = int(d[5:7])
            month = f"{y:04d}-{m:02d}"
        except Exception:
            continue

        months.add(month)
        if month not in month_to_date:
            month_to_date[month] = d

    return months, month_to_date


def filter_curve_to_meetings(
    curve: list[dict],
    meeting_months: set[str],
    month_to_date: dict[str, str],
    current_rate: float,
    increment_bp: int,
) -> list[dict]:
    """
    OPTION B (precise): transforme la courbe mensuelle en points "après réunion"
    via pondération jours avant/après.
    """
    if not meeting_months:
        return []

    meeting_dates = sorted(month_to_date.values())

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
    out_next_path = OUT_DIR / f"{code_lower}_next_meeting.json"

    print(f"\n==============================")
    print(f"✅ {bank_code} loaded")
    print(f"Bank: {bank_name}")
    print(f"Current rate: {current_rate}")
    print(f"CSV: {CSV_PATH}")
    print(f"Price formula: {price_formula}")
    print(f"Symbol prefix filters: {SYMBOL_PREFIX_FILTERS.get(bank_code)}")
    print(f"Name filters (fallback): {NAME_FILTERS.get(bank_code)}")
    print(f"Increment bp: {increment_bp}")

    filtered = filter_rows_for_bank(all_rows, bank_code)
    print(f"✅ Filtered rows: {len(filtered)}")

    if len(filtered) == 0:
        print(f"⚠️ No rows matched for {bank_code}. JSON will be empty.")
        curve: list[dict] = []
        meetings_curve: list[dict] = []
        next_meeting: dict = {}
    else:
        picked = pick_one_per_month_max_volume(filtered)
        curve = build_curve(picked, price_formula)

        # 1) supprime les dates passées
        curve = strip_past_months(curve)

        # 2) OPTION B: points après réunion (pondération)
        meeting_months, month_to_date = meeting_months_from_config(cfg)
        meetings_curve = filter_curve_to_meetings(
            curve=curve,
            meeting_months=meeting_months,
            month_to_date=month_to_date,
            current_rate=current_rate,
            increment_bp=increment_bp,
        )

        # 3) petit résumé "next meeting" (si dispo)
        next_meeting = {}
        if meetings_curve:
            first = meetings_curve[0]
            # Ce JSON est surtout pour l'UI Base44
            # expectedMoveBps : utilise moveRawBps (plus précis)
            dist = {}
            # distribution simple sur 2 niveaux (rateAfter et rateAfter - increment)
            # (tu peux raffiner plus tard)
            rate_main = float(first.get("rateAfter", current_rate))
            dist[f"{rate_main:.2f}"] = 1.0

            probs = {"cut": 0.0, "hold": 0.0, "hike": 0.0}
            move_raw = float(first.get("moveRawBps", 0.0))
            if move_raw < -1e-9:
                probs["cut"] = 1.0
            elif move_raw > 1e-9:
                probs["hike"] = 1.0
            else:
                probs["hold"] = 1.0

            next_meeting = {
                "meetingDate": first.get("meetingDate"),
                "month": first.get("month"),
                "currentRate": current_rate,
                "expectedRateAfterRaw": first.get("rateRaw"),
                "expectedMoveBps": round(move_raw, 2),
                "distribution": dist,
                "probabilities": probs,
                "mainScenario": {"rate": rate_main, "prob": 1.0},
                "altScenario": None,
            }

    # ✅ Écrit les 3 fichiers
    write_json(out_curve_path, curve)
    write_json(out_meetings_path, meetings_curve)
    write_json(out_next_path, next_meeting)

    print("\n📈 Monthly curve (future months only):")
    for p in curve[:12]:
        print(
            f"{p['month']} | {p['symbol']} | price={p['price']} | vol={p['volume']} -> {p['rate']} %"
        )
    print(f"\n💾 Wrote JSON: {out_curve_path} ({len(curve)} points)")

    print("\n📅 Meeting curve (Option B):")
    for p in meetings_curve[:12]:
        print(
            f"{p.get('meetingDate')} | rateAfter={p.get('rateAfter')} | moveAfterBps={p.get('moveAfterBps')} | w_after={p.get('weightAfter')}"
        )
    print(f"\n💾 Wrote JSON: {out_meetings_path} ({len(meetings_curve)} points)")

    if next_meeting:
        print("\n🎯 Next meeting summary:")
        print(
            f"date={next_meeting.get('meetingDate')} | expectedMoveBps={next_meeting.get('expectedMoveBps')} | probs={next_meeting.get('probabilities')}"
        )
    print(f"\n💾 Wrote JSON: {out_next_path}")


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
