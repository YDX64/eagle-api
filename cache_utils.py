"""
Cache Utilities - Stale-While-Revalidate Pattern Implementation

This module provides advanced caching utilities including:
- Stale-while-revalidate pattern for high availability
- Automatic background cache refresh
- Fallback to stale data on upstream failures
- Request deduplication for concurrent identical requests
- Smart TTL based on match status
- Status normalization from raw API values
"""
import logging
import json
import time
import threading
from typing import Callable, Any, Optional, Dict
from functools import wraps
from threading import Lock
from concurrent.futures import Future, ThreadPoolExecutor

logger = logging.getLogger(__name__)


# ============================================================================
# STATUS NORMALIZATION (Converts raw nowgoal values to standard status)
# ============================================================================
def normalize_match_status(raw_status: str = None, match_state: int = None,
                           score_info: dict = None) -> str:
    """
    Normalize match status from nowgoal raw values to standard values.

    Nowgoal returns various status formats:
    - HTML text: 'FT', 'HT', '45'', 'AET', 'PEN', etc.
    - JSON match_state: -1 (finished), 0 (not_started), 1/2/3 (live)
    - Score info: If scores exist, match has started

    This function normalizes to: 'finished', 'live', 'not_started'

    Args:
        raw_status: Status text from HTML (e.g., 'FT', 'HT', "45'")
        match_state: Numeric state from JSON API (-1, 0, 1, 2, 3)
        score_info: Dict with home_score, away_score, ht_score fields

    Returns:
        str: One of 'finished', 'live', 'not_started'

    Examples:
        >>> normalize_match_status(raw_status='FT')
        'finished'
        >>> normalize_match_status(match_state=-1)
        'finished'
        >>> normalize_match_status(raw_status='HT')
        'live'
        >>> normalize_match_status(raw_status="45'")
        'live'
        >>> normalize_match_status(score_info={'home_score': '1', 'away_score': '0', 'status': ''})
        'live'
    """
    # Priority 1: Check match_state (most reliable, from JSON API)
    if match_state is not None:
        if match_state == -1:
            return 'finished'
        elif match_state == 0:
            return 'not_started'
        elif match_state in [1, 2, 3]:
            return 'live'

    # Priority 2: Check raw_status text (from HTML)
    if raw_status:
        status_clean = str(raw_status).strip().upper()

        # Finished statuses
        if status_clean in ['FT', 'AET', 'PEN', 'FINISHED', 'CANC', 'ABD', 'AWD', 'WO', 'POSTP']:
            return 'finished'

        # Live statuses (including minute markers like 45', 90+2)
        if status_clean in ['HT', '1H', '2H', 'LIVE', 'ET', 'BT', 'PT']:
            return 'live'

        # Check for minute marker (e.g., "45'", "90+2", "23")
        if "'" in raw_status or status_clean.isdigit() or '+' in status_clean:
            return 'live'

        # Explicit not started indicators
        if status_clean in ['VS', 'NOT STARTED', '-', 'SCH', 'TBD']:
            return 'not_started'

    # Priority 3: Check score_info - if there's a score, match has started
    if score_info:
        home_score = str(score_info.get('home_score', '')).strip()
        away_score = str(score_info.get('away_score', '')).strip()

        # If both scores exist and are numeric, match has started
        if home_score and away_score:
            try:
                h = int(home_score)
                a = int(away_score)
                # Match has a score - it's either live or finished
                # If status is empty but score exists, assume LIVE
                # (finished matches should have FT status)
                logger.debug(f"[STATUS-DETECT] Score exists ({h}-{a}) but status empty, assuming LIVE")
                return 'live'
            except ValueError:
                pass  # Not numeric scores, ignore

    # Default: assume not started (safest for TTL - will use shorter cache)
    return 'not_started'


def get_smart_ttl_for_status(normalized_status: str) -> int:
    """
    Get optimal cache TTL based on normalized match status.

    Args:
        normalized_status: One of 'finished', 'live', 'not_started'

    Returns:
        int: TTL in seconds
        - finished: 86400 (24 hours) - data won't change
        - live: 60 (1 minute) - frequent updates needed
        - not_started: 300 (5 minutes) - moderate updates
    """
    ttl_map = {
        'finished': 86400,    # 24 hours - match over, data stable
        'live': 60,           # 1 minute - real-time updates needed
        'not_started': 300    # 5 minutes - pre-match updates
    }
    return ttl_map.get(normalized_status, 300)  # Default 5 minutes


# ============================================================================
# CACHE STATISTICS (Monitoring and debugging)
# ============================================================================
class CacheStats:
    """Track cache performance metrics for monitoring."""

    def __init__(self):
        self._lock = Lock()
        self.hits = 0
        self.misses = 0
        self.stale_served = 0
        self.background_refreshes = 0
        self.refresh_failures = 0
        self.dedup_hits = 0

    def record_hit(self):
        with self._lock:
            self.hits += 1

    def record_miss(self):
        with self._lock:
            self.misses += 1

    def record_stale_served(self):
        with self._lock:
            self.stale_served += 1

    def record_background_refresh(self, success: bool = True):
        with self._lock:
            self.background_refreshes += 1
            if not success:
                self.refresh_failures += 1

    def record_dedup_hit(self):
        with self._lock:
            self.dedup_hits += 1

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            total = self.hits + self.misses
            hit_rate = (self.hits / total * 100) if total > 0 else 0
            return {
                'hits': self.hits,
                'misses': self.misses,
                'hit_rate': f"{hit_rate:.1f}%",
                'stale_served': self.stale_served,
                'background_refreshes': self.background_refreshes,
                'refresh_failures': self.refresh_failures,
                'dedup_hits': self.dedup_hits
            }

    def reset(self):
        with self._lock:
            self.hits = 0
            self.misses = 0
            self.stale_served = 0
            self.background_refreshes = 0
            self.refresh_failures = 0
            self.dedup_hits = 0


# Global cache stats instance
_cache_stats = CacheStats()

def get_cache_stats() -> Dict[str, Any]:
    """Get current cache statistics."""
    return _cache_stats.get_stats()

def reset_cache_stats():
    """Reset cache statistics (for testing/monitoring)."""
    _cache_stats.reset()

# ============================================================================
# REQUEST DEDUPLICATION (Prevents duplicate work for concurrent identical requests)
# ============================================================================
class RequestDeduplicator:
    """
    Prevents duplicate work when multiple identical requests arrive concurrently.

    When multiple users request the same resource simultaneously:
    - First request triggers the actual work
    - Subsequent identical requests wait for the first to complete
    - All requests receive the same result

    This saves significant resources during traffic spikes.
    """

    def __init__(self):
        self.pending_requests = {}  # key -> Future
        self.lock = Lock()
        self.executor = ThreadPoolExecutor(max_workers=20, thread_name_prefix="dedup_worker")

    def deduplicate(self, key: str, fetch_function: Callable, ttl: int = 60) -> Any:
        """
        Deduplicate a request based on a unique key.

        Args:
            key: Unique identifier for this request (e.g., cache key)
            fetch_function: Function to call if this is the first request
            ttl: Time in seconds to keep the deduplication active

        Returns:
            Result from fetch_function (either newly fetched or from pending request)
        """
        with self.lock:
            # Check if there's already a pending request for this key
            if key in self.pending_requests:
                future = self.pending_requests[key]
                logger.info(f"[DEDUP-HIT] Request for {key} is already pending, waiting for result...")
                # Release lock before waiting
                self.lock.release()
                try:
                    # Wait for the pending request to complete
                    result = future.result(timeout=ttl)
                    logger.info(f"[DEDUP-RESULT] Got deduplicated result for {key}")
                    return result
                except Exception as e:
                    logger.warning(f"[DEDUP-ERROR] Error waiting for deduplicated result: {e}")
                    raise
                finally:
                    # Re-acquire lock for the 'with' context manager exit
                    self.lock.acquire()

            # This is the first request for this key
            logger.info(f"[DEDUP-MISS] First request for {key}, triggering fetch...")

            # Create a future for this request
            future = self.executor.submit(fetch_function)
            self.pending_requests[key] = future

        # Execute the request (outside the lock)
        try:
            result = future.result(timeout=ttl)
            logger.info(f"[DEDUP-COMPLETE] Fetch completed for {key}")
            return result
        except Exception as e:
            logger.warning(f"[DEDUP-FETCH-ERROR] Error during fetch for {key}: {e}")
            raise
        finally:
            # Cleanup the pending request
            with self.lock:
                if key in self.pending_requests:
                    del self.pending_requests[key]
                    logger.debug(f"[DEDUP-CLEANUP] Removed {key} from pending requests")

    def clear(self):
        """Clear all pending requests (useful for testing or shutdown)"""
        with self.lock:
            self.pending_requests.clear()
            logger.info("[DEDUP-CLEAR] Cleared all pending requests")

    def get_pending_count(self) -> int:
        """Get the number of currently pending deduplicated requests"""
        with self.lock:
            return len(self.pending_requests)

# Global deduplicator instance
_global_deduplicator = RequestDeduplicator()

# Background refresh deduplication - prevents race conditions
_background_refresh_lock = Lock()
_background_refresh_in_progress = set()  # Set of cache keys currently being refreshed


def _safe_json_serialize(data: Any) -> str:
    """Safely serialize data to JSON string."""
    def json_encoder(obj):
        """Custom JSON encoder for non-serializable objects."""
        if hasattr(obj, 'isoformat'):  # datetime objects
            return obj.isoformat()
        if hasattr(obj, '__dict__'):  # Custom objects
            return obj.__dict__
        return str(obj)  # Fallback to string

    try:
        return json.dumps(data, default=json_encoder, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"[SERIALIZE] JSON failed, using str fallback: {e}")
        return json.dumps(str(data))


def _safe_json_deserialize(data) -> Any:
    """Safely deserialize JSON string or bytes to data."""
    try:
        # Handle bytes from Redis
        if isinstance(data, bytes):
            data = data.decode('utf-8')
        return json.loads(data)
    except json.JSONDecodeError as e:
        logger.warning(f"[DESERIALIZE] JSON decode failed: {e}")
        return None
    except Exception as e:
        logger.warning(f"[DESERIALIZE] Unexpected error: {e}")
        return None


def get_with_stale_fallback(cache_instance, cache_key: str,
                            fetch_function: Callable,
                            fresh_ttl: int = 180,
                            stale_ttl: int = 3600):
    """
    Get data from cache with stale-while-revalidate pattern.

    This function implements a high-availability caching strategy:
    1. Check fresh cache (primary)
    2. If expired, check stale cache and return immediately
    3. Attempt to fetch fresh data in foreground
    4. If fetch fails, fallback to stale cache
    5. Update both fresh and stale caches on success

    Args:
        cache_instance: Redis cache instance (Flask-Caching)
        cache_key: Primary cache key (e.g., 'match_data:123')
        fetch_function: Function to call when cache misses (no args)
        fresh_ttl: Fresh cache timeout in seconds (default: 180 = 3 minutes)
        stale_ttl: Stale cache timeout in seconds (default: 3600 = 1 hour)

    Returns:
        Data with metadata:
        - cached: bool (was data from cache?)
        - cache_hit: bool (was fresh cache hit?)
        - stale: bool (was stale cache used?)

    Example:
        >>> data = get_with_stale_fallback(
        ...     cache,
        ...     'match:123',
        ...     lambda: fetch_match_data(123),
        ...     fresh_ttl=180,
        ...     stale_ttl=3600
        ... )
    """
    stale_key = f'{cache_key}:stale'

    # ============================================================
    # STEP 1: Check fresh cache (primary path)
    # ============================================================
    try:
        fresh_data = cache_instance.get(cache_key)
        if fresh_data:
            # Fresh cache hit - deserialize and return (handles both str and bytes from Redis)
            data = _safe_json_deserialize(fresh_data) if isinstance(fresh_data, (str, bytes)) else fresh_data
            if data is None:
                logger.warning(f"[CACHE-CORRUPT] Failed to deserialize cache for {cache_key}")
            else:
                if isinstance(data, dict):
                    data['cached'] = True
                    data['cache_hit'] = True
                    data['stale'] = False
                _cache_stats.record_hit()
                logger.debug(f"[CACHE-HIT] Fresh cache hit for key: {cache_key}")
                return data
    except Exception as e:
        logger.warning(f"[CACHE-ERROR] Failed to check fresh cache for {cache_key}: {e}")

    # ============================================================
    # STEP 2: Fresh cache miss - check stale cache
    # ============================================================
    _cache_stats.record_miss()
    stale_data = None
    try:
        stale_cached = cache_instance.get(stale_key)
        if stale_cached:
            stale_data = _safe_json_deserialize(stale_cached) if isinstance(stale_cached, (str, bytes)) else stale_cached
            logger.debug(f"[CACHE-STALE] Stale cache available for key: {cache_key}")
    except Exception as e:
        logger.warning(f"[CACHE-ERROR] Failed to check stale cache for {cache_key}: {e}")

    # ============================================================
    # STEP 3: Attempt to fetch fresh data from upstream
    # ============================================================
    try:
        logger.info(f"[CACHE-MISS] Fetching fresh data for key: {cache_key}")
        fresh_data = fetch_function()

        # Successfully fetched - update both caches
        try:
            serialized = _safe_json_serialize(fresh_data)

            # Update fresh cache
            cache_instance.set(cache_key, serialized, timeout=fresh_ttl)
            logger.debug(f"[CACHE-SET] Fresh cache updated for {cache_key} (TTL: {fresh_ttl}s)")

            # Update stale cache (longer TTL for fallback)
            cache_instance.set(stale_key, serialized, timeout=stale_ttl)
            logger.debug(f"[CACHE-SET] Stale cache updated for {cache_key} (TTL: {stale_ttl}s)")

        except Exception as cache_error:
            logger.warning(f"[CACHE-ERROR] Failed to cache data for {cache_key}: {cache_error}")

        # Add metadata
        if isinstance(fresh_data, dict):
            fresh_data['cached'] = False
            fresh_data['cache_hit'] = False
            fresh_data['stale'] = False

        return fresh_data

    except Exception as fetch_error:
        # ============================================================
        # STEP 4: Upstream fetch failed - fallback to stale cache
        # ============================================================
        logger.info(f"[CACHE-FALLBACK] Upstream fetch failed for {cache_key}: {fetch_error}")

        if stale_data:
            # Stale data available - serve it!
            logger.info(f"[CACHE-FALLBACK] Serving stale cache for {cache_key} due to upstream failure")
            _cache_stats.record_stale_served()

            if isinstance(stale_data, dict):
                stale_data['cached'] = True
                stale_data['cache_hit'] = False  # Not fresh hit
                stale_data['stale'] = True  # Mark as stale
                stale_data['stale_reason'] = 'upstream_failure'

            return stale_data
        else:
            # No stale data available - re-raise the error
            logger.warning(f"[CACHE-FALLBACK] No stale cache available for {cache_key}, failing request")
            raise fetch_error


def get_with_background_refresh(cache_instance, cache_key: str,
                                  fetch_function: Callable,
                                  fresh_ttl: int = 1800,
                                  dynamic_ttl: int = None):
    """
    Get data from cache with TRUE stale-while-revalidate pattern.

    Bu fonksiyon kullanıcı deneyimi için optimize edilmiştir:
    1. Cache varsa HEMEN DÖN (fresh veya stale fark etmez)
    2. Cache eski ise (>fresh_ttl) arka planda refresh başlat
    3. Kullanıcı asla beklemez!

    Args:
        cache_instance: Redis cache instance (Flask-Caching)
        cache_key: Cache key (e.g., 'match_with_analysis:123')
        fetch_function: Function to fetch fresh data (no args)
        fresh_ttl: Fresh threshold in seconds (default: 1800 = 30 minutes)
        dynamic_ttl: Optional dynamic TTL based on data type (overrides fresh_ttl)

    Returns:
        Data with metadata:
        - cached: bool (was data from cache?)
        - cache_hit: bool (was cache used?)
        - stale: bool (was stale cache used?)
        - refreshing: bool (is background refresh running?)
        - _normalized_status: str (normalized match status if available)
    """

    # Use dynamic TTL if provided (from smart TTL calculation)
    effective_ttl = dynamic_ttl if dynamic_ttl is not None else fresh_ttl

    # Step 1: Check cache
    try:
        cached_data = cache_instance.get(cache_key)

        if cached_data:
            # Cache hit! Deserialize using JSON (handles both str and bytes from Redis)
            data = _safe_json_deserialize(cached_data) if isinstance(cached_data, (str, bytes)) else cached_data

            if data is None:
                logger.warning(f"[CACHE-CORRUPT] Failed to deserialize cache for {cache_key}, fetching fresh")
                # Fall through to cache miss path
            else:
                # Check cache age
                cached_at = data.get('_cached_at', 0)
                age = time.time() - cached_at

                # Get stored TTL from data if available (for dynamic TTL)
                stored_ttl = data.get('_smart_ttl', effective_ttl)

                # Age kontrol
                if age < stored_ttl:
                    # FRESH! Hemen dön, refresh yapma
                    if isinstance(data, dict):
                        data['cached'] = True
                        data['cache_hit'] = True
                        data['stale'] = False
                        data['refreshing'] = False

                    _cache_stats.record_hit()
                    logger.debug(f"[CACHE-FRESH] Cache age {age:.0f}s < {stored_ttl}s, serving: {cache_key}")
                    return data

                else:
                    # STALE! Hemen dön + arka planda refresh başlat
                    if isinstance(data, dict):
                        data['cached'] = True
                        data['cache_hit'] = True
                        data['stale'] = True
                        data['refreshing'] = True

                    _cache_stats.record_stale_served()
                    logger.info(f"[CACHE-STALE] Cache age {age:.0f}s >= {stored_ttl}s, serving stale + background refresh: {cache_key}")

                    # Background refresh with deduplication
                    _start_background_refresh(cache_instance, cache_key, fetch_function, effective_ttl)

                    # Stale veriyi HEMEN dön
                    return data

        # Cache miss - fresh fetch (bu durumda kullanıcı bekler)
        _cache_stats.record_miss()
        logger.info(f"[CACHE-MISS] No cache found, fetching fresh data: {cache_key}")
        fresh_data = fetch_function()

        # Timestamp ve metadata ekle
        if isinstance(fresh_data, dict):
            fresh_data['_cached_at'] = time.time()
            # CRITICAL: Keep _smart_ttl if already calculated by fetch_function
            # Only set effective_ttl if fetch_function didn't calculate smart TTL
            if '_smart_ttl' not in fresh_data or fresh_data.get('_smart_ttl') is None:
                fresh_data['_smart_ttl'] = effective_ttl
            fresh_data['cached'] = False
            fresh_data['cache_hit'] = False
            fresh_data['stale'] = False
            fresh_data['refreshing'] = False

        # Cache'e yaz
        try:
            serialized = _safe_json_serialize(fresh_data)
            # Max TTL 24 hours, but smart TTL determines freshness
            cache_instance.set(cache_key, serialized, timeout=86400)
            logger.debug(f"[CACHE-SET] Cached fresh data for {cache_key} (smart TTL: {effective_ttl}s)")
        except Exception as e:
            logger.warning(f"[CACHE-ERROR] Failed to cache data for {cache_key}: {e}")

        return fresh_data

    except Exception as e:
        # Cache infrastructure hatası - direkt fetch
        logger.warning(f"[CACHE-ERROR] Cache check failed for {cache_key}: {e}, fetching fresh")
        fresh_data = fetch_function()

        if isinstance(fresh_data, dict):
            fresh_data['cached'] = False
            fresh_data['cache_hit'] = False
            fresh_data['stale'] = False
            fresh_data['refreshing'] = False

        return fresh_data


def _start_background_refresh(cache_instance, cache_key: str, fetch_function: Callable, ttl: int):
    """
    Start a background refresh with deduplication.

    Prevents race condition where multiple stale requests trigger multiple
    concurrent background refreshes for the same cache key.
    """
    global _background_refresh_in_progress

    # Check if refresh already in progress
    with _background_refresh_lock:
        if cache_key in _background_refresh_in_progress:
            logger.debug(f"[BACKGROUND-REFRESH] Already in progress for {cache_key}, skipping")
            _cache_stats.record_dedup_hit()
            return

        # Mark as in progress
        _background_refresh_in_progress.add(cache_key)

    def background_refresh():
        try:
            logger.info(f"[BACKGROUND-REFRESH] Starting refresh for {cache_key}")
            fresh_data = fetch_function()

            # Timestamp ve metadata ekle
            if isinstance(fresh_data, dict):
                fresh_data['_cached_at'] = time.time()
                # CRITICAL: Keep _smart_ttl if already calculated by fetch_function
                if '_smart_ttl' not in fresh_data or fresh_data.get('_smart_ttl') is None:
                    fresh_data['_smart_ttl'] = ttl

            # Cache'e yaz
            serialized = _safe_json_serialize(fresh_data)
            cache_instance.set(cache_key, serialized, timeout=86400)  # 24 saat max age

            _cache_stats.record_background_refresh(success=True)
            logger.info(f"[BACKGROUND-REFRESH] Successfully refreshed {cache_key}")

        except Exception as e:
            _cache_stats.record_background_refresh(success=False)
            logger.warning(f"[BACKGROUND-REFRESH] Failed to refresh {cache_key}: {e}")

        finally:
            # Always remove from in-progress set
            with _background_refresh_lock:
                _background_refresh_in_progress.discard(cache_key)

    # Thread başlat (daemon=True: uygulama kapanınca otomatik kapansın)
    thread = threading.Thread(target=background_refresh, daemon=True, name=f"bg_refresh_{cache_key[:20]}")
    thread.start()


def cache_with_stale_fallback(cache_key_func: Callable,
                               fresh_ttl: int = 180,
                               stale_ttl: int = 3600):
    """
    Decorator for stale-while-revalidate caching pattern.

    This decorator wraps a function with stale-while-revalidate caching:
    - Checks fresh cache first
    - Falls back to stale cache if upstream fails
    - Automatically refreshes both caches on success

    Args:
        cache_key_func: Function that takes function args and returns cache key
        fresh_ttl: Fresh cache timeout in seconds (default: 180)
        stale_ttl: Stale cache timeout in seconds (default: 3600)

    Returns:
        Decorated function with stale-while-revalidate caching

    Example:
        >>> @cache_with_stale_fallback(
        ...     cache_key_func=lambda match_id: f'match:{match_id}',
        ...     fresh_ttl=180,
        ...     stale_ttl=3600
        ... )
        ... def fetch_match_data(match_id):
        ...     return {...}
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Get cache instance from global state
            from routes.utils import _cache_instance

            if _cache_instance is None:
                # No cache available - call function directly
                logger.warning(f"[CACHE-WARN] Cache not initialized, calling {func.__name__} directly")
                return func(*args, **kwargs)

            # Generate cache key
            cache_key = cache_key_func(*args, **kwargs)

            # Use get_with_stale_fallback
            return get_with_stale_fallback(
                cache_instance=_cache_instance,
                cache_key=cache_key,
                fetch_function=lambda: func(*args, **kwargs),
                fresh_ttl=fresh_ttl,
                stale_ttl=stale_ttl
            )

        return wrapper
    return decorator
