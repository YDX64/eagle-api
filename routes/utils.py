"""
Shared utility functions for routes package
"""
import json
import logging
import pickle
import random
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# Import required modules
from parsers import (
    MatchDateParser,
    parse_player_list,
    parse_standings_table,
    parse_match_list_table,
    parse_standings,
    parse_injury_suspension,
    parse_last_match_lineups,
    parse_fixture,
    parse_match_info,
    parse_h2h_details,
    parse_first_half_odds,
    parse_correct_score_odds,
    parse_double_chance_odds,
    parse_corner_odds,
    parse_odds_comp
)
from http_client import (
    fetch_all_urls_sync,
    fetch_date_data_simple
)
from models import APIError
from app_config import current_config
from cache_utils import (
    get_with_stale_fallback,
    get_with_background_refresh,
    _global_deduplicator,
    normalize_match_status,
    get_smart_ttl_for_status,
    get_cache_stats
)

# Global cache instance (app başlatıldıktan sonra set edilecek)
_cache_instance = None

def set_cache_instance(cache):
    """Set cache instance from app.py after initialization"""
    global _cache_instance
    _cache_instance = cache
    logger = logging.getLogger(__name__)
    logger.debug(f"[CACHE-INIT] Cache instance set: {type(cache)}, has 'get': {hasattr(cache, 'get')}, has 'set': {hasattr(cache, 'set')}")


def get_smart_cache_timeout(data_type='default', match_status=None, date_str=None):
    """
    Veri tipine göre akıllı cache timeout döndür

    Args:
        data_type: 'match', 'h2h', 'odds', 'date_matches', 'default'
        match_status: 'live', 'finished', 'not_started' (opsiyonel)
        date_str: Tarih string (date_matches için)

    Returns:
        int: Cache timeout saniye cinsinden
    """
    from datetime import datetime, timedelta

    # Match data
    if data_type == 'match':
        if match_status == 'finished':
            return 86400  # 1 gün (bitmiş maç, değişmez)
        elif match_status == 'live':
            return 60  # 1 dakika (live maç, sık güncelleme)
        else:
            return 300  # 5 dakika (başlamamış maç)

    # H2H data (tarihsel veri, nadiren değişir)
    elif data_type == 'h2h':
        return 86400  # 1 gün

    # Odds data (bahis oranları, sık değişir)
    # P0: Increased from 5 minutes to 15 minutes to reduce timeout rate
    elif data_type == 'odds':
        return 900  # 15 dakika (was 5)

    # Date matches (maç listesi nadiren değişir)
    elif data_type == 'date_matches':
        if date_str:
            try:
                target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                today = datetime.now().date()

                if target_date < today:
                    # Geçmiş tarih (değişmez)
                    return 86400  # 24 saat
                elif target_date == today:
                    # Bugün (maç saatleri nadiren değişir)
                    return 1800  # 30 dakika
                else:
                    # Gelecek tarih
                    return 7200  # 2 saat
            except:
                pass
        return 1800  # Default 30 dakika

    # Default
    else:
        return 300  # 5 dakika


def cache_wrapper(cache_key, fetch_function, use_cache=True, cache_timeout=1800, enable_stale=True):
    """
    Generic cache wrapper with TRUE stale-while-revalidate pattern (background refresh)

    Args:
        cache_key: Unique cache key for the data
        fetch_function: Callable that returns data when cache misses
        use_cache: Cache kullanılsın mı (varsayılan: True)
        cache_timeout: Fresh TTL saniye cinsinden (varsayılan: 1800 = 30 dakika)
        enable_stale: Stale-while-revalidate pattern kullan (varsayılan: True)

    Returns:
        Data with cache metadata
    """
    if not use_cache:
        data = fetch_function()
        if isinstance(data, dict):
            data['cached'] = False
            data['cache_hit'] = False
        return data

    logger = logging.getLogger(__name__)

    # Cache instance yoksa direkt fetch
    if _cache_instance is None:
        logger.warning(f"[CACHE-WARN] Cache not initialized, fetching directly for key: {cache_key}")
        data = fetch_function()
        if isinstance(data, dict):
            data['cached'] = False
            data['cache_hit'] = False
        return data

    # Use TRUE stale-while-revalidate pattern if enabled (background refresh)
    if enable_stale:
        try:
            # Wrap the cache function with deduplication to prevent concurrent identical fetches
            def cache_with_dedup():
                return get_with_background_refresh(
                    cache_instance=_cache_instance,
                    cache_key=cache_key,
                    fetch_function=fetch_function,
                    fresh_ttl=cache_timeout
                )

            # Use deduplicator to prevent duplicate concurrent requests
            return _global_deduplicator.deduplicate(
                key=f"cache:{cache_key}",  # Unique dedup key
                fetch_function=cache_with_dedup,
                ttl=60  # Wait up to 60s for pending request
            )
        except APIError:
            # Re-raise APIError (404, 504, etc.)
            raise
        except Exception as e:
            logger.warning(f"[CACHE-ERROR] Stale cache strategy failed for {cache_key}: {e}, using direct fetch")
            data = fetch_function()
            if isinstance(data, dict):
                data['cached'] = False
                data['cache_hit'] = False
            return data

    # Original cache logic (no stale fallback)
    try:
        # Cache'den kontrol et
        cached_data = _cache_instance.get(cache_key)
        if cached_data:
            # Pickle ile deserialize et
            data = pickle.loads(cached_data)
            if isinstance(data, dict):
                data['cached'] = True
                data['cache_hit'] = True
            logger.debug(f"[CACHE-HIT] Cache hit for key: {cache_key}")
            return data

        # Cache MISS - fetch ve cache'le
        logger.debug(f"[CACHE-MISS] Cache miss for key: {cache_key}, fetching fresh data")
        data = fetch_function()

        # Pickle ile serialize et ve cache'le
        try:
            serialized_data = pickle.dumps(data)
            _cache_instance.set(cache_key, serialized_data, timeout=cache_timeout)
            logger.debug(f"[CACHE-SET] Cached data for key: {cache_key} (timeout: {cache_timeout}s)")
        except Exception as cache_error:
            logger.warning(f"[CACHE-ERROR] Failed to cache key {cache_key}: {str(cache_error)}")

        if isinstance(data, dict):
            data['cached'] = False
            data['cache_hit'] = False
        return data

    except APIError:
        # Re-raise APIError (404, 504, etc.)
        raise
    except Exception as e:
        logger.warning(f"[CACHE-ERROR] Cache error for key {cache_key}: {str(e)}, falling back to direct fetch")
        import traceback
        logger.debug(f"[CACHE-ERROR] Cache error traceback: {traceback.format_exc()}")
        data = fetch_function()
        if isinstance(data, dict):
            data['cached'] = False
            data['cache_hit'] = False
        return data


def fetch_match_data_with_analysis_cached(match_id, use_cache=True, cache_timeout=None):
    """
    PERFORMANCE OPTIMIZATION: Fetch match data WITH analysis cached together

    This function caches both raw data AND analysis results together,
    eliminating ~1-2 seconds of analysis overhead on cache hits.

    SMART TTL BASED ON MATCH STATUS:
    - finished (FT): 24 hours (data never changes)
    - live (HT, 45'): 1 minute (real-time updates needed)
    - not_started: 5 minutes (pre-match updates)

    Args:
        match_id: Match ID
        use_cache: Cache kullanılsın mı (varsayılan: True)
        cache_timeout: Cache süresi (None=akıllı timeout kullan)

    Returns:
        Dict with match data + analysis + normalized status
    """
    logger = logging.getLogger(__name__)
    cache_key = f'match_with_analysis:{match_id}'

    # Cache kullanılmıyorsa direkt çek ve analyze et
    if not use_cache:
        data = fetch_match_data_sync(match_id)
        data = _add_analysis_to_match_data(data)
        data['cached'] = False
        data['cache_hit'] = False
        return data

    # Cache instance yoksa direkt fetch
    if _cache_instance is None:
        logger.warning(f"[CACHE-WARN] Cache not initialized for match:{match_id}")
        data = fetch_match_data_sync(match_id)
        data = _add_analysis_to_match_data(data)
        data['cached'] = False
        data['cache_hit'] = False
        return data

    # Variable to store calculated smart TTL for passing to cache function
    calculated_smart_ttl = [None]  # Using list to allow modification in nested function

    # Wrapper function for stale-while-revalidate
    def fetch_analyze_and_determine_ttl():
        """Fetch data, analyze, and determine appropriate cache timeout"""
        data = fetch_match_data_sync(match_id)

        # Add analysis (this is the expensive part we're caching)
        data = _add_analysis_to_match_data(data)

        # Extract status for normalization
        # Status can be in multiple locations depending on data source:
        # 1. match_info.score_info.status (HTML parse result)
        # 2. match_info.status (direct)
        # 3. match_info.match_state (JSON API: -1=finished, 0=not_started, 1/2/3=live)
        match_info = data.get('match_info', {})
        score_info = match_info.get('score_info', {})

        # Priority: score_info.status > match_info.status
        raw_status = score_info.get('status', '') or match_info.get('status', '')
        match_state = match_info.get('match_state')  # From JSON API (-1, 0, 1, 2, 3)

        # CRITICAL: Normalize status from raw nowgoal values to standard values
        # Pass score_info to detect live matches when status is empty but score exists
        normalized_status = normalize_match_status(
            raw_status=raw_status,
            match_state=match_state,
            score_info=score_info
        )

        # Store normalized status in data for debugging and cache TTL
        data['_normalized_status'] = normalized_status

        # Calculate smart TTL based on normalized status
        smart_ttl = cache_timeout if cache_timeout else get_smart_ttl_for_status(normalized_status)
        data['_smart_ttl'] = smart_ttl

        logger.info(f"[SMART-TTL] Match {match_id}: raw_status='{raw_status}', match_state={match_state}, "
                    f"normalized='{normalized_status}', TTL={smart_ttl}s")

        # Store for outer scope
        calculated_smart_ttl[0] = smart_ttl

        return data

    # First check if we have cached data to determine its TTL
    # If not, we'll use default and let the fetch function calculate the real TTL
    default_ttl = cache_timeout if cache_timeout else 300  # 5 minutes default for first fetch

    try:
        data = get_with_background_refresh(
            cache_instance=_cache_instance,
            cache_key=cache_key,
            fetch_function=fetch_analyze_and_determine_ttl,
            fresh_ttl=default_ttl,
            dynamic_ttl=calculated_smart_ttl[0]  # Will be None for first call, set by data's _smart_ttl after
        )

        # The actual smart TTL is stored in data['_smart_ttl'] and used by cache internally

        # Remove internal fields before returning (optional, keep _normalized_status for debugging)
        if isinstance(data, dict):
            # Keep _normalized_status for debugging but remove internal TTL field
            data.pop('_cache_timeout', None)

        return data

    except APIError:
        raise
    except Exception as e:
        logger.warning(f"[CACHE-ERROR] Cache infrastructure failed for match:{match_id}: {e}, trying direct fetch")
        data = fetch_match_data_sync(match_id)
        data = _add_analysis_to_match_data(data)
        data['cached'] = False
        data['cache_hit'] = False
        data['stale'] = False
        return data


def _add_analysis_to_match_data(data):
    """
    Helper function to add analysis to match data using PARALLEL execution.

    Independent analysis functions (1-5) run in parallel using ThreadPoolExecutor.
    Dependent functions (6-7) run sequentially after parallel phase completes.

    Performance improvement: ~360ms (from ~580ms to ~220ms)

    Args:
        data: Raw match data from fetch_match_data_sync

    Returns:
        Data with 'analysis' field added
    """
    # Skip if already analyzed
    if data.get('analysis'):
        return data

    logger = logging.getLogger(__name__)

    from analysis import (
        analyze_correct_score_predictions,
        analyze_h2h_details,
        analyze_team_performance,
        analyze_odds_trends,
        calculate_final_predictions,
        generate_betting_tips,
        compute_spotlight_stats,
    )
    from analysis.odds_analysis import analyze_odds_comprehensive
    from analysis.poisson_model import analyze_poisson
    from analysis.odds_movement import analyze_odds_movement_predictions
    from analysis.streak_detector import detect_streaks

    # Extract data needed for analysis
    h2h_details_backup = data.get('h2h_details')
    correct_score_odds = data.get('correct_score_odds')
    first_half_odds = data.get('first_half_odds')
    odds_comp = data.get('odds_comp')

    # Prepare odds_data for trends analysis
    odds_data = {
        'odds_comparison': odds_comp.get('odds_comparison', []) if odds_comp else [],
        'first_half_odds': first_half_odds or {}
    }

    # Define independent analysis tasks (can run in parallel)
    parallel_tasks = []

    if correct_score_odds or data.get('match_info'):
        parallel_tasks.append(('correct_score', analyze_correct_score_predictions, data))

    if h2h_details_backup:
        parallel_tasks.append(('h2h', analyze_h2h_details, data))

    if data.get('match_info'):
        parallel_tasks.append(('team_performance', analyze_team_performance, data))

    if odds_comp:
        parallel_tasks.append(('odds_comprehensive', analyze_odds_comprehensive, odds_comp))

    if odds_comp or first_half_odds:
        parallel_tasks.append(('odds_trends', analyze_odds_trends, odds_data))

    # EAGLE: Poisson goal model (needs h2h data)
    if h2h_details_backup and data.get('match_info'):
        parallel_tasks.append(('poisson', analyze_poisson, data))

    # EAGLE: Odds movement predictions (needs odds data)
    if odds_comp or first_half_odds:
        parallel_tasks.append(('odds_movement', analyze_odds_movement_predictions, odds_data))

    # EAGLE: Streak detection (needs h2h data)
    if h2h_details_backup:
        parallel_tasks.append(('streaks', detect_streaks, data))

    if h2h_details_backup or odds_comp:
        parallel_tasks.append(('spotlight', compute_spotlight_stats, data))

    # Run independent analyses in PARALLEL
    analysis_result = {}

    if parallel_tasks:
        # Use ThreadPoolExecutor for parallel execution
        with ThreadPoolExecutor(max_workers=6, thread_name_prefix='analysis') as executor:
            # Submit all tasks
            future_to_name = {
                executor.submit(func, arg): name
                for name, func, arg in parallel_tasks
            }

            # Collect results as they complete
            for future in as_completed(future_to_name):
                task_name = future_to_name[future]
                try:
                    result = future.result(timeout=10)  # 10s timeout per task
                    if result:
                        analysis_result.update(result)
                except Exception as e:
                    logger.warning(f"{task_name} analysis failed: {e}")

    # Run DEPENDENT analyses sequentially (they need results from parallel phase)

    # 6. Final predictions (depends on analysis_result from parallel tasks)
    if analysis_result:
        try:
            analysis_result.update(calculate_final_predictions(analysis_result))
        except Exception as e:
            logger.warning(f"Final predictions failed: {e}")

    # 7. Betting tips (depends on analysis_result)
    if analysis_result:
        try:
            data['analysis'] = analysis_result  # Tips need analysis in data
            analysis_result.update(generate_betting_tips(data))
        except Exception as e:
            logger.warning(f"Betting tips generation failed: {e}")

    # Store analysis in data
    data['analysis'] = analysis_result
    data['analysis_cached'] = data.get('cached', False)

    return data


def fetch_match_data_cached(match_id, use_cache=True, cache_timeout=None):
    """
    Cached version of match data fetching with stale-while-revalidate pattern.

    This function implements high-availability caching:
    - Returns stale cache immediately if fresh cache expired
    - Falls back to stale cache if upstream fails
    - Automatically refreshes both fresh and stale caches on success

    Args:
        match_id: Match ID
        use_cache: Cache kullanılsın mı (varsayılan: True)
        cache_timeout: Cache süresi (None=akıllı timeout kullan)
    """
    logger = logging.getLogger(__name__)
    cache_key = f'match_data:{match_id}'

    # Cache kullanılmıyorsa direkt çek
    if not use_cache:
        data = fetch_match_data_sync(match_id)
        if isinstance(data, dict):
            data['cached'] = False
            data['cache_hit'] = False
        return data

    # Cache instance yoksa direkt fetch
    if _cache_instance is None:
        logger.warning(f"[CACHE-WARN] Cache not initialized for match:{match_id}")
        data = fetch_match_data_sync(match_id)
        if isinstance(data, dict):
            data['cached'] = False
            data['cache_hit'] = False
        return data

    # Wrapper function for stale-while-revalidate
    def fetch_and_determine_ttl():
        """Fetch data and determine appropriate cache timeout"""
        data = fetch_match_data_sync(match_id)

        # Match status'u bul (akıllı timeout için)
        match_info = data.get('match_info', {})
        status = match_info.get('status', 'unknown')

        # Akıllı timeout (eğer manuel verilmemişse)
        determined_timeout = cache_timeout
        if determined_timeout is None:
            determined_timeout = get_smart_cache_timeout('match', status)

        # Store timeout in data for get_with_stale_fallback to use
        data['_cache_timeout'] = determined_timeout

        return data

    # Use stale-while-revalidate pattern
    # Fresh TTL: Smart timeout based on match status
    # Stale TTL: 1 hour (fallback for upstream failures)
    fresh_ttl = cache_timeout if cache_timeout else 1800  # Default 30 minutes (optimized)
    stale_ttl = 3600  # 1 hour backup

    try:
        data = get_with_stale_fallback(
            cache_instance=_cache_instance,
            cache_key=cache_key,
            fetch_function=fetch_and_determine_ttl,
            fresh_ttl=fresh_ttl,
            stale_ttl=stale_ttl
        )

        # If we got a cache timeout from fetch, use it for next refresh
        if isinstance(data, dict) and '_cache_timeout' in data:
            # Remove internal field before returning
            data.pop('_cache_timeout', None)

        return data

    except APIError:
        # Re-raise APIError (404, 504, 503, etc.) - these are valid upstream errors
        raise
    except Exception as e:
        # Cache infrastructure error (not upstream error) - try direct fetch
        logger.warning(f"[CACHE-ERROR] Cache infrastructure failed for match:{match_id}: {e}, trying direct fetch")
        data = fetch_match_data_sync(match_id)
        if isinstance(data, dict):
            data['cached'] = False
            data['cache_hit'] = False
            data['stale'] = False
        return data


def fetch_h2h_data_cached(match_id, use_cache=True, cache_timeout=None):
    """
    Cached version of H2H data fetching.

    Optimizasyon sırası:
    1. h2h_data:{id} cache'ini kontrol et (en hızlı)
    2. match_with_analysis:{id} cache'ini kontrol et (cross-cache reuse)
       → /match/{id} zaten çektiyse H2H için ek fetch yapmaya gerek yok
    3. Hiçbiri yoksa fetch_h2h_data_only() ile upstream'den çek (1 URL)
    """
    logger = logging.getLogger(__name__)
    cache_key = f'h2h_data:{match_id}'

    if cache_timeout is None:
        cache_timeout = get_smart_cache_timeout('h2h')

    # ── CROSS-CACHE: match_with_analysis varsa H2H verisini oradan al ────────
    if use_cache and _cache_instance is not None:
        try:
            raw = _cache_instance.get(f'match_with_analysis:{match_id}')
            if raw:
                full = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
                h2h = full.get('h2h_details') if isinstance(full, dict) else None
                if h2h and not (isinstance(h2h, dict) and h2h.get('error')):
                    logger.debug(f"♻️  H2H [{match_id}]: reused from match_with_analysis cache")
                    return {
                        'match_id':   match_id,
                        'match_info': full.get('match_info', {}),
                        'h2h_details': h2h,
                        'fixture':    full.get('fixture', {}),
                        'timestamp':  full.get('timestamp'),
                        'cached':     True,
                        'cache_hit':  True,
                        'stale':      full.get('stale', False),
                        'cache_source': 'match_with_analysis',
                        'optimized':  True,
                        'optimization': 'cross_cache_reuse',
                    }
        except Exception as e:
            logger.debug(f"Cross-cache H2H check failed for {match_id}: {e}")

    return cache_wrapper(
        cache_key=cache_key,
        fetch_function=lambda: fetch_h2h_data_only(match_id),
        use_cache=use_cache,
        cache_timeout=cache_timeout,
    )


def fetch_odds_data_cached(match_id, use_cache=True, cache_timeout=None):
    """
    Cached version of odds data fetching.

    Optimizasyon sırası:
    1. odds_data:{id} cache'ini kontrol et
    2. match_with_analysis:{id} cache'ini kontrol et (cross-cache reuse)
       → /match/{id} zaten corner+double_chance dahil tüm odds'ları çektiyse
         ek fetch yapmaya gerek yok
    3. Hiçbiri yoksa fetch_odds_data_only() ile upstream'den çek (5 URL)
    """
    logger = logging.getLogger(__name__)
    cache_key = f'odds_data:{match_id}'

    if cache_timeout is None:
        cache_timeout = get_smart_cache_timeout('odds')

    # ── CROSS-CACHE: match_with_analysis'tan odds verisini çek ───────────────
    # NOT: fetch_match_data_sync() artık corner_odds ve double_chance_odds
    # çekmiyor. Dolayısıyla bu cross-cache yalnızca doğrudan odds_comp,
    # correct_score_odds ve first_half_odds içerdiğinde tam reuse sağlar.
    # corner_odds / double_chance_odds için yine fetch_odds_data_only() çalışır.
    if use_cache and _cache_instance is not None:
        try:
            raw = _cache_instance.get(f'match_with_analysis:{match_id}')
            if raw:
                full = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
                if isinstance(full, dict):
                    odds_comp   = full.get('odds_comp')
                    corner      = full.get('corner_odds')
                    double_ch   = full.get('double_chance_odds')
                    correct_sc  = full.get('correct_score_odds')
                    first_half  = full.get('first_half_odds')

                    def _ok(v):
                        """Değer var mı ve hata içermiyor mu?"""
                        return v and not (isinstance(v, dict) and v.get('error'))

                    if _ok(odds_comp) and _ok(corner) and _ok(double_ch):
                        # Tüm odds alanları match_with_analysis'ta mevcut → tam reuse
                        logger.debug(f"♻️  Odds [{match_id}]: full reuse from match_with_analysis cache")
                        return {
                            'match_id': match_id,
                            'odds_data': {
                                'corner_odds':       corner       or {},
                                'correct_score_odds': correct_sc or {},
                                'double_chance_odds': double_ch  or {},
                                'first_half_odds':   first_half  or {},
                                'odds_comp':         odds_comp   or {},
                            },
                            'timestamp':  full.get('timestamp'),
                            'cached':     True,
                            'cache_hit':  True,
                            'stale':      full.get('stale', False),
                            'cache_source': 'match_with_analysis',
                            'optimized':  True,
                            'optimization': 'cross_cache_reuse',
                        }
        except Exception as e:
            logger.debug(f"Cross-cache Odds check failed for {match_id}: {e}")

    def fetch_and_format_odds():
        # ✅ OPTIMIZED: Only fetch odds data (5 URLs, skip H2H)
        odds_data = fetch_odds_data_only(match_id)

        # Format for backward compatibility
        return {
            'match_id': match_id,
            'odds_data': {
                'corner_odds': odds_data.get('corner_odds', {}),
                'correct_score_odds': odds_data.get('correct_score_odds', {}),
                'double_chance_odds': odds_data.get('double_chance_odds', {}),
                'first_half_odds': odds_data.get('first_half_odds', {}),
                'odds_comp': odds_data.get('odds_comp', {})
            },
            'timestamp': odds_data.get('timestamp'),
            'fetch_times': odds_data.get('fetch_times', {}),
            'sources_used': odds_data.get('sources_used', {}),
            'optimized': odds_data.get('optimized', False),
            'optimization': odds_data.get('optimization', '')
        }

    return cache_wrapper(
        cache_key=cache_key,
        fetch_function=fetch_and_format_odds,
        use_cache=use_cache,
        cache_timeout=cache_timeout
    )


def fetch_date_matches_cached(date_str, sort_by_time=True, use_cache=True, cache_timeout=None):
    """
    Cached version of date-based match list fetching

    Args:
        date_str: Date string (YYYY-MM-DD)
        sort_by_time: Maçları saat sırasına göre sırala
        use_cache: Cache kullanılsın mı (varsayılan: True)
        cache_timeout: Cache süresi (None=akıllı timeout)
    """
    # Akıllı timeout (bugün=3dk, geçmiş=1saat, gelecek=10dk)
    if cache_timeout is None:
        cache_timeout = get_smart_cache_timeout('date_matches', date_str=date_str)

    # Sort parametresi cache key'e dahil (farklı sort parametreleri farklı cache'ler)
    cache_key = f'matches_date:{date_str}:sorted_{sort_by_time}'

    def fetch_date_matches():
        logger = logging.getLogger(__name__)
        # API URL'ini oluştur - SourceManager'dan primary source kullan
        from http_client import get_source_manager
        source_manager = get_source_manager()
        base_url = source_manager.current_primary
        endpoints = current_config.NOWGOAL_ENDPOINTS
        api_url = f"{base_url}{endpoints['matches_by_date'].format(date=date_str, random=random.random())}"

        logger.debug(f"[FETCH] Fetching date matches for {date_str}")
        logger.debug(f"[HTTP] Request URL: {api_url}")

        # Veriyi çek
        from parsers import MatchDateParser
        date_parser = MatchDateParser()

        try:
            response_text = fetch_date_data_simple(api_url)
            logger.debug(f"[HTTP] Response received, length: {len(response_text) if response_text else 0} characters")

            # İlk 500 karakteri log'a yaz
            if response_text:
                logger.debug(f"[HTTP] Response preview: {response_text[:500]}")
            else:
                logger.warning("[ERROR] Empty response received!")

        except Exception as e:
            logger.warning(f"[ERROR] Failed to fetch date data: {str(e)}")
            raise

        parsed_data = date_parser.parse_date_response(response_text)
        logger.debug(f"[PARSE] Parsed data: {len(parsed_data.get('matches', [])) if parsed_data else 0} matches found")

        if not parsed_data:
            return None

        # Maçları formatla
        matches = []
        if 'matches' in parsed_data:
            for match in parsed_data['matches']:
                # Lig bilgisini al
                league_id = match.get('league_id')
                league_info = parsed_data['leagues'].get(str(league_id), {}) or parsed_data['leagues'].get(league_id, {})

                match_datetime = match['match_time']  # orijinal datetime objesi

                # Türkiye saati için 3 saat ekle
                from datetime import timedelta
                adjusted_datetime = match_datetime + timedelta(hours=3) if match_datetime else None

                matches.append({
                    'match_id': match['match_id'],
                    'home_team': match['home_team'],
                    'away_team': match['away_team'],
                    'match_date': adjusted_datetime.date().isoformat() if adjusted_datetime else None,
                    'match_time': adjusted_datetime.strftime('%H:%M') if adjusted_datetime else None,
                    'league': {
                        'id': league_id,
                        'name': league_info.get('league_name', 'Unknown'),
                        'code': league_info.get('league_code', '')
                    },
                    '_sort_datetime': adjusted_datetime  # sıralama için
                })

        # Saat sırasına göre sırala
        if sort_by_time:
            matches.sort(key=lambda x: x.get('_sort_datetime') or datetime.max)

        # _sort_datetime alanını kaldır
        for match in matches:
            match.pop('_sort_datetime', None)

        return {
            'date': date_str,
            'matches': matches,
            'count': len(matches),
            'timestamp': datetime.utcnow().isoformat()
        }

    return cache_wrapper(
        cache_key=cache_key,
        fetch_function=fetch_date_matches,
        use_cache=use_cache,
        cache_timeout=cache_timeout
    )


def _build_match_info_from_date_cache(match_id):
    """
    Fallback: Build minimal match_info from the cached date-based match list.
    Used when the h2h HTML page returns 404 but the match exists in the daily list.
    """
    logger = logging.getLogger(__name__)
    if _cache_instance is None:
        return None

    # Try today, yesterday, tomorrow caches
    from datetime import date, timedelta
    today = date.today()
    dates_to_check = [today, today - timedelta(days=1), today + timedelta(days=1)]

    for check_date in dates_to_check:
        date_str = check_date.isoformat()
        for sort_val in [True, False]:
            cache_key = f'matches_date:{date_str}:sorted_{sort_val}'
            try:
                cached_data = _cache_instance.get(cache_key)
                if not cached_data:
                    continue
                # Cache stores JSON string - deserialize if needed
                if isinstance(cached_data, (str, bytes)):
                    try:
                        cached_data = json.loads(cached_data)
                    except (json.JSONDecodeError, TypeError):
                        continue
                if not isinstance(cached_data, dict) or 'matches' not in cached_data:
                    continue
                for match in cached_data['matches']:
                    if match.get('match_id') == match_id:
                        logger.info(f"Found match {match_id} in date cache ({date_str})")
                        return {
                            'home_team': match.get('home_team', 'Unknown'),
                            'away_team': match.get('away_team', 'Unknown'),
                            'league': match.get('league', {}).get('name', ''),
                            'league_id': match.get('league', {}).get('id'),
                            'match_date': match.get('match_date', ''),
                            'match_time': match.get('match_time', ''),
                            'home_logo': '',
                            'away_logo': '',
                            'score_info': {},
                            '_source': 'date_cache_fallback'
                        }
            except Exception:
                continue
    return None


def fetch_match_data_sync(match_id):
    """
    Synchronous match data fetching with multi-source failover support

    This function now uses the new multi-source failover system to automatically
    retry failed requests with alternative data sources.

    NEW: Includes invalid match caching to prevent repeated upstream requests
    for matches that don't exist.
    """
    logger = logging.getLogger(__name__)

    # Validate match_id
    if not isinstance(match_id, int) or match_id <= 0:
        raise APIError("Invalid match ID", 400)

    # ============================================================
    # TASK 1: Check if this match is known to be invalid
    # ============================================================
    if _cache_instance is not None:
        invalid_cache_key = f'invalid_match:{match_id}'
        try:
            is_invalid = _cache_instance.get(invalid_cache_key)
            if is_invalid:
                # P0: Changed from info to debug to reduce log spam
                logger.debug(f"⚠️ Match {match_id} is known invalid (cached 404)")
                # Return 404 immediately without upstream calls
                raise APIError("Match not found", 404)
        except Exception as cache_err:
            logger.debug(f"Could not check invalid cache: {cache_err}")

    # Define endpoint templates (NOT full URLs - failover will add base URLs)
    endpoints = current_config.NOWGOAL_ENDPOINTS

    # NEW FORMAT: {key: (endpoint_template, match_id)}
    # NOT: corner_odds ve double_chance_odds buradan kaldırıldı.
    # Analysis pipeline'ında kullanılmıyorlar ve /match/{id}/odds endpoint'i
    # zaten fetch_odds_data_only() ile bunları kendi başına çekiyor.
    urls = {
        "h2h_details":        (endpoints['match_h2h'], match_id),
        "correct_score_odds": (endpoints['odds_correct_score'], match_id),
        "odds_comp":          (endpoints['odds_comp'], match_id),
        "first_half_odds":    (endpoints['odds_first_half'].replace('{random}', str(random.random())), match_id),
    }

    logger = logging.getLogger(__name__)
    logger.info(f"🔍 Fetching match data for match ID: {match_id} with multi-source failover")

    # Fetch with multi-source failover support
    try:
        results = fetch_all_urls_sync(urls, match_id=match_id, use_failover=True)

        data = {
            'match_id': match_id,
            'timestamp': datetime.utcnow().isoformat(),
            'fetch_times': {},
            'sources_used': {},  # NEW: Track which source was used for each data type
            'cached': False
        }

        # Process results (now includes source_used - 5 values instead of 4)
        for result in results:
            if isinstance(result, Exception):
                # Handle exceptions from asyncio.gather
                logger.warning(f"Exception in result: {str(result)}")
                data['general_error'] = {"error": f"Request failed with exception: {str(result)}"}
                continue

            # Unpack result - now includes source_used
            key, content, content_type, fetch_time, source_used = result
            data['fetch_times'][key] = fetch_time
            if source_used:
                data['sources_used'][key] = source_used

            if content_type == 'error':
                # Log error but continue (graceful degradation)
                logger.warning(f"⚠️ Error fetching {key}: {content.get('error', 'Unknown error')}")
                data[key] = content
            elif content_type == 'html' and key == 'h2h_details':
                try:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(content, 'lxml')
                    data['match_info'] = parse_match_info(soup)
                    data['fixture'] = parse_fixture(soup)
                    data['h2h_details'] = parse_h2h_details(soup)
                except Exception as e:
                    logger.warning(f"Error parsing HTML for {key}: {str(e)}")
                    data[key] = {"error": f"Failed to parse HTML: {str(e)}"}
            elif content_type == 'json':
                # Parse specific JSON data types
                if key == 'correct_score_odds':
                    try:
                        data[key] = parse_correct_score_odds(content)
                    except Exception as e:
                        logger.warning(f"Error parsing correct score odds: {str(e)}")
                        data[key] = {"error": f"Failed to parse correct score odds: {str(e)}"}
                elif key == 'first_half_odds':
                    try:
                        data[key] = parse_first_half_odds(content)
                    except Exception as e:
                        logger.warning(f"Error parsing first half odds: {str(e)}")
                        data[key] = {"error": f"Failed to parse first half odds: {str(e)}"}
                elif key == 'odds_comp':
                    try:
                        data[key] = parse_odds_comp(content)
                    except Exception as e:
                        logger.warning(f"Error parsing odds comparison: {str(e)}")
                        data[key] = {"error": f"Failed to parse odds comparison: {str(e)}"}
                else:
                    data[key] = content
            else:
                data[key] = {"error": f"Unknown content type: {content_type}"}

        # ===================================================================
        # GRACEFUL DEGRADATION: Check required vs optional fields
        # ===================================================================
        required_fields = ['match_info']  # Absolute minimum required
        optional_fields = ['h2h_details', 'correct_score_odds', 'first_half_odds', 'odds_comp', 'fixture']

        # Check if we have minimum required data
        missing_required = []
        for field in required_fields:
            if field not in data or (isinstance(data.get(field), dict) and 'error' in data.get(field, {})):
                missing_required.append(field)

        # FALLBACK: If match_info is missing (h2h page 404), try to build it from
        # the cached date-based match list. This handles cases where the h2h page
        # doesn't exist but the match is real (e.g. upstream redirect to unknown subdomain).
        if 'match_info' in missing_required:
            fallback_info = _build_match_info_from_date_cache(match_id)
            if fallback_info:
                data['match_info'] = fallback_info
                missing_required.remove('match_info')
                logger.info(f"✅ Built match_info from date cache fallback for match {match_id}")

        if missing_required:
            # Collect error details from all failed sources
            error_details = []
            all_404 = True  # Track if all errors are 404s

            for result in results:
                if isinstance(result, tuple) and len(result) >= 3:
                    key, content, content_type = result[0], result[1], result[2]
                    if content_type == 'error' and isinstance(content, dict):
                        error_msg = content.get('error', 'Unknown error')
                        error_details.append(f"{key}: {error_msg}")

                        # Check if this is NOT a 404 error
                        if '404' not in error_msg and 'not found' not in error_msg.lower():
                            all_404 = False

            error_summary = "; ".join(error_details) if error_details else "All upstream sources failed"

            # ============================================================
            # TASK 1 & 2: Cache invalid matches and return proper status code
            # ============================================================
            if all_404:
                # All sources returned 404 - match doesn't exist
                logger.warning(f"🔒 Caching match {match_id} as invalid (all sources returned 404)")

                # Cache as invalid for 24 hours (P0: reduced log spam)
                if _cache_instance is not None:
                    try:
                        invalid_cache_key = f'invalid_match:{match_id}'
                        _cache_instance.set(invalid_cache_key, '1', timeout=86400)  # 24 hours
                        logger.info(f"✅ Cached invalid match {match_id} for 24 hours")
                    except Exception as cache_err:
                        logger.warning(f"Failed to cache invalid match: {cache_err}")

                # Return 404 Not Found (not 502)
                raise APIError("Match not found", 404)

            # Not all 404s - check if all timeouts
            all_timeout = all('timeout' in err.lower() or 'timed out' in err.lower()
                            for err in error_details)

            if all_timeout:
                # All sources timed out - Gateway Timeout
                logger.warning(f"⏱️ All sources timed out for match {match_id}")
                raise APIError("Upstream sources are experiencing delays. Please try again in a moment.", 504)

            # Add context for Sentry (will be attached to the exception below)
            try:
                import sentry_sdk
                sentry_sdk.set_context("match_fetch_failure", {
                    'match_id': match_id,
                    'missing_fields': missing_required,
                    'error_details': error_details,
                    'sources_tried': data.get('sources_used', {}),
                    'fetch_times': data.get('fetch_times', {}),
                    'all_404': all_404,
                    'all_timeout': all_timeout
                })
            except:
                pass

            # Generic upstream failure - Service Unavailable (not 502)
            raise APIError("Upstream data sources are temporarily unavailable", 503)

        # For optional fields with errors, set to None instead of error object
        for field in optional_fields:
            if field in data and isinstance(data.get(field), dict) and 'error' in data.get(field, {}):
                logger.warning(f"⚠️ Optional field '{field}' unavailable for match {match_id}, setting to None")
                data[field] = None

        # ===================================================================
        # TASK 7: Partial Data Response Support
        # ===================================================================
        # Check if any optional fields are missing/None
        missing_optional = []
        for field in optional_fields:
            if field not in data or data.get(field) is None:
                missing_optional.append(field)

        if missing_optional:
            # Some optional fields are missing - mark as partial response
            data['partial'] = True
            data['warning'] = 'Bazı detaylar geçici olarak kullanılamıyor'
            data['missing_fields'] = missing_optional
            logger.info(f"⚠️ Partial data response for match {match_id}: missing {len(missing_optional)} optional fields")
            logger.debug(f"   Missing fields: {missing_optional}")
        else:
            # All fields present - complete response
            data['partial'] = False

        logger.info(f"✅ Successfully fetched match data for {match_id}")
        logger.debug(f"   Sources used: {data.get('sources_used', {})}")

        return data

    except APIError:
        # Re-raise APIError as-is (preserves status code like 404, 504, etc.)
        raise
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to fetch match data for {match_id}: {str(e)}")
        raise APIError(f"Failed to fetch match data: {str(e)}", 500)


def fetch_h2h_data_only(match_id):
    """
    PERFORMANCE OPTIMIZATION: Fetch ONLY H2H data (1 URL instead of 6)

    This function reduces unnecessary data fetching by ~83% for H2H endpoint.
    Instead of fetching all 6 URLs (h2h + 5 odds), we only fetch the H2H URL.

    Expected improvement: 10.5s → 3-4s (60-70% faster)

    Args:
        match_id: Match ID

    Returns:
        Dict with match_id, match_info, h2h_details, fixture

    Raises:
        APIError: If fetch fails
    """
    logger = logging.getLogger(__name__)

    # Validate match_id
    if not isinstance(match_id, int) or match_id <= 0:
        raise APIError("Invalid match ID", 400)

    # Check invalid match cache
    if _cache_instance is not None:
        invalid_cache_key = f'invalid_match:{match_id}'
        try:
            is_invalid = _cache_instance.get(invalid_cache_key)
            if is_invalid:
                logger.debug(f"⚠️ Match {match_id} is known invalid (cached 404)")
                raise APIError("Match not found", 404)
        except Exception as cache_err:
            logger.debug(f"Could not check invalid cache: {cache_err}")

    endpoints = current_config.NOWGOAL_ENDPOINTS

    # OPTIMIZATION: Only fetch H2H URL (1 URL instead of 6)
    urls = {
        "h2h_details": (endpoints['match_h2h'], match_id)
    }

    logger.info(f"🎯 OPTIMIZED: Fetching ONLY H2H data for match {match_id} (1 URL)")

    try:
        results = fetch_all_urls_sync(urls, match_id=match_id, use_failover=True)

        # Process H2H result
        for result in results:
            if isinstance(result, Exception):
                logger.warning(f"Exception in H2H fetch: {str(result)}")
                continue

            key, content, content_type, fetch_time, source_used = result

            if content_type == 'error':
                logger.warning(f"⚠️ Error fetching {key}: {content.get('error', 'Unknown error')}")

                # Check if 404
                error_msg = content.get('error', '')
                if '404' in error_msg or 'not found' in error_msg.lower():
                    # Cache as invalid
                    if _cache_instance is not None:
                        try:
                            invalid_cache_key = f'invalid_match:{match_id}'
                            _cache_instance.set(invalid_cache_key, '1', timeout=86400)
                            logger.info(f"✅ Cached invalid match {match_id} for 24 hours")
                        except Exception as cache_err:
                            logger.warning(f"Failed to cache invalid match: {cache_err}")
                    raise APIError("Match not found", 404)

                raise APIError("Failed to fetch H2H data", 503)

            elif content_type == 'html' and key == 'h2h_details':
                try:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(content, 'html.parser')  # Using html.parser (faster than lxml)

                    return {
                        'match_id': match_id,
                        'match_info': parse_match_info(soup),
                        'h2h_details': parse_h2h_details(soup),
                        'fixture': parse_fixture(soup),
                        'timestamp': datetime.utcnow().isoformat(),
                        'cached': False,
                        'fetch_times': {key: fetch_time},
                        'sources_used': {key: source_used},
                        'optimized': True,
                        'optimization': 'h2h_only'
                    }
                except Exception as e:
                    logger.warning(f"Error parsing H2H HTML: {str(e)}")
                    raise APIError(f"Failed to parse H2H data: {str(e)}", 500)

        raise APIError("No valid H2H data received", 503)

    except APIError:
        raise
    except Exception as e:
        logger.warning(f"Failed to fetch H2H data for {match_id}: {str(e)}")
        raise APIError(f"Failed to fetch H2H data: {str(e)}", 500)


def fetch_odds_data_only(match_id):
    """
    PERFORMANCE OPTIMIZATION: Fetch ONLY odds data (5 URLs instead of 6)

    This function skips H2H data fetching, reducing unnecessary overhead by ~17%.
    Expected improvement: 12.8s → 8-10s (30-40% faster)

    Args:
        match_id: Match ID

    Returns:
        Dict with match_id, odds_data (corner, correct_score, double_chance, first_half, odds_comp)

    Raises:
        APIError: If fetch fails
    """
    logger = logging.getLogger(__name__)

    # Validate match_id
    if not isinstance(match_id, int) or match_id <= 0:
        raise APIError("Invalid match ID", 400)

    # Check invalid match cache
    if _cache_instance is not None:
        invalid_cache_key = f'invalid_match:{match_id}'
        try:
            is_invalid = _cache_instance.get(invalid_cache_key)
            if is_invalid:
                logger.debug(f"⚠️ Match {match_id} is known invalid (cached 404)")
                raise APIError("Match not found", 404)
        except Exception as cache_err:
            logger.debug(f"Could not check invalid cache: {cache_err}")

    endpoints = current_config.NOWGOAL_ENDPOINTS

    # OPTIMIZATION: Only fetch odds URLs (5 URLs, skip h2h_details)
    urls = {
        "corner_odds": (endpoints['odds_corner'], match_id),
        "correct_score_odds": (endpoints['odds_correct_score'], match_id),
        "double_chance_odds": (endpoints['odds_double_chance'], match_id),
        "odds_comp": (endpoints['odds_comp'], match_id),
        "first_half_odds": (endpoints['odds_first_half'].replace('{random}', str(random.random())), match_id)
    }

    logger.info(f"🎯 OPTIMIZED: Fetching ONLY odds data for match {match_id} (5 URLs, skip H2H)")

    try:
        results = fetch_all_urls_sync(urls, match_id=match_id, use_failover=True)

        data = {
            'match_id': match_id,
            'timestamp': datetime.utcnow().isoformat(),
            'fetch_times': {},
            'sources_used': {},
            'cached': False,
            'optimized': True,
            'optimization': 'odds_only'
        }

        all_404 = True

        # Process all odds results
        for result in results:
            if isinstance(result, Exception):
                logger.warning(f"Exception in odds fetch: {str(result)}")
                continue

            key, content, content_type, fetch_time, source_used = result
            data['fetch_times'][key] = fetch_time
            if source_used:
                data['sources_used'][key] = source_used

            if content_type == 'error':
                logger.warning(f"⚠️ Error fetching {key}: {content.get('error', 'Unknown error')}")
                error_msg = content.get('error', '')
                if '404' not in error_msg and 'not found' not in error_msg.lower():
                    all_404 = False
                data[key] = content
            elif content_type == 'json':
                all_404 = False

                # Parse specific odds types
                try:
                    if key == 'correct_score_odds':
                        data[key] = parse_correct_score_odds(content)
                    elif key == 'double_chance_odds':
                        data[key] = parse_double_chance_odds(content)
                    elif key == 'corner_odds':
                        data[key] = parse_corner_odds(content)
                    elif key == 'first_half_odds':
                        data[key] = parse_first_half_odds(content)
                    elif key == 'odds_comp':
                        data[key] = parse_odds_comp(content)
                except Exception as e:
                    logger.warning(f"Error parsing {key}: {str(e)}")
                    data[key] = {"error": f"Failed to parse: {str(e)}"}

        # Check if all requests failed with 404
        if all_404:
            if _cache_instance is not None:
                try:
                    invalid_cache_key = f'invalid_match:{match_id}'
                    _cache_instance.set(invalid_cache_key, '1', timeout=86400)
                    logger.info(f"✅ Cached invalid match {match_id} for 24 hours")
                except Exception as cache_err:
                    logger.warning(f"Failed to cache invalid match: {cache_err}")
            raise APIError("Match not found", 404)

        # Check if we got at least some odds data
        has_odds = any([
            data.get('corner_odds') and not isinstance(data.get('corner_odds'), dict) or not data.get('corner_odds', {}).get('error'),
            data.get('correct_score_odds') and not isinstance(data.get('correct_score_odds'), dict) or not data.get('correct_score_odds', {}).get('error'),
            data.get('double_chance_odds') and not isinstance(data.get('double_chance_odds'), dict) or not data.get('double_chance_odds', {}).get('error'),
            data.get('first_half_odds') and not isinstance(data.get('first_half_odds'), dict) or not data.get('first_half_odds', {}).get('error'),
            data.get('odds_comp') and not isinstance(data.get('odds_comp'), dict) or not data.get('odds_comp', {}).get('error')
        ])

        if not has_odds:
            raise APIError("No valid odds data received", 503)

        logger.info(f"✅ Successfully fetched odds data for {match_id}")
        return data

    except APIError:
        raise
    except Exception as e:
        logger.warning(f"Failed to fetch odds data for {match_id}: {str(e)}")
        raise APIError(f"Failed to fetch odds data: {str(e)}", 500)


