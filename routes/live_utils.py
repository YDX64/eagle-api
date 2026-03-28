"""
Live Data Utilities

Fetch and cache functions for live match data.
Uses Lambda for IP rotation when available.
"""
import logging
import time
import json
from typing import Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from app_config import current_config
from http_client import fetch_date_data_simple, get_global_thread_pool, USE_LAMBDA, lambda_client, fetch_batch_via_lambda
from cache_utils import CacheStats

logger = logging.getLogger(__name__)

# ============================================================================
# LIVE DATA ENDPOINTS (Dynamically built from config)
# ============================================================================
def get_live_endpoints():
    """
    Get live data endpoints based on current config.
    Uses PRIMARY_DATA_SOURCE from environment variables.
    """
    base_url = current_config.PRIMARY_DATA_SOURCE.rstrip('/')
    return {
        'matches': f'{base_url}/gf/data/bf_en-idn.js',
        'stats': f'{base_url}/gf/data/detail.js',
        'odds': f'{base_url}/gf/data/odds/en/runOddsData_8.txt',
        'corners': f'{base_url}/gf/data/sbCorner.js',
        'changes': f'{base_url}/gf/data/change_en.xml',
    }


# Lazy-loaded endpoints (initialized on first use)
_live_endpoints_cache = None


def _get_live_endpoints():
    """Get or initialize LIVE_ENDPOINTS from config"""
    global _live_endpoints_cache
    if _live_endpoints_cache is None:
        _live_endpoints_cache = get_live_endpoints()
        logger.info(f"📡 Live endpoints initialized from: {current_config.PRIMARY_DATA_SOURCE}")
    return _live_endpoints_cache


# Backward compatibility - will be lazily evaluated
LIVE_ENDPOINTS = None  # Use _get_live_endpoints() instead

# Cache TTLs (in seconds)
LIVE_CACHE_TTL = 30  # 30 seconds for live data
ODDS_CACHE_TTL = 15  # 15 seconds for odds (change more frequently)

# In-memory cache for live data
_live_cache = {}
_cache_lock = None


def _get_cache_lock():
    """Get or create cache lock"""
    global _cache_lock
    if _cache_lock is None:
        import threading
        _cache_lock = threading.Lock()
    return _cache_lock


# ============================================================================
# RAW DATA FETCHING
# ============================================================================

def fetch_live_endpoint(endpoint_key: str) -> Optional[str]:
    """
    Fetch raw data from a live endpoint

    Args:
        endpoint_key: One of 'matches', 'stats', 'odds', 'corners', 'changes'

    Returns:
        Raw response text or None on error
    """
    url = _get_live_endpoints().get(endpoint_key)
    if not url:
        logger.error(f"Unknown endpoint: {endpoint_key}")
        return None

    try:
        logger.debug(f"📡 Fetching live endpoint: {endpoint_key}")
        start_time = time.time()

        # Use the same fetch function as other endpoints (supports Lambda)
        response = fetch_date_data_simple(url)

        elapsed = time.time() - start_time
        logger.debug(f"✅ Fetched {endpoint_key} in {elapsed:.2f}s ({len(response)} chars)")

        return response

    except Exception as e:
        logger.error(f"❌ Failed to fetch {endpoint_key}: {e}")
        return None


def fetch_raw_live_data() -> Dict[str, str]:
    """
    Fetch raw data from all live endpoints (for debugging)

    Returns:
        Dict with raw responses from each endpoint
    """
    result = {}

    for key in ['matches', 'stats', 'odds']:
        try:
            result[f'{key}_raw'] = fetch_live_endpoint(key) or ''
        except Exception as e:
            result[f'{key}_raw'] = f'Error: {e}'

    return result


def fetch_all_live_data_parallel(
    include_stats: bool = True,
    include_odds: bool = True,
    include_corners: bool = False
) -> Dict[str, str]:
    """
    Fetch all live data endpoints in parallel.
    Uses batch Lambda (single invocation) when available, falls back to per-endpoint fetch.

    Returns:
        Dict with raw responses keyed by endpoint name
    """
    endpoints_to_fetch = ['matches']

    if include_stats:
        endpoints_to_fetch.append('stats')
    if include_odds:
        endpoints_to_fetch.append('odds')
    if include_corners:
        endpoints_to_fetch.append('corners')

    live_endpoints = _get_live_endpoints()
    results = {}
    failed_keys = []

    # ================================================================
    # STEP 1: Batch Lambda ile tüm live endpoint'leri tek çağrıda dene
    # ================================================================
    if USE_LAMBDA:
        batch_urls = {key: live_endpoints[key] for key in endpoints_to_fetch if key in live_endpoints}

        if batch_urls:
            batch_results = fetch_batch_via_lambda(batch_urls)

            for key in endpoints_to_fetch:
                lambda_result = batch_results.get(key)
                if isinstance(lambda_result, dict) and lambda_result.get('statusCode') == 200:
                    results[key] = lambda_result['body']
                    logger.debug(f"   ✅ [LIVE-BATCH] {key} successful from Lambda")
                else:
                    failed_keys.append(key)
                    logger.debug(f"   ⚠️ [LIVE-BATCH] {key} failed, will try direct HTTP")
    else:
        failed_keys = list(endpoints_to_fetch)

    # ================================================================
    # STEP 2: Başarısız olanları direct HTTP ile dene
    # ================================================================
    if failed_keys:
        logger.debug(f"   🔄 [LIVE] {len(failed_keys)} endpoints need direct fetch: {failed_keys}")
        executor = get_global_thread_pool()

        future_to_key = {
            executor.submit(fetch_live_endpoint, key): key
            for key in failed_keys
        }

        for future in as_completed(future_to_key, timeout=15):
            key = future_to_key[future]
            try:
                results[key] = future.result(timeout=3)
            except Exception as e:
                logger.error(f"Failed to fetch {key}: {e}")
                results[key] = None

    return results


# ============================================================================
# CACHED DATA FETCHING
# ============================================================================

def _get_from_cache(cache_key: str) -> Optional[Dict]:
    """Get data from cache if not expired"""
    lock = _get_cache_lock()
    with lock:
        if cache_key in _live_cache:
            entry = _live_cache[cache_key]
            if time.time() < entry['expires']:
                return entry['data']
    return None


def _set_cache(cache_key: str, data: Any, ttl: int):
    """Set data in cache with TTL"""
    lock = _get_cache_lock()
    with lock:
        _live_cache[cache_key] = {
            'data': data,
            'expires': time.time() + ttl,
            'created': time.time()
        }


def fetch_live_data_cached(
    include_stats: bool = True,
    include_odds: bool = True,
    include_corners: bool = False
) -> Dict[str, Any]:
    """
    Fetch and parse all live data with caching

    Args:
        include_stats: Include technical stats
        include_odds: Include live odds
        include_corners: Include corner data

    Returns:
        Parsed and enriched live data
    """
    cache_key = f"live_all_{include_stats}_{include_odds}_{include_corners}"

    # Check cache
    cached = _get_from_cache(cache_key)
    if cached:
        logger.debug(f"📦 Cache hit for {cache_key}")
        return cached

    logger.info(f"🔄 Fetching fresh live data (stats={include_stats}, odds={include_odds})")

    try:
        # Fetch all endpoints in parallel
        raw_data = fetch_all_live_data_parallel(include_stats, include_odds, include_corners)

        # Import parser
        from live_parsers import LiveDataParser
        parser = LiveDataParser()

        # Parse all data
        parsed = parser.parse_all(
            matches_js=raw_data.get('matches'),
            stats_js=raw_data.get('stats'),
            odds_txt=raw_data.get('odds'),
            corners_js=raw_data.get('corners')
        )

        # Enrich matches with stats/odds/corners
        if parsed['matches']:
            parsed['matches'] = parser.enrich_matches_with_stats(
                parsed['matches'],
                parsed.get('stats', {}),
                parsed.get('odds', {}),
                parsed.get('corners', {})
            )

        # Cache result
        _set_cache(cache_key, parsed, LIVE_CACHE_TTL)

        return parsed

    except Exception as e:
        logger.exception(f"Error fetching live data: {e}")
        return {'error': str(e)}


def fetch_live_match_details_cached(match_id: int) -> Optional[Dict]:
    """
    Fetch detailed data for a specific match

    Returns:
        Match data with stats, odds, corners, and events
    """
    cache_key = f"live_match_{match_id}"

    # Check cache
    cached = _get_from_cache(cache_key)
    if cached:
        logger.debug(f"📦 Cache hit for match {match_id}")
        return cached

    # Fetch all live data
    all_data = fetch_live_data_cached(
        include_stats=True,
        include_odds=True,
        include_corners=True
    )

    if 'error' in all_data:
        return all_data

    # Find specific match
    for match in all_data.get('matches', []):
        if match.get('match_id') == match_id:
            # Add events if available
            events = all_data.get('events', {}).get(match_id, [])
            match['events'] = events

            # Add league info
            league_id = match.get('league_id')
            if league_id and league_id in all_data.get('leagues', {}):
                match['league'] = all_data['leagues'][league_id]

            # Cache individual match
            _set_cache(cache_key, match, LIVE_CACHE_TTL)
            return match

    return None


def fetch_live_stats_cached(match_id: int) -> Optional[Dict]:
    """
    Fetch stats for a specific match

    Returns:
        Match stats or None
    """
    cache_key = f"live_stats_{match_id}"

    # Check cache
    cached = _get_from_cache(cache_key)
    if cached:
        return cached

    # Fetch stats endpoint
    raw_stats = fetch_live_endpoint('stats')
    if not raw_stats:
        return None

    # Parse stats
    from live_parsers import LiveStatsParser
    parser = LiveStatsParser()
    all_stats = parser.parse(raw_stats)

    if match_id in all_stats:
        stats = all_stats[match_id]
        _set_cache(cache_key, stats, LIVE_CACHE_TTL)
        return stats

    return None


def fetch_live_odds_cached(match_id: int) -> Optional[Dict]:
    """
    Fetch odds for a specific match

    Returns:
        Match odds or None
    """
    cache_key = f"live_odds_{match_id}"

    # Check cache
    cached = _get_from_cache(cache_key)
    if cached:
        return cached

    # Fetch odds endpoint
    raw_odds = fetch_live_endpoint('odds')
    if not raw_odds:
        return None

    # Parse odds
    from live_parsers import LiveOddsParser
    parser = LiveOddsParser()
    all_odds = parser.parse(raw_odds)

    if match_id in all_odds:
        odds = all_odds[match_id]
        _set_cache(cache_key, odds, ODDS_CACHE_TTL)
        return odds

    return None


def fetch_live_corners_cached(match_id: int) -> Optional[Dict]:
    """
    Fetch corner data for a specific match

    Returns:
        Corner data or None
    """
    cache_key = f"live_corners_{match_id}"

    # Check cache
    cached = _get_from_cache(cache_key)
    if cached:
        return cached

    # Fetch corners endpoint
    raw_corners = fetch_live_endpoint('corners')
    if not raw_corners:
        return None

    # Parse corners
    from live_parsers import CornerStatsParser
    parser = CornerStatsParser()
    all_corners = parser.parse(raw_corners)

    if match_id in all_corners:
        corners = all_corners[match_id]
        _set_cache(cache_key, corners, LIVE_CACHE_TTL)
        return corners

    return None


def fetch_live_events_cached(match_id: int) -> Optional[list]:
    """
    Fetch events for a specific match

    Returns:
        List of events or None
    """
    cache_key = f"live_events_{match_id}"

    # Check cache
    cached = _get_from_cache(cache_key)
    if cached is not None:
        return cached

    # Fetch stats endpoint (contains events too)
    raw_stats = fetch_live_endpoint('stats')
    if not raw_stats:
        return None

    # Parse events
    from live_parsers import LiveEventsParser
    parser = LiveEventsParser()
    all_events = parser.parse(raw_stats)

    events = all_events.get(match_id, [])
    _set_cache(cache_key, events, LIVE_CACHE_TTL)
    return events


# ============================================================================
# CACHE MANAGEMENT
# ============================================================================

def clear_live_cache():
    """Clear all live data cache"""
    global _live_cache
    lock = _get_cache_lock()
    with lock:
        _live_cache.clear()
    logger.info("🧹 Live cache cleared")


def get_live_cache_stats() -> Dict:
    """Get live cache statistics"""
    lock = _get_cache_lock()
    with lock:
        now = time.time()
        valid_entries = sum(1 for e in _live_cache.values() if e['expires'] > now)
        expired_entries = len(_live_cache) - valid_entries

        return {
            'total_entries': len(_live_cache),
            'valid_entries': valid_entries,
            'expired_entries': expired_entries,
            'cache_keys': list(_live_cache.keys())
        }
