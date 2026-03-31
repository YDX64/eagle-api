"""
Basket1 Accuracy Bridge — imports basketball picks into awa-postgres.

Fetches resolved picks from Basket1 API, transforms them into
prediction_results format, and stores with sport='basketball'.

The Basket1 API runs as a sibling container on the same Docker network
(coolify).  Connection details come from environment variables:

    BASKET1_API_URL   — base URL (default ``http://basket1-api:8091``)
    BASKET1_API_KEY   — API key for authentication

Functions:

    fetch_basket1_picks(date)         → raw picks list
    transform_picks_to_results(picks) → prediction_results rows
    sync_basket1_accuracy(date)       → full sync + summary dict
    get_basket1_accuracy_summary(n)   → N-day accuracy breakdown
"""

import logging
import os
import re
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests

from accuracy.db import execute_many, execute_query

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASKET1_API_URL = os.getenv("BASKET1_API_URL", "http://basket1-api:8091")
BASKET1_API_KEY = os.getenv("BASKET1_API_KEY", "")
BASKET1_FALLBACK_URL = os.getenv("BASKET1_FALLBACK_URL", "http://147.93.94.92:8091")

# HTTP settings
REQUEST_TIMEOUT = 30  # seconds
MAX_RETRIES = 2

# Resolved pick states that count as final
RESOLVED_STATES = {"won", "lost"}


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _build_headers() -> Dict[str, str]:
    """Build request headers including API key if configured."""
    headers = {
        "Accept": "application/json",
        "User-Agent": "EagleAPI-Basket1Bridge/1.0",
    }
    if BASKET1_API_KEY:
        headers["X-API-KEY"] = BASKET1_API_KEY
    return headers


def _request_with_fallback(path: str) -> Optional[Dict[str, Any]]:
    """
    Make a GET request to Basket1 API with fallback URL.

    Tries the primary URL first. If it fails, retries with the fallback URL
    (host IP instead of Docker network name). Returns the parsed JSON
    response or None on total failure.
    """
    urls = [f"{BASKET1_API_URL}{path}"]
    if BASKET1_FALLBACK_URL and BASKET1_FALLBACK_URL != BASKET1_API_URL:
        urls.append(f"{BASKET1_FALLBACK_URL}{path}")

    headers = _build_headers()

    for url in urls:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.debug(
                    "[Basket1Bridge] GET %s (attempt %d/%d)",
                    url, attempt, MAX_RETRIES,
                )
                resp = requests.get(
                    url,
                    headers=headers,
                    timeout=REQUEST_TIMEOUT,
                )
                resp.raise_for_status()
                data = resp.json()
                return data

            except requests.exceptions.ConnectionError as exc:
                logger.warning(
                    "[Basket1Bridge] Connection failed for %s: %s",
                    url, exc,
                )
                break  # No point retrying same URL on connection error

            except requests.exceptions.Timeout as exc:
                logger.warning(
                    "[Basket1Bridge] Timeout for %s (attempt %d): %s",
                    url, attempt, exc,
                )
                if attempt < MAX_RETRIES:
                    time.sleep(1)

            except requests.exceptions.HTTPError as exc:
                logger.warning(
                    "[Basket1Bridge] HTTP error for %s: %s",
                    url, exc,
                )
                break  # Server responded with an error, don't retry

            except Exception as exc:
                logger.error(
                    "[Basket1Bridge] Unexpected error for %s: %s",
                    url, exc,
                )
                break

    return None


# ---------------------------------------------------------------------------
# Score parsing
# ---------------------------------------------------------------------------

def _parse_score(actual_score: Optional[str]) -> Tuple[Optional[int], Optional[int]]:
    """
    Parse an actual_score string like "109-119" into (home, away).

    Returns (None, None) if the score cannot be parsed.
    """
    if not actual_score:
        return None, None

    match = re.match(r"(\d+)\s*[-:]\s*(\d+)", actual_score.strip())
    if not match:
        return None, None

    return int(match.group(1)), int(match.group(2))


def _parse_line_from_pick(pick: str) -> Optional[float]:
    """
    Extract the numeric line from a pick string.

    Examples:
        "ALT 232.0"  → 232.0
        "UST 215.5"  → 215.5
        "AH -3.5 EV" → -3.5
        "MS 1"       → None (no line)
    """
    # Match any number (possibly negative, possibly decimal) in the pick
    match = re.search(r"([-+]?\d+(?:\.\d+)?)", pick)
    if match:
        return float(match.group(1))
    return None


# ---------------------------------------------------------------------------
# Pick evaluation
# ---------------------------------------------------------------------------

def _evaluate_ou_pick(
    pick: str,
    home_score: int,
    away_score: int,
) -> Optional[bool]:
    """
    Evaluate an Over/Under pick for basketball.

    Pick format:
        "ALT 232.0" — Under 232.0 (correct if total < 232.0)
        "UST 215.5" — Over 215.5 (correct if total > 215.5)

    Returns True/False or None if unparseable.
    """
    total = home_score + away_score
    pick_upper = pick.strip().upper()

    line = _parse_line_from_pick(pick)
    if line is None:
        logger.debug("[Basket1Bridge] Cannot parse OU line from: '%s'", pick)
        return None

    if pick_upper.startswith("ALT"):
        return total < line
    if pick_upper.startswith("UST"):
        return total > line

    # Fallback: check for Turkish keywords
    pick_lower = pick.strip().lower()
    if "alt" in pick_lower or "under" in pick_lower:
        return total < line
    if "ust" in pick_lower or "over" in pick_lower or "üst" in pick_lower:
        return total > line

    logger.debug("[Basket1Bridge] Unrecognised OU direction in: '%s'", pick)
    return None


def _evaluate_ah_pick(
    pick: str,
    home_score: int,
    away_score: int,
) -> Optional[bool]:
    """
    Evaluate an Asian Handicap pick for basketball.

    Pick format:
        "AH -3.5 EV"  — Home team -3.5 (home must win by >3.5)
        "AH +5.5 DEP" — Away team +5.5 (away must not lose by >5.5)

    Returns True/False or None if unparseable.
    """
    pick_upper = pick.strip().upper()

    line = _parse_line_from_pick(pick)
    if line is None:
        logger.debug("[Basket1Bridge] Cannot parse AH line from: '%s'", pick)
        return None

    # Determine side
    if "EV" in pick_upper or "HOME" in pick_upper:
        # Handicap applies to home team
        adjusted_diff = (home_score + line) - away_score
    elif "DEP" in pick_upper or "AWAY" in pick_upper:
        # Handicap applies to away team
        adjusted_diff = (away_score + line) - home_score
    else:
        # Default: assume the sign indicates side
        # Positive line on a team means they get points
        # Negative means they give points
        # Without explicit side, assume home
        adjusted_diff = (home_score + line) - away_score

    if adjusted_diff > 0:
        return True
    if adjusted_diff < 0:
        return False
    # Push — treat as correct (conservative, same as football module)
    return True


def _evaluate_ml_pick(
    pick: str,
    home_score: int,
    away_score: int,
) -> Optional[bool]:
    """
    Evaluate a Moneyline (winner) pick for basketball.

    Pick format:
        "MS 1" — Home win
        "MS 2" — Away win

    Returns True/False or None if unparseable.
    """
    pick_upper = pick.strip().upper()

    # Extract the team indicator
    if "MS 1" in pick_upper or "MS1" in pick_upper or pick_upper == "1":
        return home_score > away_score
    if "MS 2" in pick_upper or "MS2" in pick_upper or pick_upper == "2":
        return away_score > home_score

    # Check for team names or other indicators
    if "HOME" in pick_upper or "EV" in pick_upper:
        return home_score > away_score
    if "AWAY" in pick_upper or "DEP" in pick_upper:
        return away_score > home_score

    logger.debug("[Basket1Bridge] Unrecognised ML pick: '%s'", pick)
    return None


# ---------------------------------------------------------------------------
# Fetch picks from Basket1 API
# ---------------------------------------------------------------------------

def fetch_basket1_picks(target_date: str) -> List[Dict[str, Any]]:
    """
    Fetch resolved basketball picks from the Basket1 API for a given date.

    Calls ``GET /api/v1/picks/{date}`` and filters to only resolved picks
    (result_status in ['won', 'lost']).

    Args:
        target_date: Date string in YYYY-MM-DD format.

    Returns:
        List of raw pick dicts from the API.
        Empty list if the API is unreachable or returns no data.
    """
    path = f"/api/v1/picks/{target_date}"

    logger.info("[Basket1Bridge] Fetching picks for %s", target_date)
    data = _request_with_fallback(path)

    if data is None:
        logger.warning(
            "[Basket1Bridge] Failed to fetch picks for %s (API unreachable)",
            target_date,
        )
        return []

    if not data.get("success", False):
        logger.warning(
            "[Basket1Bridge] API returned error for %s: %s",
            target_date, data.get("error", "unknown"),
        )
        return []

    all_picks = data.get("picks", [])

    # Filter to resolved picks only
    resolved = [
        p for p in all_picks
        if p.get("result_status") in RESOLVED_STATES
    ]

    logger.info(
        "[Basket1Bridge] Fetched %d picks for %s (%d resolved, %d pending)",
        len(all_picks),
        target_date,
        len(resolved),
        len(all_picks) - len(resolved),
    )

    return resolved


# ---------------------------------------------------------------------------
# Transform picks into prediction_results format
# ---------------------------------------------------------------------------

def transform_picks_to_results(
    picks: List[Dict[str, Any]],
    target_date: str,
) -> List[Dict[str, Any]]:
    """
    Transform Basket1 picks into prediction_results-compatible dicts.

    For each pick, creates one or more result entries depending on which
    pick fields are populated (over_pick, handicap_pick, winner_pick).

    Each pick type is evaluated independently using the actual_score to
    determine correctness. If the pick's main_pick_type matches, we use
    the result_status directly as a faster path.

    Args:
        picks:       List of raw pick dicts from Basket1 API.
        target_date: Date string in YYYY-MM-DD format.

    Returns:
        List of dicts ready for insertion into prediction_results table.
    """
    results: List[Dict[str, Any]] = []

    for pick in picks:
        match_id = pick.get("match_id")
        if not match_id:
            continue

        actual_score = pick.get("actual_score")
        home_score, away_score = _parse_score(actual_score)

        if home_score is None or away_score is None:
            logger.debug(
                "[Basket1Bridge] Cannot parse score for match %s: '%s'",
                match_id, actual_score,
            )
            continue

        total_points = home_score + away_score
        result_status = pick.get("result_status")
        main_pick_type = pick.get("main_pick_type", "").upper()
        edge = pick.get("edge")

        # Common fields for all result entries from this pick
        base = {
            "date": target_date,
            "match_id": match_id,
            "sport": "basketball",
            "home_team": pick.get("home_team", ""),
            "away_team": pick.get("away_team", ""),
            "league": pick.get("league", ""),
            "home_score": home_score,
            "away_score": away_score,
            "ht_home_score": None,
            "ht_away_score": None,
            "total_goals": total_points,  # total_goals stores total points for basketball
            "total_corners": None,
            "total_cards": None,
        }

        # --- Over/Under pick ---
        over_pick = pick.get("over_pick")
        if over_pick:
            # Determine correctness
            if main_pick_type == "OU":
                # Main pick type matches — trust result_status directly
                is_correct = result_status == "won"
            else:
                # Secondary pick — evaluate manually
                is_correct = _evaluate_ou_pick(over_pick, home_score, away_score)

            if is_correct is not None:
                actual_str = f"{total_points} ({home_score}-{away_score})"
                results.append({
                    **base,
                    "algorithm": "basket_ou",
                    "market": "over_under",
                    "prediction": over_pick,
                    "confidence": edge,
                    "actual_result": actual_str,
                    "is_correct": is_correct,
                })

        # --- Asian Handicap pick ---
        handicap_pick = pick.get("handicap_pick")
        if handicap_pick:
            if main_pick_type == "AH":
                is_correct = result_status == "won"
            else:
                is_correct = _evaluate_ah_pick(handicap_pick, home_score, away_score)

            if is_correct is not None:
                actual_str = f"{home_score}-{away_score}"
                results.append({
                    **base,
                    "algorithm": "basket_ah",
                    "market": "handicap",
                    "prediction": handicap_pick,
                    "confidence": edge,
                    "actual_result": actual_str,
                    "is_correct": is_correct,
                })

        # --- Moneyline (winner) pick ---
        winner_pick = pick.get("winner_pick")
        if winner_pick:
            if main_pick_type == "ML":
                is_correct = result_status == "won"
            else:
                is_correct = _evaluate_ml_pick(winner_pick, home_score, away_score)

            if is_correct is not None:
                if home_score > away_score:
                    winner_str = f"MS 1 ({home_score}-{away_score})"
                else:
                    winner_str = f"MS 2 ({home_score}-{away_score})"
                results.append({
                    **base,
                    "algorithm": "basket_ml",
                    "market": "winner",
                    "prediction": winner_pick,
                    "confidence": edge,
                    "actual_result": winner_str,
                    "is_correct": is_correct,
                })

    logger.info(
        "[Basket1Bridge] Transformed %d picks into %d result entries",
        len(picks), len(results),
    )
    return results


# ---------------------------------------------------------------------------
# Database persistence (reuses schema from accuracy.db)
# ---------------------------------------------------------------------------

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


def _store_prediction_results(results: List[Dict[str, Any]]) -> int:
    """Insert/update prediction results in the database."""
    if not results:
        return 0
    count = execute_many(_UPSERT_RESULT_SQL, results)
    logger.info("[Basket1Bridge] Stored %d prediction results", len(results))
    return count


def _compute_and_store_accuracy(
    results: List[Dict[str, Any]],
    target_date: str,
) -> Dict[str, Dict[str, Any]]:
    """
    Aggregate results by algorithm (market), compute accuracy percentages,
    and store in algorithm_accuracy table.

    Returns dict of algorithm -> {total, correct, accuracy_pct, avg_confidence}.
    """
    algo_stats: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "total": 0,
            "correct": 0,
            "undetermined": 0,
            "confidences": [],
            "market": "",
        }
    )

    for ev in results:
        algo = ev["algorithm"]
        stats = algo_stats[algo]
        stats["market"] = ev["market"]
        stats["total"] += 1

        if ev["is_correct"] is True:
            stats["correct"] += 1
        elif ev["is_correct"] is None:
            stats["undetermined"] += 1

        if ev.get("confidence") is not None:
            stats["confidences"].append(ev["confidence"])

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
            "sport": "basketball",
            "algorithm": algo,
            "market": stats["market"],
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
            "[Basket1Bridge] Stored accuracy for %d basketball algorithms",
            len(accuracy_rows),
        )

    return summary


# ---------------------------------------------------------------------------
# Main sync entry point
# ---------------------------------------------------------------------------

def sync_basket1_accuracy(target_date: str) -> Dict[str, Any]:
    """
    Main entry point: fetch, transform, store, and summarise basketball
    pick accuracy for a given date.

    Steps:
        1. Fetch resolved picks from Basket1 API.
        2. Transform into prediction_results format.
        3. Store individual results (upsert).
        4. Compute and store per-algorithm accuracy.
        5. Return summary dict.

    Args:
        target_date: Date in YYYY-MM-DD format.

    Returns:
        Summary dict::

            {
                "date": "2026-03-28",
                "sport": "basketball",
                "total_picks": 12,
                "resolved": 10,
                "result_entries": 14,
                "per_market": {
                    "over_under": {"total": 8, "correct": 5, "pct": 62.5},
                    "handicap":   {"total": 3, "correct": 2, "pct": 66.67},
                    "winner":     {"total": 3, "correct": 2, "pct": 66.67},
                },
                "overall_accuracy_pct": 64.29,
                "elapsed_seconds": 1.23,
            }
    """
    start_time = time.time()

    logger.info(
        "[Basket1Bridge] Starting basketball accuracy sync for %s", target_date
    )

    # Validate date format
    try:
        datetime.strptime(target_date, "%Y-%m-%d")
    except ValueError:
        return {
            "error": f"Invalid date format: {target_date}",
            "date": target_date,
            "sport": "basketball",
        }

    # Step 1: Fetch picks
    picks = fetch_basket1_picks(target_date)
    if not picks:
        elapsed = time.time() - start_time
        return {
            "date": target_date,
            "sport": "basketball",
            "total_picks": 0,
            "resolved": 0,
            "result_entries": 0,
            "per_market": {},
            "overall_accuracy_pct": 0.0,
            "elapsed_seconds": round(elapsed, 2),
            "message": "No resolved picks found",
        }

    # Step 2: Transform
    results = transform_picks_to_results(picks, target_date)

    # Step 3: Store individual results
    _store_prediction_results(results)

    # Step 4: Compute and store aggregated accuracy
    per_algorithm = _compute_and_store_accuracy(results, target_date)

    # Step 5: Build summary
    # Map algorithm names back to market names for the summary
    algo_to_market = {
        "basket_ou": "over_under",
        "basket_ah": "handicap",
        "basket_ml": "winner",
    }

    per_market: Dict[str, Dict[str, Any]] = {}
    total_determined = 0
    total_correct = 0

    for algo, stats in per_algorithm.items():
        market_name = algo_to_market.get(algo, algo)
        per_market[market_name] = {
            "total": stats["total"],
            "correct": stats["correct"],
            "pct": stats["accuracy_pct"],
        }
        total_determined += stats["total"]
        total_correct += stats["correct"]

    overall_pct = (
        round((total_correct / total_determined) * 100, 2)
        if total_determined > 0
        else 0.0
    )

    elapsed = time.time() - start_time

    summary = {
        "date": target_date,
        "sport": "basketball",
        "total_picks": len(picks),
        "resolved": len(picks),
        "result_entries": len(results),
        "per_market": per_market,
        "overall_accuracy_pct": overall_pct,
        "total_determined": total_determined,
        "total_correct": total_correct,
        "elapsed_seconds": round(elapsed, 2),
    }

    logger.info(
        "[Basket1Bridge] %s done: %d/%d correct (%.1f%%) across %d markets in %.1fs",
        target_date,
        total_correct,
        total_determined,
        overall_pct,
        len(per_market),
        elapsed,
    )

    return summary


# ---------------------------------------------------------------------------
# Multi-day accuracy summary
# ---------------------------------------------------------------------------

def get_basket1_accuracy_summary(days: int = 7) -> Dict[str, Any]:
    """
    Query prediction_results for basketball over the last N days and
    return a per-market accuracy breakdown.

    Args:
        days: Number of days to look back (default 7).

    Returns:
        Summary dict::

            {
                "sport": "basketball",
                "days": 7,
                "start_date": "2026-03-22",
                "end_date": "2026-03-28",
                "per_market": {
                    "over_under": {"total": 42, "correct": 27, "pct": 64.29},
                    "handicap":   {"total": 18, "correct": 12, "pct": 66.67},
                    "winner":     {"total": 15, "correct": 10, "pct": 66.67},
                },
                "overall": {"total": 75, "correct": 49, "pct": 65.33},
                "daily_breakdown": [
                    {"date": "2026-03-28", "total": 12, "correct": 8, "pct": 66.67},
                    ...
                ],
            }
    """
    end_dt = date.today() - timedelta(days=1)
    start_dt = end_dt - timedelta(days=days - 1)
    start_str = start_dt.strftime("%Y-%m-%d")
    end_str = end_dt.strftime("%Y-%m-%d")

    logger.info(
        "[Basket1Bridge] Generating %d-day summary (%s to %s)",
        days, start_str, end_str,
    )

    try:
        rows = execute_query(
            """
            SELECT date, algorithm, market, is_correct, confidence
            FROM prediction_results
            WHERE sport = 'basketball'
              AND date >= %s AND date <= %s
              AND is_correct IS NOT NULL
            ORDER BY date, algorithm
            """,
            (start_str, end_str),
            fetch=True,
        ) or []
    except Exception as exc:
        logger.error(
            "[Basket1Bridge] Summary query failed: %s", exc, exc_info=True,
        )
        return {
            "sport": "basketball",
            "days": days,
            "error": str(exc),
        }

    if not rows:
        return {
            "sport": "basketball",
            "days": days,
            "start_date": start_str,
            "end_date": end_str,
            "per_market": {},
            "overall": {"total": 0, "correct": 0, "pct": 0.0},
            "daily_breakdown": [],
            "message": "No basketball accuracy data for this period",
        }

    # Aggregate per market
    market_stats: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {"total": 0, "correct": 0}
    )
    daily_stats: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {"total": 0, "correct": 0}
    )

    for row in rows:
        market = row["market"]
        d = str(row["date"])

        market_stats[market]["total"] += 1
        daily_stats[d]["total"] += 1

        if row["is_correct"]:
            market_stats[market]["correct"] += 1
            daily_stats[d]["correct"] += 1

    # Build per_market summary
    per_market: Dict[str, Dict[str, Any]] = {}
    overall_total = 0
    overall_correct = 0

    for market, stats in market_stats.items():
        pct = (
            round((stats["correct"] / stats["total"]) * 100, 2)
            if stats["total"] > 0
            else 0.0
        )
        per_market[market] = {
            "total": stats["total"],
            "correct": stats["correct"],
            "pct": pct,
        }
        overall_total += stats["total"]
        overall_correct += stats["correct"]

    overall_pct = (
        round((overall_correct / overall_total) * 100, 2)
        if overall_total > 0
        else 0.0
    )

    # Build daily breakdown (sorted by date descending)
    daily_breakdown = []
    for d in sorted(daily_stats.keys(), reverse=True):
        stats = daily_stats[d]
        pct = (
            round((stats["correct"] / stats["total"]) * 100, 2)
            if stats["total"] > 0
            else 0.0
        )
        daily_breakdown.append({
            "date": d,
            "total": stats["total"],
            "correct": stats["correct"],
            "pct": pct,
        })

    return {
        "sport": "basketball",
        "days": days,
        "start_date": start_str,
        "end_date": end_str,
        "per_market": per_market,
        "overall": {
            "total": overall_total,
            "correct": overall_correct,
            "pct": overall_pct,
        },
        "daily_breakdown": daily_breakdown,
    }
