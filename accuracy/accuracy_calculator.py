"""
Accuracy Calculator — compares Eagle predictions with actual match results.

Loads the day's prediction JSON, fetches real match results via
result_resolver, evaluates each prediction market, and stores
per-prediction results + aggregated per-algorithm accuracy in PostgreSQL.

Main entry point:
    calculate_accuracy(target_date: str) -> dict
"""

import json
import logging
import os
import re
import time
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from accuracy.db import execute_many, execute_query
from accuracy.result_resolver import resolve_match_results

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


# ============================================================================
# Prediction file loader
# ============================================================================

def _load_predictions(target_date: str) -> Optional[Dict[str, Any]]:
    """Load Eagle prediction JSON for the given date."""
    path = os.path.join(DATA_DIR, f"eagle_predictions_{target_date}.json")
    if not os.path.exists(path):
        logger.warning("[Accuracy] Prediction file not found: %s", path)
        return None
    try:
        with open(path, "r") as f:
            data = json.load(f)
        match_count = len(data.get("matches", []))
        logger.info("[Accuracy] Loaded %d predictions from %s", match_count, path)
        return data
    except Exception as exc:
        logger.error("[Accuracy] Error loading predictions: %s", exc)
        return None


# ============================================================================
# Market resolution functions
#
# Each function takes:
#   eagle_pick  — the prediction string (e.g. "1", "Ust 2.5", "KG Var")
#   result      — the match result dict from result_resolver
# Returns:
#   True  = prediction correct
#   False = prediction wrong
#   None  = cannot determine (missing data)
# ============================================================================

def _normalise_pick(pick: str) -> str:
    """Lowercase, strip, normalize Turkish chars for comparison."""
    if not pick:
        return ""
    return (
        pick.strip()
        .lower()
        .replace("ü", "u")
        .replace("ö", "o")
        .replace("ı", "i")
        .replace("İ", "i")
        .replace("ş", "s")
        .replace("ç", "c")
    )


def _resolve_ms(eagle_pick: str, result: Dict) -> Optional[bool]:
    """Match Result (1X2)."""
    home = result["home_score"]
    away = result["away_score"]
    pick = _normalise_pick(eagle_pick)

    # Map various pick formats to canonical outcome
    if any(x in pick for x in ["ms1", "1"]) and "2" not in pick:
        return home > away
    if "x" in pick and "1" not in pick and "2" not in pick:
        return home == away
    if any(x in pick for x in ["ms2", "2"]):
        return home < away

    # Fallback: direct comparison
    if pick in ("1",):
        return home > away
    if pick in ("x",):
        return home == away
    if pick in ("2",):
        return home < away

    logger.debug("[Accuracy] Unrecognised MS pick: '%s'", eagle_pick)
    return None


def _resolve_over_under(eagle_pick: str, result: Dict, line: float) -> Optional[bool]:
    """Over/Under for a given line (2.5, 3.5, etc.)."""
    total = result["total_goals"]
    pick = _normalise_pick(eagle_pick)

    if "ust" in pick or "over" in pick:
        return total > line  # Ust 2.5 correct if total >= 3
    if "alt" in pick or "under" in pick:
        return total < line + 1  # Alt 2.5 correct if total <= 2 (i.e. < 3)

    logger.debug("[Accuracy] Unrecognised OU pick: '%s'", eagle_pick)
    return None


def _resolve_over25(eagle_pick: str, result: Dict) -> Optional[bool]:
    return _resolve_over_under(eagle_pick, result, 2.5)


def _resolve_over35(eagle_pick: str, result: Dict) -> Optional[bool]:
    return _resolve_over_under(eagle_pick, result, 3.5)


def _resolve_btts(eagle_pick: str, result: Dict) -> Optional[bool]:
    """Both Teams To Score."""
    home = result["home_score"]
    away = result["away_score"]
    both_scored = home >= 1 and away >= 1
    pick = _normalise_pick(eagle_pick)

    if "var" in pick or "yes" in pick or "evet" in pick:
        return both_scored
    if "yok" in pick or "no" in pick or "hayir" in pick:
        return not both_scored

    logger.debug("[Accuracy] Unrecognised BTTS pick: '%s'", eagle_pick)
    return None


def _resolve_ht_result(eagle_pick: str, result: Dict) -> Optional[bool]:
    """Half-Time Result (1X2)."""
    ht_home = result.get("ht_home_score")
    ht_away = result.get("ht_away_score")
    if ht_home is None or ht_away is None:
        return None

    pick = _normalise_pick(eagle_pick)

    if "1" in pick and "2" not in pick:
        return ht_home > ht_away
    if "x" in pick:
        return ht_home == ht_away
    if "2" in pick and "1" not in pick:
        return ht_home < ht_away

    logger.debug("[Accuracy] Unrecognised HT result pick: '%s'", eagle_pick)
    return None


def _resolve_ht_over05(eagle_pick: str, result: Dict) -> Optional[bool]:
    """Half-Time Over/Under 0.5."""
    ht_home = result.get("ht_home_score")
    ht_away = result.get("ht_away_score")
    if ht_home is None or ht_away is None:
        return None

    ht_total = ht_home + ht_away
    pick = _normalise_pick(eagle_pick)

    if "ust" in pick or "over" in pick:
        return ht_total >= 1
    if "alt" in pick or "under" in pick:
        return ht_total == 0

    logger.debug("[Accuracy] Unrecognised HT OU 0.5 pick: '%s'", eagle_pick)
    return None


def _resolve_corner(eagle_pick: str, result: Dict) -> Optional[bool]:
    """Corner Over/Under with dynamic line."""
    total_corners = result.get("total_corners")
    if total_corners is None:
        return None  # Cannot resolve without corner data

    pick = _normalise_pick(eagle_pick)

    # Extract the line from the pick string
    # Patterns: "korner ust 10.5", "korner alt 9.5", "ust 10.5 korner"
    line_match = re.search(r"(\d+(?:\.\d+)?)", pick)
    if not line_match:
        logger.debug("[Accuracy] No line found in corner pick: '%s'", eagle_pick)
        return None

    line = float(line_match.group(1))

    if "ust" in pick or "over" in pick:
        return total_corners > line
    if "alt" in pick or "under" in pick:
        return total_corners < line

    logger.debug("[Accuracy] Unrecognised corner pick direction: '%s'", eagle_pick)
    return None


def _resolve_card(eagle_pick: str, result: Dict) -> Optional[bool]:
    """Card Over/Under with dynamic line."""
    total_cards = result.get("total_cards")
    if total_cards is None:
        return None  # Cannot resolve without card data

    pick = _normalise_pick(eagle_pick)

    # Patterns: "ust 3.5 kart", "alt 4.5 kart", "3.5 ust kart"
    line_match = re.search(r"(\d+(?:\.\d+)?)", pick)
    if not line_match:
        logger.debug("[Accuracy] No line found in card pick: '%s'", eagle_pick)
        return None

    line = float(line_match.group(1))

    if "ust" in pick or "over" in pick:
        return total_cards > line
    if "alt" in pick or "under" in pick:
        return total_cards < line

    logger.debug("[Accuracy] Unrecognised card pick direction: '%s'", eagle_pick)
    return None


def _resolve_correct_score(eagle_pick: str, result: Dict) -> Optional[bool]:
    """Correct Score — exact score prediction."""
    ft_score = result["ft_score"]  # e.g. "2-1"
    pick = _normalise_pick(eagle_pick)

    # Extract score from pick: "skor 1-0", "1:0", "1-0", "skor 2-1"
    score_match = re.search(r"(\d+)\s*[-:]\s*(\d+)", pick)
    if not score_match:
        logger.debug("[Accuracy] No score found in CS pick: '%s'", eagle_pick)
        return None

    predicted_score = f"{score_match.group(1)}-{score_match.group(2)}"
    return predicted_score == ft_score


def _resolve_handicap(eagle_pick: str, result: Dict) -> Optional[bool]:
    """
    Asian Handicap resolution.

    Pick format from eagle_cron.py: "AH +/-X.X Ev/Dep"
    Examples: "AH -1.0 Ev", "AH +0.5 Dep", "AH -0.25 Ev"

    Resolution:
        Apply handicap to the picked team's score.
        If picked team "covers" (adjusted score > opponent), the pick wins.
        Quarter lines: half win/loss is treated as correct (conservative).
    """
    home = result["home_score"]
    away = result["away_score"]
    pick_raw = eagle_pick.strip()
    pick = _normalise_pick(pick_raw)

    # Extract handicap line and side
    ah_match = re.search(r"ah\s*([-+]?\d+(?:\.\d+)?)\s*(ev|dep|home|away)", pick)
    if not ah_match:
        # Try alternate format: just "handicap -1.0 ev"
        ah_match = re.search(r"([-+]?\d+(?:\.\d+)?)\s*(ev|dep|home|away)", pick)
    if not ah_match:
        logger.debug("[Accuracy] Cannot parse handicap pick: '%s'", eagle_pick)
        return None

    line = float(ah_match.group(1))
    side = ah_match.group(2)

    # Determine which team the handicap applies to
    if side in ("ev", "home"):
        adjusted_diff = (home + line) - away
    else:  # dep / away
        adjusted_diff = (away + line) - home

    # Standard AH resolution
    if adjusted_diff > 0:
        return True   # Pick wins
    if adjusted_diff < 0:
        return False  # Pick loses
    # adjusted_diff == 0 means push — treat as correct (conservative)
    return True


def _resolve_first_half(eagle_pick: str, result: Dict) -> Optional[bool]:
    """
    First-half market resolution.

    Picks can be various IY (ilk yari) markets:
      - "IY 1", "IY X", "IY 2" → HT 1X2
      - "IY Ust 0.5", "IY Alt 0.5" → HT over/under 0.5
      - "IY Ust 1.5", "IY Alt 1.5" → HT over/under 1.5
      - "IY KG Var", "IY KG Yok" → HT BTTS
    """
    ht_home = result.get("ht_home_score")
    ht_away = result.get("ht_away_score")
    if ht_home is None or ht_away is None:
        return None

    pick = _normalise_pick(eagle_pick)
    ht_total = ht_home + ht_away

    # IY 1X2
    if "iy" in pick or "ilk" in pick or "first" in pick:
        # Over/under with line
        line_match = re.search(r"(ust|alt|over|under)\s*(\d+(?:\.\d+)?)", pick)
        if line_match:
            direction = line_match.group(1)
            line = float(line_match.group(2))
            if "ust" in direction or "over" in direction:
                return ht_total > line
            else:
                return ht_total < line

        # BTTS
        if "kg" in pick or "btts" in pick:
            both = ht_home >= 1 and ht_away >= 1
            if "var" in pick or "yes" in pick:
                return both
            if "yok" in pick or "no" in pick:
                return not both

        # 1X2
        if "1" in pick and "2" not in pick and not re.search(r"\d\.\d", pick):
            return ht_home > ht_away
        if "x" in pick and "1" not in pick and "2" not in pick:
            return ht_home == ht_away
        if "2" in pick and "1" not in pick:
            return ht_home < ht_away

    logger.debug("[Accuracy] Unrecognised first_half pick: '%s'", eagle_pick)
    return None


def _resolve_second_half(eagle_pick: str, result: Dict) -> Optional[bool]:
    """
    Second-half market resolution.

    Calculate 2nd half scores: FT - HT, then apply similar logic to first_half.
    """
    ht_home = result.get("ht_home_score")
    ht_away = result.get("ht_away_score")
    if ht_home is None or ht_away is None:
        return None

    sh_home = result["home_score"] - ht_home
    sh_away = result["away_score"] - ht_away
    sh_total = sh_home + sh_away

    pick = _normalise_pick(eagle_pick)

    # Over/under with line
    line_match = re.search(r"(ust|alt|over|under)\s*(\d+(?:\.\d+)?)", pick)
    if line_match:
        direction = line_match.group(1)
        line = float(line_match.group(2))
        if "ust" in direction or "over" in direction:
            return sh_total > line
        else:
            return sh_total < line

    # BTTS
    if "kg" in pick or "btts" in pick:
        both = sh_home >= 1 and sh_away >= 1
        if "var" in pick or "yes" in pick:
            return both
        if "yok" in pick or "no" in pick:
            return not both

    # 1X2
    if "1" in pick and "2" not in pick and not re.search(r"\d\.\d", pick):
        return sh_home > sh_away
    if "x" in pick and "1" not in pick and "2" not in pick:
        return sh_home == sh_away
    if "2" in pick and "1" not in pick:
        return sh_home < sh_away

    logger.debug("[Accuracy] Unrecognised second_half pick: '%s'", eagle_pick)
    return None


def _resolve_half_btts(eagle_pick: str, result: Dict) -> Optional[bool]:
    """
    Half-based BTTS resolution.

    Picks like:
      - "IY KG Var"  → first half both teams scored
      - "IY KG Yok"  → first half NOT both scored
      - "2Y KG Var"  → second half both teams scored
      - "2Y KG Yok"  → second half NOT both scored
      - "IY+2Y KG Var" → both halves BTTS
    """
    ht_home = result.get("ht_home_score")
    ht_away = result.get("ht_away_score")
    if ht_home is None or ht_away is None:
        return None

    sh_home = result["home_score"] - ht_home
    sh_away = result["away_score"] - ht_away

    fh_btts = ht_home >= 1 and ht_away >= 1
    sh_btts = sh_home >= 1 and sh_away >= 1

    pick = _normalise_pick(eagle_pick)

    # Determine which half
    is_first_half = "iy" in pick or "1y" in pick or "ilk" in pick or "first" in pick
    is_second_half = "2y" in pick or "ikinci" in pick or "second" in pick
    is_both_halves = ("iy" in pick and "2y" in pick) or "+" in pick

    # Determine direction
    is_yes = "var" in pick or "yes" in pick or "evet" in pick
    is_no = "yok" in pick or "no" in pick or "hayir" in pick

    if is_both_halves:
        both_halves_btts = fh_btts and sh_btts
        if is_yes:
            return both_halves_btts
        if is_no:
            return not both_halves_btts
    elif is_second_half:
        if is_yes:
            return sh_btts
        if is_no:
            return not sh_btts
    elif is_first_half:
        if is_yes:
            return fh_btts
        if is_no:
            return not fh_btts
    else:
        # Default: treat as full-match half BTTS (any half)
        if is_yes:
            return fh_btts or sh_btts
        if is_no:
            return not (fh_btts or sh_btts)

    logger.debug("[Accuracy] Unrecognised half_btts pick: '%s'", eagle_pick)
    return None


# Market -> resolver function mapping
MARKET_RESOLVERS = {
    "ms": _resolve_ms,
    "over25": _resolve_over25,
    "over35": _resolve_over35,
    "btts": _resolve_btts,
    "ht_result": _resolve_ht_result,
    "ht_over05": _resolve_ht_over05,
    "corner": _resolve_corner,
    "card": _resolve_card,
    "correct_score": _resolve_correct_score,
    "handicap": _resolve_handicap,
    "first_half": _resolve_first_half,
    "second_half": _resolve_second_half,
    "half_btts": _resolve_half_btts,
}


# ============================================================================
# Core accuracy computation
# ============================================================================

def _build_actual_result_string(market: str, result: Dict) -> str:
    """Build a human-readable actual result string for storage."""
    home = result["home_score"]
    away = result["away_score"]
    ht_home = result.get("ht_home_score", 0) or 0
    ht_away = result.get("ht_away_score", 0) or 0

    if market == "ms":
        if home > away:
            return f"1 ({home}-{away})"
        elif home == away:
            return f"X ({home}-{away})"
        else:
            return f"2 ({home}-{away})"

    if market in ("over25", "over35"):
        total = home + away
        return f"{total} gol ({home}-{away})"

    if market == "btts":
        both = home >= 1 and away >= 1
        return f"{'KG Var' if both else 'KG Yok'} ({home}-{away})"

    if market in ("ht_result", "ht_over05"):
        return f"IY {ht_home}-{ht_away}"

    if market == "corner":
        corners = result.get("total_corners")
        return f"{corners} korner" if corners is not None else "korner bilinmiyor"

    if market == "card":
        cards = result.get("total_cards")
        return f"{cards} kart" if cards is not None else "kart bilinmiyor"

    if market == "correct_score":
        return f"Skor {home}-{away}"

    if market == "handicap":
        return f"{home}-{away}"

    if market in ("first_half", "half_btts"):
        return f"IY {ht_home}-{ht_away}, MS {home}-{away}"

    if market == "second_half":
        sh_home = home - ht_home
        sh_away = away - ht_away
        return f"2Y {sh_home}-{sh_away}, MS {home}-{away}"

    return f"{home}-{away}"


def _evaluate_predictions(
    predictions_data: Dict[str, Any],
    results_map: Dict[int, Dict[str, Any]],
    target_date: str,
) -> List[Dict[str, Any]]:
    """
    Compare each prediction against actual results.

    Returns a list of evaluation dicts ready for DB insertion.
    """
    evaluations: List[Dict[str, Any]] = []
    matches = predictions_data.get("matches", [])

    for match_entry in matches:
        match_info = match_entry.get("match", {})
        predictions = match_entry.get("predictions", {})
        match_id = match_info.get("match_id")

        if not match_id or not predictions:
            continue

        result = results_map.get(match_id)
        if result is None:
            # Match not finished yet or not found in results
            continue

        for market, pred_data in predictions.items():
            eagle_pick = pred_data.get("eagle_pick")
            eagle_confidence = pred_data.get("eagle_confidence")

            if not eagle_pick:
                continue

            # Get the resolver for this market
            resolver = MARKET_RESOLVERS.get(market)
            if resolver is None:
                # Unknown market (e.g. htft) — skip
                logger.debug(
                    "[Accuracy] No resolver for market '%s', skipping", market
                )
                continue

            # Evaluate
            try:
                is_correct = resolver(eagle_pick, result)
            except Exception as exc:
                logger.warning(
                    "[Accuracy] Resolver error for match %d market %s: %s",
                    match_id, market, exc,
                )
                is_correct = None

            actual_result = _build_actual_result_string(market, result)

            evaluations.append({
                "date": target_date,
                "match_id": match_id,
                "sport": "football",
                "algorithm": market,  # market name as algorithm identifier
                "market": market,
                "prediction": eagle_pick,
                "confidence": eagle_confidence,
                "actual_result": actual_result,
                "is_correct": is_correct,
                "home_team": match_info.get("home_team", ""),
                "away_team": match_info.get("away_team", ""),
                "league": match_info.get("league", ""),
                "home_score": result["home_score"],
                "away_score": result["away_score"],
                "ht_home_score": result.get("ht_home_score"),
                "ht_away_score": result.get("ht_away_score"),
                "total_goals": result["total_goals"],
                "total_corners": result.get("total_corners"),
                "total_cards": result.get("total_cards"),
            })

    return evaluations


# ============================================================================
# Database persistence
# ============================================================================

_UPSERT_RESULT_SQL = """
INSERT INTO prediction_results (
    date, match_id, sport, algorithm, market, prediction, confidence,
    actual_result, is_correct, home_team, away_team, league,
    home_score, away_score, ht_home_score, ht_away_score,
    total_goals, total_corners, total_cards
) VALUES (
    %(date)s, %(match_id)s, %(sport)s, %(algorithm)s, %(market)s,
    %(prediction)s, %(confidence)s, %(actual_result)s, %(is_correct)s,
    %(home_team)s, %(away_team)s, %(league)s,
    %(home_score)s, %(away_score)s, %(ht_home_score)s, %(ht_away_score)s,
    %(total_goals)s, %(total_corners)s, %(total_cards)s
)
ON CONFLICT (date, match_id, algorithm, market) DO UPDATE SET
    prediction = EXCLUDED.prediction,
    confidence = EXCLUDED.confidence,
    actual_result = EXCLUDED.actual_result,
    is_correct = EXCLUDED.is_correct,
    home_score = EXCLUDED.home_score,
    away_score = EXCLUDED.away_score,
    ht_home_score = EXCLUDED.ht_home_score,
    ht_away_score = EXCLUDED.ht_away_score,
    total_goals = EXCLUDED.total_goals,
    total_corners = EXCLUDED.total_corners,
    total_cards = EXCLUDED.total_cards
"""

_UPSERT_ACCURACY_SQL = """
INSERT INTO algorithm_accuracy (
    date, sport, algorithm, market, total_predictions, correct_predictions,
    accuracy_pct, avg_confidence
) VALUES (
    %(date)s, %(sport)s, %(algorithm)s, %(market)s, %(total_predictions)s,
    %(correct_predictions)s, %(accuracy_pct)s, %(avg_confidence)s
)
ON CONFLICT (date, sport, algorithm, market) DO UPDATE SET
    total_predictions = EXCLUDED.total_predictions,
    correct_predictions = EXCLUDED.correct_predictions,
    accuracy_pct = EXCLUDED.accuracy_pct,
    avg_confidence = EXCLUDED.avg_confidence
"""


def _store_results(evaluations: List[Dict[str, Any]]) -> int:
    """Insert/update prediction results in the database."""
    if not evaluations:
        return 0
    count = execute_many(_UPSERT_RESULT_SQL, evaluations)
    logger.info("[Accuracy] Stored %d prediction results", len(evaluations))
    return count


def _compute_and_store_accuracy(
    evaluations: List[Dict[str, Any]],
    target_date: str,
) -> Dict[str, Dict[str, Any]]:
    """
    Aggregate evaluations by algorithm (market), compute accuracy,
    and store in algorithm_accuracy table.

    Returns dict of algorithm -> {total, correct, accuracy_pct, avg_confidence}.
    """
    # Group by algorithm
    algo_stats: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "total": 0,
            "correct": 0,
            "undetermined": 0,
            "confidences": [],
        }
    )

    for ev in evaluations:
        algo = ev["algorithm"]
        stats = algo_stats[algo]
        stats["total"] += 1

        if ev["is_correct"] is True:
            stats["correct"] += 1
        elif ev["is_correct"] is None:
            stats["undetermined"] += 1

        if ev["confidence"] is not None:
            stats["confidences"].append(ev["confidence"])

    # Compute percentages and prepare DB rows
    accuracy_rows: List[Dict[str, Any]] = []
    summary: Dict[str, Dict[str, Any]] = {}

    for algo, stats in algo_stats.items():
        determined = stats["total"] - stats["undetermined"]
        if determined > 0:
            accuracy_pct = round((stats["correct"] / determined) * 100, 2)
        else:
            accuracy_pct = 0.0

        avg_conf = (
            round(sum(stats["confidences"]) / len(stats["confidences"]), 2)
            if stats["confidences"]
            else 0.0
        )

        accuracy_rows.append({
            "date": target_date,
            "sport": "football",
            "algorithm": algo,
            "market": algo,  # algorithm == market for per-market tracking
            "total_predictions": determined,
            "correct_predictions": stats["correct"],
            "accuracy_pct": accuracy_pct,
            "avg_confidence": avg_conf,
        })

        summary[algo] = {
            "total": determined,
            "correct": stats["correct"],
            "undetermined": stats["undetermined"],
            "accuracy_pct": accuracy_pct,
            "avg_confidence": avg_conf,
        }

    if accuracy_rows:
        execute_many(_UPSERT_ACCURACY_SQL, accuracy_rows)
        logger.info(
            "[Accuracy] Stored accuracy for %d algorithms", len(accuracy_rows)
        )

    return summary


# ============================================================================
# Public API
# ============================================================================

def calculate_accuracy(
    target_date: str,
    *,
    enrich_details: bool = True,
) -> Dict[str, Any]:
    """
    Main entry point: compare predictions vs results for a given date.

    1. Load prediction JSON from data/ directory.
    2. Fetch actual match results via result_resolver.
    3. Evaluate each prediction market.
    4. Store results in prediction_results table.
    5. Compute and store aggregated accuracy in algorithm_accuracy table.

    Args:
        target_date:     Date in YYYY-MM-DD format.
        enrich_details:  Fetch corner/card data from detail pages (slower
                         but more accurate).

    Returns:
        Summary dict:
        {
            "date": "2026-03-28",
            "total_predictions": 450,
            "matched_predictions": 380,
            "unmatched_predictions": 70,
            "per_algorithm": {
                "ms": {"total": 60, "correct": 38, "accuracy_pct": 63.33, ...},
                "over25": {"total": 55, "correct": 35, "accuracy_pct": 63.64, ...},
                ...
            },
            "overall_accuracy_pct": 58.42,
            "elapsed_seconds": 12.3,
        }
    """
    start_time = time.time()

    logger.info("[Accuracy] Starting accuracy calculation for %s", target_date)

    # Validate date
    try:
        datetime.strptime(target_date, "%Y-%m-%d")
    except ValueError:
        return {
            "error": f"Invalid date format: {target_date}",
            "date": target_date,
        }

    # Step 1: Load predictions
    predictions_data = _load_predictions(target_date)
    if not predictions_data:
        return {
            "date": target_date,
            "error": "No prediction file found",
            "total_predictions": 0,
        }

    total_prediction_matches = len(predictions_data.get("matches", []))

    # Step 2: Fetch match results
    results_list = resolve_match_results(
        target_date, enrich_details=enrich_details
    )
    if not results_list:
        return {
            "date": target_date,
            "error": "No finished match results found",
            "total_predictions": total_prediction_matches,
        }

    # Build lookup: match_id -> result
    results_map: Dict[int, Dict[str, Any]] = {}
    for r in results_list:
        mid = r.get("match_id")
        if mid:
            results_map[mid] = r

    logger.info(
        "[Accuracy] %d predictions, %d results available",
        total_prediction_matches, len(results_map),
    )

    # Step 3: Evaluate predictions
    evaluations = _evaluate_predictions(predictions_data, results_map, target_date)

    matched = len(evaluations)
    unmatched = 0
    for match_entry in predictions_data.get("matches", []):
        mid = match_entry.get("match", {}).get("match_id")
        if mid and mid not in results_map:
            unmatched += 1

    logger.info(
        "[Accuracy] Evaluated %d predictions (%d unmatched matches)",
        matched, unmatched,
    )

    # Step 4: Store individual results
    _store_results(evaluations)

    # Step 5: Compute and store aggregated accuracy
    per_algorithm = _compute_and_store_accuracy(evaluations, target_date)

    # Compute overall accuracy
    total_determined = sum(a["total"] for a in per_algorithm.values())
    total_correct = sum(a["correct"] for a in per_algorithm.values())
    overall_pct = (
        round((total_correct / total_determined) * 100, 2)
        if total_determined > 0
        else 0.0
    )

    elapsed = time.time() - start_time

    summary = {
        "date": target_date,
        "total_prediction_matches": total_prediction_matches,
        "total_result_matches": len(results_map),
        "matched_predictions": matched,
        "unmatched_match_count": unmatched,
        "per_algorithm": per_algorithm,
        "overall_accuracy_pct": overall_pct,
        "total_determined": total_determined,
        "total_correct": total_correct,
        "elapsed_seconds": round(elapsed, 2),
    }

    logger.info(
        "[Accuracy] Done for %s: %d/%d correct (%.1f%%) in %.1fs",
        target_date,
        total_correct,
        total_determined,
        overall_pct,
        elapsed,
    )

    return summary
