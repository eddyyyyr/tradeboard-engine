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
    moveAfterBps: float  # ex: -31.0
    moveRawBps: float    # ex: -30.8

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

    Hypothèse standard (CME / FedWatch-like) :
      R_month = w_before * R_before + w_after * R_after
      => R_after = (R_month - w_before * R_before) / w_after
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

    for d in meeting_dates_sorted:
        ym = _ym_from_date_str(d)
        if ym not in month_to_rate:
            # Pas de contrat mensuel correspondant → on ignore
            continue

        meeting_dt = _parse_date(d)
        y, m = _parse_ym(ym)
        dim = _days_in_month(y, m)

        # Pondérations temporelles
        days_before = meeting_dt.day - 1
        w_before = days_before / dim
        w_after = 1.0 - w_before

        r_month = month_to_rate[ym]

        # Sécurité : meeting le dernier jour du mois
        if w_after <= 1e-9:
            r_after_raw = r_month
        else:
            r_after_raw = (r_month - (w_before * prev_after_rate)) / w_after

        # Arrondi à l’incrément officiel
        r_after = _round_to_increment(r_after_raw, increment_bp)

        # 🔹 MOVE en bps (diff vs taux précédent)
        move_raw_bps = (r_after_raw - prev_after_rate) * 100.0
        move_after_bps = (r_after - prev_after_rate) * 100.0

        mp = MeetingPoint(
            meetingDate=d,
            month=ym,
            rateAfter=round(r_after, 6),
            rateRaw=round(float(r_after_raw), 6),
            moveAfterBps=round(move_after_bps, 2),
            moveRawBps=round(move_raw_bps, 4),
            weightBefore=round(w_before, 6),
            weightAfter=round(w_after, 6),
        )

        out.append(mp.to_dict())

        # Le taux "après" devient le taux "avant" du meeting suivant
        prev_after_rate = float(r_after)

    return out
