# engine/meeting_expected.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import calendar
from typing import List, Dict, Any


@dataclass(frozen=True)
class MeetingPoint:
    meetingDate: str      # "YYYY-MM-DD"
    month: str            # "YYYY-MM"
    rateAfter: float      # taux "après réunion"
    rateRaw: float        # taux brut (non arrondi)
    weightBefore: float   # poids jours avant réunion
    weightAfter: float    # poids jours après réunion


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
    # increment_bp=25 -> 0.25
    step = increment_bp / 100.0
    if step <= 0:
        return rate
    return round(round(rate / step) * step, 6)


def compute_after_meeting_curve(
    monthly_curve: List[Dict[str, Any]],
    meeting_dates: List[str],
    current_rate: float,
    increment_bp: int = 25,
) -> List[Dict[str, Any]]:
    """
    Convertit une courbe mensuelle (1 point par mois) en courbe "par réunion"
    (expected rate AFTER each meeting), via pondération days-before/days-after.

    Hypothèse standard:
      R_month = w_before * R_before + w_after * R_after
      => R_after = (R_month - w_before*R_before) / w_after
    """
    # Index "YYYY-MM" -> taux mensuel
    month_to_rate: dict[str, float] = {}
    for p in monthly_curve:
        m = p.get("month")
        r = p.get("rate")
        if isinstance(m, str) and isinstance(r, (int, float)):
            month_to_rate[m] = float(r)

    # Meetings triées
    meeting_dates_sorted = sorted([d for d in meeting_dates if isinstance(d, str) and len(d) >= 10])

    out: List[Dict[str, Any]] = []
    prev_after = float(current_rate)

    for d in meeting_dates_sorted:
        ym = _ym_from_date_str(d)
        if ym not in month_to_rate:
            # pas de contrat mensuel pour ce mois -> on skip (on gérera fallback après)
            continue

        meeting_dt = _parse_date(d)
        y, m = _parse_ym(ym)
        dim = _days_in_month(y, m)

        # jours avant la réunion DANS le mois (si meeting le 1 -> 0)
        days_before = meeting_dt.day - 1
        w_before = days_before / dim
        w_after = 1.0 - w_before

        r_month = month_to_rate[ym]

        # Évite division par ~0 si meeting le dernier jour (rare)
        if w_after <= 1e-9:
            r_after_raw = r_month
        else:
            r_after_raw = (r_month - (w_before * prev_after)) / w_after

        r_after = _round_to_increment(r_after_raw, increment_bp)

        out.append(
            {
                "meetingDate": d,
                "month": ym,
                "rateAfter": round(r_after, 6),
                "rateRaw": round(float(r_after_raw), 6),
                "weightBefore": round(w_before, 6),
                "weightAfter": round(w_after, 6),
            }
        )

        prev_after = float(r_after)

    return out
