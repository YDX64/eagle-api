"""
Streak Detector - Falcon-style trend detection from recent matches
Detects strong patterns like 10/10 over 2.5, 10/10 BTTS, 10/10 HT goals.

When a team has a perfect streak, it becomes a very strong signal.

This is an ADDITIONAL analysis source - it does NOT replace existing analyses.
"""
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def detect_streaks(match_data: Dict) -> Dict:
    """
    Detect strong streaks from team recent matches.

    Returns:
        {
            "streak_predictions": {
                "home_streaks": {...},
                "away_streaks": {...},
                "h2h_streaks": {...},
                "signals": {market: {direction, strength, reason}},
                "confidence": float
            }
        }
    """
    try:
        h2h = match_data.get("h2h_details") or {}
        match_info = match_data.get("match_info") or {}
        home_team = match_info.get("home_team_name", "")
        away_team = match_info.get("away_team_name", "")

        if not home_team or not away_team:
            return {}

        home_matches = h2h.get("home_team_previous_matches") or []
        away_matches = h2h.get("away_team_previous_matches") or []
        h2h_matches = h2h.get("head_to_head") or []

        home_streaks = _analyze_team_streaks(home_matches, home_team, limit=10)
        away_streaks = _analyze_team_streaks(away_matches, away_team, limit=10)
        h2h_streaks = _analyze_h2h_streaks(h2h_matches, limit=10)

        # Convert streaks to prediction signals
        signals = _streaks_to_signals(home_streaks, away_streaks, h2h_streaks)

        # Calculate confidence
        strong_signals = sum(1 for s in signals.values() if s.get("strength", 0) >= 0.8)
        confidence = min(85, 50 + strong_signals * 15)

        return {
            "streak_predictions": {
                "home_streaks": home_streaks,
                "away_streaks": away_streaks,
                "h2h_streaks": h2h_streaks,
                "signals": signals,
                "confidence": confidence,
            }
        }

    except Exception as e:
        logger.error(f"Streak detection error: {e}")
        return {}


def _analyze_team_streaks(matches: List[Dict], team_name: str, limit: int = 10) -> Dict:
    """Analyze a team's recent matches for streaks."""
    if len(matches) < 5:
        return {}

    recent = matches[:limit]
    stats = {
        "matches_analyzed": len(recent),
        "over_25": 0,
        "under_25": 0,
        "over_35": 0,
        "btts": 0,
        "no_btts": 0,
        "ht_goals": 0,  # HT had at least 1 goal
        "team_scored": 0,
        "team_clean_sheet": 0,
        "wins": 0,
        "losses": 0,
        "draws": 0,
    }

    for m in recent:
        try:
            hs = int(m.get("home_score", 0))
            aws = int(m.get("away_score", 0))
            total = hs + aws

            # Over/Under
            if total > 2:
                stats["over_25"] += 1
            else:
                stats["under_25"] += 1

            if total > 3:
                stats["over_35"] += 1

            # BTTS
            if hs > 0 and aws > 0:
                stats["btts"] += 1
            else:
                stats["no_btts"] += 1

            # HT goals
            ht_hs = m.get("ht_home_score")
            ht_as = m.get("ht_away_score")
            if ht_hs is not None and ht_as is not None:
                if int(ht_hs) + int(ht_as) > 0:
                    stats["ht_goals"] += 1

            # Team-specific
            is_home = m.get("home_team") == team_name
            team_goals = hs if is_home else aws
            opp_goals = aws if is_home else hs

            if team_goals > 0:
                stats["team_scored"] += 1
            if opp_goals == 0:
                stats["team_clean_sheet"] += 1

            if team_goals > opp_goals:
                stats["wins"] += 1
            elif team_goals < opp_goals:
                stats["losses"] += 1
            else:
                stats["draws"] += 1

        except (ValueError, TypeError):
            continue

    n = stats["matches_analyzed"]
    if n == 0:
        return {}

    # Calculate rates
    stats["over_25_rate"] = round(stats["over_25"] / n, 2)
    stats["btts_rate"] = round(stats["btts"] / n, 2)
    stats["ht_goal_rate"] = round(stats["ht_goals"] / n, 2) if stats.get("ht_goals") else 0
    stats["scoring_rate"] = round(stats["team_scored"] / n, 2)
    stats["win_rate"] = round(stats["wins"] / n, 2)

    return stats


def _analyze_h2h_streaks(matches: List[Dict], limit: int = 10) -> Dict:
    """Analyze head-to-head streak patterns."""
    if len(matches) < 3:
        return {}

    recent = matches[:limit]
    stats = {
        "matches_analyzed": len(recent),
        "over_25": 0,
        "btts": 0,
        "ht_goals": 0,
    }

    for m in recent:
        try:
            hs = int(m.get("home_score", 0))
            aws = int(m.get("away_score", 0))
            total = hs + aws

            if total > 2:
                stats["over_25"] += 1
            if hs > 0 and aws > 0:
                stats["btts"] += 1

            ht_hs = m.get("ht_home_score")
            ht_as = m.get("ht_away_score")
            if ht_hs is not None and ht_as is not None:
                if int(ht_hs) + int(ht_as) > 0:
                    stats["ht_goals"] += 1
        except (ValueError, TypeError):
            continue

    n = stats["matches_analyzed"]
    stats["over_25_rate"] = round(stats["over_25"] / n, 2) if n > 0 else 0
    stats["btts_rate"] = round(stats["btts"] / n, 2) if n > 0 else 0

    return stats


def _streaks_to_signals(
    home: Dict, away: Dict, h2h: Dict
) -> Dict[str, Dict]:
    """
    Convert streak data to directional signals for prediction.
    Strong streaks (>=80% rate) become strong signals.
    """
    signals = {}

    # Over 2.5 signal
    home_over = home.get("over_25_rate", 0.5)
    away_over = away.get("over_25_rate", 0.5)
    avg_over = (home_over + away_over) / 2

    if avg_over >= 0.8:
        signals["over25"] = {
            "direction": "over",
            "strength": avg_over,
            "reason": f"Both teams high over rate: H={home_over}, A={away_over}",
        }
    elif avg_over <= 0.3:
        signals["over25"] = {
            "direction": "under",
            "strength": 1.0 - avg_over,
            "reason": f"Both teams low over rate: H={home_over}, A={away_over}",
        }

    # BTTS signal
    home_btts = home.get("btts_rate", 0.5)
    away_btts = away.get("btts_rate", 0.5)
    avg_btts = (home_btts + away_btts) / 2

    if avg_btts >= 0.75:
        signals["btts"] = {
            "direction": "yes",
            "strength": avg_btts,
            "reason": f"High BTTS rate: H={home_btts}, A={away_btts}",
        }
    elif avg_btts <= 0.3:
        signals["btts"] = {
            "direction": "no",
            "strength": 1.0 - avg_btts,
            "reason": f"Low BTTS rate: H={home_btts}, A={away_btts}",
        }

    # HT goal signal
    home_ht = home.get("ht_goal_rate", 0.5)
    away_ht = away.get("ht_goal_rate", 0.5)
    avg_ht = (home_ht + away_ht) / 2

    if avg_ht >= 0.8:
        signals["ht_over05"] = {
            "direction": "over",
            "strength": avg_ht,
            "reason": f"High HT goal rate: H={home_ht}, A={away_ht}",
        }

    # MS signal from win rates
    home_wr = home.get("win_rate", 0.33)
    away_wr = away.get("win_rate", 0.33)

    if home_wr >= 0.7 and away_wr <= 0.3:
        signals["ms"] = {
            "direction": "home",
            "strength": home_wr,
            "reason": f"Home dominant: WR={home_wr}, Away WR={away_wr}",
        }
    elif away_wr >= 0.7 and home_wr <= 0.3:
        signals["ms"] = {
            "direction": "away",
            "strength": away_wr,
            "reason": f"Away dominant: WR={away_wr}, Home WR={home_wr}",
        }

    # H2H signals (override if strong)
    h2h_over = h2h.get("over_25_rate", 0.5)
    if h2h.get("matches_analyzed", 0) >= 5 and h2h_over >= 0.8:
        signals["h2h_over25"] = {
            "direction": "over",
            "strength": h2h_over,
            "reason": f"H2H history: {int(h2h_over*100)}% over 2.5",
        }

    return signals
