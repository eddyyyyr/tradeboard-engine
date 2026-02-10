# engine/meeting_expected.py

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date
import calendar
from typing import List, Dict, Any


# ============================================================
# 📌 Modèle : 1 point = 1 réunion (comme Financial Source)
# ============================================================

@dataclass(frozen=True)
class MeetingPoint:
    meetingDate: str      # "YYYY-MM-DD"
    month: str            # "YYYY-MM"

    # ✅ Taux en POURCENTAGE
    rateAfter: float      # ex: 3.44
    rateRaw: float        # ex: 3.4375 (non arrondi)

    # ✅ Move en BASIS POINTS (pour l’UI / expected move)
    moveAfterBps: float   # ex: -31.0
    moveRawBps: float     # ex: -30.8

    # Pondération temporelle
    weightBefore: float
    weightAfter: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ============================================================
# Utils dates
# ============================================================

def _days_in_month(y: int, m: int) -> int:
    return calendar.monthrange(y, m)[1]


def _ym_from_date_str(d: str) -> str:
    # "YYYY-MM-DD" -> "YYYY-MM"
    return d[:7]


def _parse_ym(ym: str) -> tuple[int, int]:
    return int(ym[:4]), int(ym[5:7])


def _parse_date(d: str) -> date:
    return date(int(d[:4]), int(d[5:7]), int(d[8:10]))


def _round_to_increment(rate: float, increment_bp: int) -> float:
    """
    Arrondit un taux (%) à l’incrément officiel (ex: 25 bps = 0.25%)
    """
    step = increment_bp / 100.0
    if step <= 0:
        return rate
    return round(round(rate / step) * step, 6)


def _next_month_ym(ym: str) -> str | None:
    """
    "2026-12" -> "2027-01"
    """
    try:
        y, m = _parse_ym(ym)
        if m == 12:
            return f"{y+1:04d}-01"
        return f"{y:04d}-{m+1:02d}"
    except Exception:
        return None


# ============================================================
# 🧠 Cœur du moteur "Expected AFTER meeting"
# ============================================================

def compute_after_meeting_curve(
    monthly_curve: List[Dict[str, Any]],
    meeting_dates: List[str],
    current_rate: float,
    increment_bp: int = 25,
) -> List[Dict[str, Any]]:
    """
    Transforme une courbe mensuelle (contrats futures)
    en courbe "par réunion" (taux APRÈS chaque meeting).

    Hypothèse standard :
      R_month = w_before * R_before + w_after * R_after
      => R_after = (R_month - w_before * R_before) / w_after

    ⚠️ Fix "meetings late month":
    Si la réunion est trop tard dans le mois (peu de jours après),
    la formule explose (division par un petit w_after).
    Dans ce cas, on utilise le mois suivant comme proxy.
    """

    # Index mois -> taux mensuel (%)
    month_to_rate: Dict[str, float] = {}
    for p in monthly_curve:
        m = p.get("month")
        r = p.get("rate")
        if isinstance(m, str) and isinstance(r, (int, float)):
            month_to_rate[m] = float(r)

    # Meetings triées chronologiquement
    meeting_dates_sorted = sorted(
        [d for d in meeting_dates if isinstance(d, str) and len(d) >= 10]
    )

    out: List[Dict[str, Any]] = []

    # Taux "avant réunion" = dernier taux après réunion connue
    prev_after_rate = float(current_rate)

    # Seuils de stabilité
    MIN_DAYS_AFTER = 5          # si < 5 jours après meeting dans le mois => proxy mois suivant
    MAX_ABS_MOVE_BPS = 300.0    # si move > 300 bps => proxy mois suivant (ou clamp)

    for d in meeting_dates_sorted:
        ym = _ym_from_date_str(d)
        if ym not in month_to_rate:
            continue

        meeting_dt = _parse_date(d)
        y, m = _parse_ym(ym)
        dim = _days_in_month(y, m)

        # Pondérations temporelles
        days_before = meeting_dt.day - 1
        days_after = dim - days_before
        w_before = days_before / dim
        w_after = 1.0 - w_before

        r_month = month_to_rate[ym]

        # 1) Calcul standard
        if w_after <= 1e-9:
            r_after_raw = r_month
        else:
            r_after_raw = (r_month - (w_before * prev_after_rate)) / w_after

        # 2) Si meeting trop tard OU move absurde -> proxy mois suivant
        use_proxy = False
        if days_after < MIN_DAYS_AFTER:
            use_proxy = True

        move_raw_bps_tmp = (r_after_raw - prev_after_rate) * 100.0
        if abs(move_raw_bps_tmp) > MAX_ABS_MOVE_BPS:
            use_proxy = True

        if use_proxy:
            ym_next = _next_month_ym(ym)
            if ym_next and ym_next in month_to_rate:
                r_after_raw = float(month_to_rate[ym_next])
            else:
                # fallback soft : on évite de partir en délire
                # on clamp autour du prev rate
                r_after_raw = max(min(r_after_raw, prev_after_rate + 3.0), prev_after_rate - 3.0)

        # Arrondi à l’incrément officiel
        r_after = _round_to_increment(r_after_raw, increment_bp)

        # 🔹 MOVE en bps (diff vs taux précédent)
        move_raw_bps = (r_after_raw - prev_after_rate) * 100.0
        move_after_bps = (r_after - prev_after_rate) * 100.0

        mp = MeetingPoint(
            meetingDate=d,
            month=ym,
            rateAfter=round(float(r_after), 6),
            rateRaw=round(float(r_after_raw), 6),
            moveAfterBps=round(float(move_after_bps), 2),
            moveRawBps=round(float(move_raw_bps), 4),
            weightBefore=round(float(w_before), 6),
            weightAfter=round(float(w_after), 6),
        )

        out.append(mp.to_dict())

        # Le taux "après" devient le taux "avant" du meeting suivant
        prev_after_rate = float(r_after)

    return out
