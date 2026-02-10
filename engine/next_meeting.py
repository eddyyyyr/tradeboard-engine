# engine/next_meeting.py

from __future__ import annotations

from typing import Any, Dict, List, Tuple


def _step_from_increment(increment_bp: int) -> float:
    # 25 bps -> 0.25 (%)
    return float(increment_bp) / 100.0


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _floor_to_step(x: float, step: float) -> float:
    # ex: x=3.37 step=0.25 -> 3.25
    return (int(x / step)) * step


def compute_distribution_from_expected(
    expected_rate: float,
    increment_bp: int,
    min_rate: float,
    max_rate: float,
) -> Dict[float, float]:
    """
    Distribution la plus simple + robuste:
    on projette l'expected sur la grille (0.25%, 0.50%, ...)
    et on répartit la proba entre les 2 niveaux adjacents (linéaire).

    Exemple:
      expected=3.37, step=0.25 -> entre 3.25 et 3.50
      p(3.50)= (3.37-3.25)/0.25 = 0.48
      p(3.25)= 0.52
    """
    step = _step_from_increment(increment_bp)
    if step <= 0:
        return {expected_rate: 1.0}

    expected_rate = _clamp(float(expected_rate), float(min_rate), float(max_rate))

    lo = _floor_to_step(expected_rate, step)
    hi = lo + step

    # si on dépasse max_rate
    if hi > max_rate + 1e-12:
        hi = lo

    # si expected tombe pile sur un niveau
    if abs(expected_rate - lo) < 1e-12 or hi == lo:
        return {round(lo, 6): 1.0}

    p_hi = (expected_rate - lo) / step
    p_lo = 1.0 - p_hi

    return {
        round(lo, 6): round(p_lo, 6),
        round(hi, 6): round(p_hi, 6),
    }


def probs_cut_hold_hike(
    dist: Dict[float, float],
    current_rate: float,
    increment_bp: int,
) -> Dict[str, float]:
    """
    Agrège une distribution de taux en 3 buckets:
    - Cut  : taux < current
    - Hold : taux == current (sur la grille)
    - Hike : taux > current
    """
    step = _step_from_increment(increment_bp)
    # On aligne current sur la grille (si jamais il est "bizarre")
    cur = round(_floor_to_step(float(current_rate) + 1e-12, step), 6)

    p_cut = 0.0
    p_hold = 0.0
    p_hike = 0.0

    for level, p in dist.items():
        if level < cur - 1e-12:
            p_cut += p
        elif level > cur + 1e-12:
            p_hike += p
        else:
            p_hold += p

    # arrondis UI
    return {
        "cut": round(p_cut, 6),
        "hold": round(p_hold, 6),
        "hike": round(p_hike, 6),
    }


def top_two_scenarios(dist: Dict[float, float]) -> Tuple[Dict[str, Any] | None, Dict[str, Any] | None]:
    """
    Renvoie 2 scénarios: le niveau le plus probable + le second.
    """
    if not dist:
        return None, None

    items = sorted(dist.items(), key=lambda kv: kv[1], reverse=True)
    s1 = {"rate": items[0][0], "prob": round(items[0][1], 6)}
    s2 = {"rate": items[1][0], "prob": round(items[1][1], 6)} if len(items) > 1 else None
    return s1, s2


def build_next_meeting_summary(
    meetings_curve: List[Dict[str, Any]],
    cfg: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Prend la courbe 'par réunion' (output de meeting_expected.py)
    et construit un JSON ultra simple pour la PROCHAINE réunion.
    """
    if not meetings_curve:
        return {}

    next_pt = meetings_curve[0]

    meeting_date = next_pt.get("meetingDate")
    month = next_pt.get("month")

    current_rate = float(cfg["current_rate"]["value"])
    increment_bp = int(cfg["current_rate"].get("increment_bp", 25))
    min_rate = float(cfg["current_rate"].get("min_rate", 0.0))
    max_rate = float(cfg["current_rate"].get("max_rate", 10.0))

    # On préfère rateRaw si dispo (plus précis)
    expected_after_raw = next_pt.get("rateRaw")
    if expected_after_raw is None:
        expected_after_raw = next_pt.get("rateAfter")
    expected_after_raw = float(expected_after_raw)

    # expected move vs current rate (bps)
    expected_move_bps = (expected_after_raw - current_rate) * 100.0

    dist = compute_distribution_from_expected(
        expected_rate=expected_after_raw,
        increment_bp=increment_bp,
        min_rate=min_rate,
        max_rate=max_rate,
    )

    probs = probs_cut_hold_hike(dist, current_rate=current_rate, increment_bp=increment_bp)
    s1, s2 = top_two_scenarios(dist)

    return {
        "meetingDate": meeting_date,
        "month": month,
        "currentRate": round(current_rate, 6),
        "expectedRateAfterRaw": round(expected_after_raw, 6),
        "expectedMoveBps": round(expected_move_bps, 2),
        "distribution": dist,   # utile debug/UI
        "probabilities": probs, # cut/hold/hike
        "mainScenario": s1,
        "altScenario": s2,
    }
