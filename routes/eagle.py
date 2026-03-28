"""
Eagle API Endpoints - Unified prediction engine
Combines Falcon, Predator, Predator V2, and Bee predictions.
"""
import asyncio
import logging
import time
from datetime import date, datetime

import httpx
from flask import Blueprint, request

from models import build_success_response, build_error_response, APIError
from routes.utils import fetch_match_data_with_analysis_cached, fetch_date_matches_cached

from eagle.config import EagleConfig
from eagle.collector import (
    extract_bee_predictions,
    extract_falcon_predictions,
    extract_predator_predictions,
    extract_predator_v2_predictions,
    fetch_falcon_for_match,
    fetch_predator_match,
    fetch_predator_v2_match,
    fetch_falcon_matches,
    fetch_predator_picks,
)
from eagle.combiner import (
    build_eagle_summary,
    combine_predictions,
)

eagle_bp = Blueprint("eagle", __name__)
logger = logging.getLogger(__name__)

# Cache for Eagle results (in-memory, per-worker)
_eagle_cache: dict = {}
_CACHE_MAX = 500


def _cache_get(key: str):
    entry = _eagle_cache.get(key)
    if entry and (time.time() - entry["ts"]) < EagleConfig.CACHE_TTL_EAGLE:
        return entry["data"]
    return None


def _cache_set(key: str, data):
    if len(_eagle_cache) > _CACHE_MAX:
        # Evict oldest 100 entries
        sorted_keys = sorted(_eagle_cache, key=lambda k: _eagle_cache[k]["ts"])
        for k in sorted_keys[:100]:
            _eagle_cache.pop(k, None)
    _eagle_cache[key] = {"data": data, "ts": time.time()}


def _run_async(coro):
    """Run an async coroutine from sync Flask context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result(timeout=90)
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


# =============================================================================
# Single Match Eagle Analysis
# =============================================================================

@eagle_bp.route("/eagle/match/<int:match_id>", methods=["GET"])
def eagle_match(match_id: int):
    """
    Get Eagle unified prediction for a single match.
    Fetches from all 4 sources and combines with weighted ensemble.
    """
    start = time.time()
    logger.info(f"[Eagle] Request: /eagle/match/{match_id}")

    # Check cache
    cache_key = f"eagle:match:{match_id}"
    cached = _cache_get(cache_key)
    if cached:
        logger.info(f"[Eagle] Cache hit for match {match_id}")
        return build_success_response(cached, cached=True)

    try:
        # 1. Get Bee (local) analysis - SYNC, needs Flask app context
        bee_data = fetch_match_data_with_analysis_cached(match_id)
        if not bee_data:
            raise APIError(f"Match {match_id} not found", 404)

        # Extract match info
        mi = bee_data.get("match_info") or {}
        match_info = {
            "match_id": match_id,
            "home_team": mi.get("home_team_name", bee_data.get("home_team", "")),
            "away_team": mi.get("away_team_name", bee_data.get("away_team", "")),
            "league": mi.get("league", bee_data.get("league", "")),
            "match_time": mi.get("match_time_utc", bee_data.get("match_time", "")),
            "match_date": bee_data.get("match_date", ""),
            "status": (mi.get("score_info") or {}).get("status", ""),
            "score": {
                "home": (mi.get("score_info") or {}).get("home_score"),
                "away": (mi.get("score_info") or {}).get("away_score"),
                "ht_home": (mi.get("score_info") or {}).get("ht_home_score"),
                "ht_away": (mi.get("score_info") or {}).get("ht_away_score"),
            } if mi.get("score_info") else None,
        }

        # 2. Fetch external sources async
        external = _run_async(_fetch_external_sources(match_id))

        # 3. Extract predictions from each source
        source_predictions = {}

        bee_preds = extract_bee_predictions(bee_data)
        if bee_preds:
            source_predictions["bee"] = bee_preds

        falcon_data = external.get("falcon")
        predator_data = external.get("predator")
        predator_v2_data = external.get("predator_v2")

        if falcon_data:
            falcon_preds = extract_falcon_predictions(falcon_data)
            if falcon_preds:
                source_predictions["falcon"] = falcon_preds

        if predator_data:
            predator_preds = extract_predator_predictions(predator_data)
            if predator_preds:
                source_predictions["predator"] = predator_preds

        if predator_v2_data:
            v2_preds = extract_predator_v2_predictions(predator_v2_data)
            if v2_preds:
                source_predictions["predator_v2"] = v2_preds

        if not source_predictions:
            raise APIError(f"No predictions available for match {match_id}", 404)

        # 4. Combine using Eagle ensemble
        markets = combine_predictions(source_predictions)

        # 5. Build summary
        result = build_eagle_summary(markets, match_info)
        _cache_set(cache_key, result)

        elapsed = time.time() - start
        logger.info(f"[Eagle] Match {match_id} completed in {elapsed:.2f}s")
        return build_success_response(result)

    except APIError:
        raise
    except Exception as e:
        elapsed = time.time() - start
        logger.error(f"[Eagle] Match {match_id} failed in {elapsed:.2f}s: {e}")
        raise APIError(f"Eagle analysis failed for match {match_id}", 500) from e


async def _fetch_external_sources(match_id: int) -> dict:
    """Async: Fetch from Falcon, Predator, Predator V2 in parallel."""
    results = {}
    async with httpx.AsyncClient() as client:
        falcon_task = fetch_falcon_for_match(client, match_id)
        predator_task = fetch_predator_match(client, match_id)
        predator_v2_task = fetch_predator_v2_match(client, match_id)

        falcon_data, predator_data, predator_v2_data = await asyncio.gather(
            falcon_task, predator_task, predator_v2_task,
            return_exceptions=True,
        )

    if isinstance(falcon_data, Exception):
        logger.warning(f"[Eagle] Falcon failed for {match_id}: {falcon_data}")
    else:
        results["falcon"] = falcon_data

    if isinstance(predator_data, Exception):
        logger.warning(f"[Eagle] Predator failed for {match_id}: {predator_data}")
    else:
        results["predator"] = predator_data

    if isinstance(predator_v2_data, Exception):
        logger.warning(f"[Eagle] Predator V2 failed for {match_id}: {predator_v2_data}")
    else:
        results["predator_v2"] = predator_v2_data

    return results


# =============================================================================
# Date-based Eagle Analysis (all matches for a date)
# =============================================================================

@eagle_bp.route("/eagle/matches/<string:target_date>", methods=["GET"])
def eagle_matches_by_date(target_date: str):
    """
    Get Eagle predictions for all matches on a given date.
    Uses Bee match list as base, enriches with Falcon and Predator data.
    """
    start = time.time()
    logger.info(f"[Eagle] Request: /eagle/matches/{target_date}")

    # Validate date
    try:
        datetime.strptime(target_date, "%Y-%m-%d")
    except ValueError:
        return build_error_response("Invalid date format. Use YYYY-MM-DD", 400), 400

    # Check cache
    cache_key = f"eagle:matches:{target_date}"
    cached = _cache_get(cache_key)
    if cached:
        return build_success_response(cached, cached=True)

    try:
        # 1. Get Bee match list - SYNC (needs Flask app context)
        bee_matches_resp = fetch_date_matches_cached(target_date)
        bee_matches = bee_matches_resp.get("matches", []) if bee_matches_resp else []

        if not bee_matches:
            result = {"date": target_date, "matches": [], "meta": {"total": 0}}
            return build_success_response(result)

        # 2. Fetch external sources + process - ASYNC
        result = _run_async(_process_date_matches(target_date, bee_matches))
        _cache_set(cache_key, result)

        elapsed = time.time() - start
        logger.info(f"[Eagle] Date {target_date} completed in {elapsed:.2f}s, {len(result.get('matches', []))} matches")
        return build_success_response(result)

    except Exception as e:
        elapsed = time.time() - start
        logger.error(f"[Eagle] Date {target_date} failed in {elapsed:.2f}s: {e}")
        raise APIError(f"Eagle analysis failed for date {target_date}", 500) from e


async def _process_date_matches(target_date: str, bee_matches: list) -> dict:
    """Async: Fetch external APIs and combine with pre-fetched Bee matches."""

    # Fetch external sources in parallel
    async with httpx.AsyncClient() as client:
        falcon_matches_task = fetch_falcon_matches(client, target_date)
        predator_picks_task = fetch_predator_picks(client, target_date)

        falcon_matches, predator_picks = await asyncio.gather(
            falcon_matches_task, predator_picks_task,
            return_exceptions=True,
        )

    if isinstance(falcon_matches, Exception):
        logger.warning(f"[Eagle] Falcon date fetch failed: {falcon_matches}")
        falcon_matches = []
    if isinstance(predator_picks, Exception):
        logger.warning(f"[Eagle] Predator date fetch failed: {predator_picks}")
        predator_picks = []

    # Build lookup maps
    predator_map = _build_predator_lookup(predator_picks)

    # Process each match (with Falcon analysis limited by rate)
    sem = asyncio.Semaphore(EagleConfig.FALCON_MAX_CONCURRENT)

    async def process_match(bee_match):
        match_id = bee_match.get("match_id") or bee_match.get("id")
        home = bee_match.get("home_team", "")
        away = bee_match.get("away_team", "")

        if not match_id:
            return None

        source_predictions = {}

        # Bee predictions
        bee_analysis = bee_match.get("analysis", {})
        if bee_analysis:
            bee_preds = extract_bee_predictions(bee_match)
            if bee_preds:
                source_predictions["bee"] = bee_preds

        # Predator predictions
        pred_key = _find_predator_match(home, away, predator_map)
        if pred_key:
            pred_data = predator_map[pred_key]
            pred_preds = extract_predator_predictions(pred_data)
            if pred_preds:
                source_predictions["predator"] = pred_preds

        # Falcon analysis (rate-limited)
        async with sem:
            async with httpx.AsyncClient() as fc:
                falcon_data = await fetch_falcon_for_match(fc, match_id)
                if falcon_data:
                    falcon_preds = extract_falcon_predictions(falcon_data)
                    if falcon_preds:
                        source_predictions["falcon"] = falcon_preds
                await asyncio.sleep(EagleConfig.FALCON_DELAY)

        if not source_predictions:
            return None

        markets = combine_predictions(source_predictions)
        match_info = {
            "match_id": match_id,
            "home_team": home,
            "away_team": away,
            "league": bee_match.get("league", ""),
            "match_time": bee_match.get("match_time", ""),
        }
        return build_eagle_summary(markets, match_info)

    tasks = [process_match(m) for m in bee_matches]
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    matches = []
    for r in raw_results:
        if isinstance(r, Exception):
            logger.warning(f"[Eagle] Match processing error: {r}")
        elif r is not None:
            matches.append(r)

    matches.sort(key=lambda m: m.get("overall_confidence", 0), reverse=True)

    banko_count = sum(1 for m in matches if m.get("is_banko"))
    high_conf_count = sum(1 for m in matches if m.get("overall_confidence", 0) >= 70)

    return {
        "date": target_date,
        "matches": matches,
        "meta": {
            "total": len(matches),
            "banko_count": banko_count,
            "high_confidence": high_conf_count,
            "sources": {
                "falcon": len(falcon_matches),
                "predator": len(predator_picks),
                "bee": len(bee_matches),
            },
        },
    }


# =============================================================================
# Best Picks (filtered by agreement/confidence)
# =============================================================================

@eagle_bp.route("/eagle/best/<string:target_date>", methods=["GET"])
def eagle_best(target_date: str):
    """Get Eagle's best picks for a date (high confidence + agreement)."""
    min_confidence = request.args.get("min_confidence", 70, type=int)
    min_agreement = request.args.get("min_agreement", 2, type=int)

    # First get all matches
    cache_key = f"eagle:matches:{target_date}"
    cached = _cache_get(cache_key)

    if not cached:
        try:
            bee_resp = fetch_date_matches_cached(target_date)
            bee_list = bee_resp.get("matches", []) if bee_resp else []
            if bee_list:
                cached = _run_async(_process_date_matches(target_date, bee_list))
            else:
                cached = {"date": target_date, "matches": []}
            _cache_set(cache_key, cached)
        except Exception as e:
            raise APIError(f"Eagle analysis failed for {target_date}", 500) from e

    all_matches = cached.get("matches", [])

    best = []
    for m in all_matches:
        if m.get("overall_confidence", 0) >= min_confidence and m.get("max_agreement", 0) >= min_agreement:
            best.append(m)

    return build_success_response({
        "date": target_date,
        "matches": best,
        "meta": {
            "total": len(best),
            "filters": {
                "min_confidence": min_confidence,
                "min_agreement": min_agreement,
            },
        },
    })


# =============================================================================
# BANKO Picks
# =============================================================================

@eagle_bp.route("/eagle/banko/<string:target_date>", methods=["GET"])
def eagle_banko(target_date: str):
    """Get Eagle BANKO picks (highest confidence, most agreement)."""
    cache_key = f"eagle:matches:{target_date}"
    cached = _cache_get(cache_key)

    if not cached:
        try:
            bee_resp = fetch_date_matches_cached(target_date)
            bee_list = bee_resp.get("matches", []) if bee_resp else []
            if bee_list:
                cached = _run_async(_process_date_matches(target_date, bee_list))
            else:
                cached = {"date": target_date, "matches": []}
            _cache_set(cache_key, cached)
        except Exception as e:
            raise APIError(f"Eagle analysis failed for {target_date}", 500) from e

    all_matches = cached.get("matches", [])
    bankos = [m for m in all_matches if m.get("is_banko")]

    return build_success_response({
        "date": target_date,
        "matches": bankos,
        "meta": {
            "total": len(bankos),
        },
    })


# =============================================================================
# Eagle Status / Health
# =============================================================================

@eagle_bp.route("/eagle/status", methods=["GET"])
def eagle_status():
    """Check Eagle engine status and source connectivity."""
    status = {
        "engine": "eagle",
        "version": "1.0.0",
        "sources": {
            "falcon": {
                "url": EagleConfig.FALCON_API_URL,
                "configured": bool(EagleConfig.FALCON_API_KEY),
            },
            "predator": {
                "url": EagleConfig.PREDATOR_API_URL,
                "configured": bool(EagleConfig.PREDATOR_API_KEY),
            },
            "predator_v2": {
                "url": EagleConfig.PREDATOR_V2_API_URL or "not configured",
                "configured": bool(EagleConfig.PREDATOR_V2_API_URL),
            },
            "bee": {
                "url": "local",
                "configured": True,
            },
        },
        "cache_entries": len(_eagle_cache),
        "weights": EagleConfig.SOURCE_WEIGHTS,
    }
    return build_success_response(status)


# =============================================================================
# Helpers
# =============================================================================

def _build_predator_lookup(picks: list) -> dict:
    """Build a lookup map from predator picks: normalized_key -> pick_data."""
    lookup = {}
    for p in picks:
        home = (p.get("home_team") or "").strip().lower()
        away = (p.get("away_team") or "").strip().lower()
        if home and away:
            key = f"{home}|{away}"
            lookup[key] = p
    return lookup


def _find_predator_match(home: str, away: str, lookup: dict) -> str | None:
    """Find a predator match using exact or fuzzy matching."""
    home_lower = home.strip().lower()
    away_lower = away.strip().lower()
    key = f"{home_lower}|{away_lower}"

    if key in lookup:
        return key

    # Try fuzzy match
    from difflib import SequenceMatcher
    best_key = None
    best_score = 0

    for k in lookup:
        parts = k.split("|")
        if len(parts) != 2:
            continue
        h_score = SequenceMatcher(None, home_lower, parts[0]).ratio()
        a_score = SequenceMatcher(None, away_lower, parts[1]).ratio()
        avg = (h_score + a_score) / 2
        if avg > best_score and avg >= EagleConfig.MATCH_THRESHOLD:
            best_score = avg
            best_key = k

    return best_key
