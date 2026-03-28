"""
Odds Movement Predictions - Falcon-style odds-based predictions
Extracts directional predictions from bookmaker line movements.

This analyzes HOW odds change (opening → closing) across multiple bookmakers
to produce predictions in the same format as other analysis sources.

This is an ADDITIONAL analysis source - it does NOT replace existing analyses.
"""
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def analyze_odds_movement_predictions(odds_data: Dict) -> Dict:
    """
    Analyze odds movements to produce predictions compatible with final_predictions format.

    Falcon approach:
    - Count how many bookmakers raised/lowered goal lines → Over/Under signal
    - Count AH movement direction → MS signal
    - HT odds movement → HT predictions

    Args:
        odds_data: Dict with 'odds_comparison' and 'first_half_odds' keys

    Returns:
        {
            "odds_movement_predictions": {
                "1x2": {home, draw, away},
                "goal_lines": {over_2_5, under_2_5, over_3_5, under_3_5},
                "btts": {yes, no},
                "ht_1x2": {home, draw, away},
                "ht_goals": {over_0_5, under_0_5},
                "confidence": float,
                "signals": {...}
            }
        }
    """
    try:
        odds_comparison = odds_data.get("odds_comparison", [])
        first_half_odds = odds_data.get("first_half_odds", {})

        if isinstance(first_half_odds, dict) and "first_half_odds" in first_half_odds:
            ht_odds = first_half_odds["first_half_odds"]
        elif isinstance(first_half_odds, list):
            ht_odds = first_half_odds
        else:
            ht_odds = []

        if not odds_comparison:
            return {}

        # 1. Goal line movement analysis (Over/Under signal)
        gl_signal = _analyze_goal_line_movement(odds_comparison)

        # 2. Asian Handicap movement (MS signal)
        ah_signal = _analyze_ah_movement(odds_comparison)

        # 3. 1x2 odds movement
        ms_signal = _analyze_1x2_movement(odds_comparison)

        # 4. HT odds movement
        ht_signal = _analyze_ht_movement(ht_odds) if ht_odds else None

        # Build predictions
        predictions = {}

        # 1x2 from AH + 1x2 movements combined
        predictions["1x2"] = _build_ms_prediction(ah_signal, ms_signal)

        # Goal lines from GL movement
        predictions["goal_lines"] = _build_goal_prediction(gl_signal)

        # BTTS from goal line + both teams' expected scoring
        predictions["btts"] = _build_btts_prediction(gl_signal, ah_signal)

        # HT predictions
        if ht_signal:
            predictions["ht_1x2"] = _build_ht_ms_prediction(ht_signal)
            predictions["ht_goals"] = _build_ht_goal_prediction(ht_signal)

        # Confidence based on signal strength
        signal_count = sum(1 for s in [gl_signal, ah_signal, ms_signal, ht_signal] if s)
        predictions["confidence"] = min(85, 50 + signal_count * 10)

        # Raw signals for debugging
        predictions["signals"] = {
            "goal_line": gl_signal,
            "asian_handicap": ah_signal,
            "match_result": ms_signal,
            "half_time": ht_signal,
        }

        return {"odds_movement_predictions": predictions}

    except Exception as e:
        logger.error(f"Odds movement analysis error: {e}")
        return {}


def _analyze_goal_line_movement(odds_comparison: List[Dict]) -> Optional[Dict]:
    """
    Count how many bookmakers raised/lowered the goal line.
    Falcon counts this across 10 bookmakers.
    """
    raised = 0
    lowered = 0
    total = 0
    opening_lines = []
    closing_lines = []

    for company in odds_comparison:
        ou = company.get("over_under", {})
        first = ou.get("first_odds", {})
        pre = ou.get("pre_match_odds", {})

        first_line = first.get("line")
        pre_line = pre.get("line")

        if first_line is not None and pre_line is not None:
            try:
                fl = float(first_line)
                pl = float(pre_line)
                total += 1
                opening_lines.append(fl)
                closing_lines.append(pl)

                if pl > fl + 0.05:
                    raised += 1
                elif pl < fl - 0.05:
                    lowered += 1
            except (ValueError, TypeError):
                continue

    if total < 3:
        return None

    avg_opening = sum(opening_lines) / len(opening_lines)
    avg_closing = sum(closing_lines) / len(closing_lines)
    direction = avg_closing - avg_opening

    return {
        "total": total,
        "raised": raised,
        "lowered": lowered,
        "avg_opening": round(avg_opening, 2),
        "avg_closing": round(avg_closing, 2),
        "direction": round(direction, 3),
        "signal": "over" if raised > lowered else "under" if lowered > raised else "neutral",
        "strength": abs(raised - lowered) / total,
    }


def _analyze_ah_movement(odds_comparison: List[Dict]) -> Optional[Dict]:
    """
    Asian Handicap movement: if line moves towards home (more negative),
    home is getting stronger. If towards away (more positive), away is stronger.

    Falcon: ev > 6 → home signal, dep > 6 → away signal
    """
    home_count = 0
    away_count = 0
    total = 0
    opening_lines = []
    closing_lines = []

    for company in odds_comparison:
        ah = company.get("asian_handicap", {})
        first = ah.get("first_odds", {})
        pre = ah.get("pre_match_odds", {})

        first_line = first.get("line")
        pre_line = pre.get("line")

        if first_line is not None and pre_line is not None:
            try:
                fl = float(first_line)
                pl = float(pre_line)
                total += 1
                opening_lines.append(fl)
                closing_lines.append(pl)

                # More negative = home stronger, more positive = away stronger
                if pl > fl + 0.05:
                    home_count += 1  # Line went up = home getting more handicap = home stronger
                elif pl < fl - 0.05:
                    away_count += 1
            except (ValueError, TypeError):
                continue

    if total < 3:
        return None

    avg_opening = sum(opening_lines) / len(opening_lines)
    avg_closing = sum(closing_lines) / len(closing_lines)

    return {
        "total": total,
        "home_moves": home_count,
        "away_moves": away_count,
        "avg_opening": round(avg_opening, 3),
        "avg_closing": round(avg_closing, 3),
        "signal": "home" if home_count > away_count else "away" if away_count > home_count else "neutral",
        "strength": abs(home_count - away_count) / total,
    }


def _analyze_1x2_movement(odds_comparison: List[Dict]) -> Optional[Dict]:
    """
    Track 1x2 odds movement direction.
    Dropping home odds = money on home = home confidence.
    """
    home_drops = 0
    away_drops = 0
    draw_drops = 0
    total = 0

    for company in odds_comparison:
        eur = company.get("european_odds", {})
        first = eur.get("first_odds", {})
        pre = eur.get("pre_match_odds", {})

        if not first or not pre:
            continue

        try:
            f_home = float(first.get("home", 0))
            f_draw = float(first.get("draw", 0))
            f_away = float(first.get("away", 0))
            p_home = float(pre.get("home", 0))
            p_draw = float(pre.get("draw", 0))
            p_away = float(pre.get("away", 0))

            if f_home <= 1.01 or f_draw <= 1.01 or f_away <= 1.01:
                continue

            total += 1
            # Dropping odds = more money on that outcome
            if p_home < f_home * 0.95:
                home_drops += 1
            if p_away < f_away * 0.95:
                away_drops += 1
            if p_draw < f_draw * 0.95:
                draw_drops += 1
        except (ValueError, TypeError):
            continue

    if total < 3:
        return None

    return {
        "total": total,
        "home_drops": home_drops,
        "away_drops": away_drops,
        "draw_drops": draw_drops,
        "signal": (
            "home" if home_drops > away_drops and home_drops > draw_drops
            else "away" if away_drops > home_drops and away_drops > draw_drops
            else "draw" if draw_drops > home_drops and draw_drops > away_drops
            else "neutral"
        ),
    }


def _analyze_ht_movement(ht_odds: list) -> Optional[Dict]:
    """Analyze half-time odds movement."""
    gl_raised = 0
    gl_lowered = 0
    home_signal = 0
    away_signal = 0
    total = 0

    for company in ht_odds:
        ou = company.get("over_under", {})
        first = ou.get("first_odds", {})
        pre = ou.get("pre_match_odds", {})

        if first and pre:
            try:
                fl = float(first.get("line", 0))
                pl = float(pre.get("line", 0))
                total += 1
                if pl > fl + 0.05:
                    gl_raised += 1
                elif pl < fl - 0.05:
                    gl_lowered += 1
            except (ValueError, TypeError):
                pass

        # HT 1x2
        eur = company.get("european_odds", {})
        f1x2 = eur.get("first_odds", {})
        p1x2 = eur.get("pre_match_odds", {})
        if f1x2 and p1x2:
            try:
                fh = float(f1x2.get("home", 0))
                ph = float(p1x2.get("home", 0))
                fa = float(f1x2.get("away", 0))
                pa = float(p1x2.get("away", 0))
                if fh > 1.01 and ph < fh * 0.95:
                    home_signal += 1
                if fa > 1.01 and pa < fa * 0.95:
                    away_signal += 1
            except (ValueError, TypeError):
                pass

    if total < 2:
        return None

    return {
        "gl_raised": gl_raised,
        "gl_lowered": gl_lowered,
        "home_signal": home_signal,
        "away_signal": away_signal,
        "total": total,
        "goal_signal": "over" if gl_raised > gl_lowered else "under" if gl_lowered > gl_raised else "neutral",
    }


# =============================================================================
# Prediction Builders (convert signals to percentages)
# =============================================================================

def _build_ms_prediction(ah: Optional[Dict], ms: Optional[Dict]) -> Dict:
    """Build 1x2 prediction from AH and 1x2 movement signals."""
    base = {"home": 33.3, "draw": 33.3, "away": 33.3}

    if ah and ah["signal"] != "neutral":
        strength = ah["strength"]
        bonus = min(20, strength * 30)  # max 20% shift
        if ah["signal"] == "home":
            base["home"] += bonus
            base["away"] -= bonus * 0.6
            base["draw"] -= bonus * 0.4
        else:
            base["away"] += bonus
            base["home"] -= bonus * 0.6
            base["draw"] -= bonus * 0.4

    if ms and ms["signal"] != "neutral":
        shift = 8
        if ms["signal"] == "home":
            base["home"] += shift
            base["away"] -= shift * 0.6
            base["draw"] -= shift * 0.4
        elif ms["signal"] == "away":
            base["away"] += shift
            base["home"] -= shift * 0.6
            base["draw"] -= shift * 0.4
        else:
            base["draw"] += shift
            base["home"] -= shift * 0.5
            base["away"] -= shift * 0.5

    # Clamp and normalize
    for k in base:
        base[k] = max(5, base[k])
    total = sum(base.values())
    return {k: round(v / total * 100, 1) for k, v in base.items()}


def _build_goal_prediction(gl: Optional[Dict]) -> Dict:
    """Build goal line prediction from GL movement."""
    if not gl:
        return {"over_2_5": 50, "under_2_5": 50, "over_3_5": 30, "under_3_5": 70}

    avg_line = gl["avg_closing"]
    direction = gl["direction"]
    strength = gl["strength"]

    # Base from closing line
    if avg_line >= 3.0:
        over25_base = 70
    elif avg_line >= 2.75:
        over25_base = 60
    elif avg_line >= 2.5:
        over25_base = 50
    elif avg_line >= 2.25:
        over25_base = 40
    else:
        over25_base = 30

    # Adjust by direction
    if direction > 0.1:
        over25_base += min(10, strength * 15)
    elif direction < -0.1:
        over25_base -= min(10, strength * 15)

    over25_base = max(15, min(85, over25_base))

    over35_base = max(10, over25_base - 25)

    return {
        "over_1_5": round(min(95, over25_base + 20), 1),
        "under_1_5": round(max(5, 100 - over25_base - 20), 1),
        "over_2_5": round(over25_base, 1),
        "under_2_5": round(100 - over25_base, 1),
        "over_3_5": round(over35_base, 1),
        "under_3_5": round(100 - over35_base, 1),
    }


def _build_btts_prediction(gl: Optional[Dict], ah: Optional[Dict]) -> Dict:
    """Build BTTS prediction from goal line and AH signals."""
    btts_base = 50.0

    if gl:
        if gl["avg_closing"] >= 2.75:
            btts_base += 10
        elif gl["avg_closing"] < 2.25:
            btts_base -= 10

    if ah:
        # Close AH = competitive match = more likely BTTS
        if abs(ah["avg_closing"]) < 0.5:
            btts_base += 5
        elif abs(ah["avg_closing"]) > 1.5:
            btts_base -= 5

    btts_base = max(20, min(80, btts_base))
    return {"yes": round(btts_base, 1), "no": round(100 - btts_base, 1)}


def _build_ht_ms_prediction(ht: Optional[Dict]) -> Dict:
    """Build HT 1x2 from HT movement."""
    base = {"home": 30, "draw": 40, "away": 30}  # HT draw is more common

    if ht:
        if ht["home_signal"] > ht["away_signal"]:
            base["home"] += 8
            base["draw"] -= 4
            base["away"] -= 4
        elif ht["away_signal"] > ht["home_signal"]:
            base["away"] += 8
            base["draw"] -= 4
            base["home"] -= 4

    total = sum(base.values())
    return {k: round(v / total * 100, 1) for k, v in base.items()}


def _build_ht_goal_prediction(ht: Optional[Dict]) -> Dict:
    """Build HT goals from HT GL movement."""
    ht_over = 55.0  # Default: slightly over
    if ht:
        if ht["goal_signal"] == "over":
            ht_over += 10
        elif ht["goal_signal"] == "under":
            ht_over -= 10

    ht_over = max(25, min(80, ht_over))
    return {
        "over_0_5": round(ht_over, 1),
        "under_0_5": round(100 - ht_over, 1),
    }
