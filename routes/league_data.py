"""
League Data Endpoints - Standings, Matches, Odds
Uses AWS Lambda compatible caching and multi-source failover
"""
import logging
import random
from typing import Optional
from flask import Blueprint, request
import requests

from models import APIError, build_success_response
from app_config import current_config
from league_parser import league_data_parser, league_odds_parser, extract_sub_league_id, extract_all_sub_leagues
from cache_utils import get_with_stale_fallback
from routes import utils as route_utils  # Import module, not variable directly

logger = logging.getLogger(__name__)

# Create blueprint
league_data_bp = Blueprint('league_data', __name__)

# ============================================================================
# HTTP SESSION: Connection reuse for faster requests
# ============================================================================
# Reusing TCP/SSL connections saves ~0.7s per request pair
_http_session = None

def _get_http_session() -> requests.Session:
    """Get or create HTTP session for connection reuse"""
    global _http_session
    if _http_session is None:
        _http_session = requests.Session()
        _http_session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
        })
        logger.info("✅ Created HTTP session for connection reuse")
    return _http_session

# ============================================================================
# PERFORMANCE OPTIMIZATION: Smart Competition Index
# ============================================================================
# Build in-memory index from leagues_master.json for instant type lookups.
# Replaces the old KNOWN_CUPS set with a richer dict that also carries
# has_subleague, letting us skip HTML fetches for the majority of leagues.

def _load_leagues_master() -> dict:
    """Load full leagues master data for lookups"""
    import json
    import os

    json_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'leagues_master.json')

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"⚠️ Could not load leagues_master.json: {e}")
        return {}


def _build_comp_index(master: dict) -> dict:
    """
    Build a fast lookup dict from leagues_master.json.
    Returns: {league_id: {'type': 'cup'|'league', 'has_subleague': bool}}
    """
    index = {}
    for country in master.get('countries', []):
        for comp in country.get('competitions', []):
            index[comp['id']] = {
                'type': comp.get('type', 'league'),
                'has_subleague': comp.get('has_subleague', False),
            }
    logger.info(f"✅ Built COMP_INDEX with {len(index)} competitions")
    return index


# Load on module import (once per process)
LEAGUES_MASTER = _load_leagues_master()
COMP_INDEX = _build_comp_index(LEAGUES_MASTER)


def get_competition_info(comp_id: int) -> Optional[dict]:
    """Get competition info from master data"""
    if not LEAGUES_MASTER:
        return None

    for country in LEAGUES_MASTER.get('countries', []):
        for comp in country.get('competitions', []):
            if comp.get('id') == comp_id:
                return {
                    'id': comp['id'],
                    'code': comp.get('code', ''),
                    'name': comp.get('name', 'Unknown'),
                    'type': comp.get('type', 'league'),
                    'has_subleague': comp.get('has_subleague', False),
                    'seasons': comp.get('seasons', []),
                    'country': country.get('name', 'Unknown'),
                    'country_flag': country.get('flag_image', ''),
                }
    return None


def is_cup(comp_id: int) -> bool:
    """Check if competition is a cup — COMP_INDEX first, then cache fallback"""
    info = COMP_INDEX.get(comp_id)
    if info is not None:
        return info['type'] == 'cup'
    # Fallback: check runtime cache for competitions discovered at request time
    cache = route_utils._cache_instance
    if cache:
        cached = cache.get(f"comp_type:{comp_id}")
        return cached == 'cup'
    return False


# ============================================================================
# CONFIGURATION - All values from environment via config.py
# ============================================================================

def get_league_page_url(league_id: int) -> str:
    """
    Build league page URL from config

    Example: https://football.nowgoal26.com/league/745
    """
    base_url = current_config.LEAGUE_DATA_SOURCE.rstrip('/')
    endpoint = current_config.LEAGUE_ENDPOINTS['league_page'].format(
        league_id=league_id
    )
    return f"{base_url}{endpoint}"


def get_league_data_url(league_id: int, sub_league_id: Optional[int], season: str) -> str:
    """
    Build league data URL from config

    Two formats:
    - With sub-league: /jsData/matchResult/2025-2026/s745_918_en.js
    - Without sub-league: /jsData/matchResult/2025-2026/s36_en.js
    """
    base_url = current_config.LEAGUE_DATA_SOURCE.rstrip('/')

    if sub_league_id and sub_league_id > 0:
        # With sub-league
        endpoint = current_config.LEAGUE_ENDPOINTS['league_data_with_sub'].format(
            league_id=league_id,
            sub_league_id=sub_league_id,
            season=season
        )
    else:
        # Without sub-league
        endpoint = current_config.LEAGUE_ENDPOINTS['league_data_without_sub'].format(
            league_id=league_id,
            season=season
        )

    return f"{base_url}{endpoint}?flesh={random.random()}"


def get_cup_data_url(cup_id: int, season: str) -> str:
    """
    Build cup data URL

    Cup format: /jsData/matchResult/2024-2025/c90_en.js
    Note: Cups use 'c' prefix instead of 's' for leagues
    """
    base_url = current_config.LEAGUE_DATA_SOURCE.rstrip('/')
    endpoint = f"/jsData/matchResult/{season}/c{cup_id}_en.js"
    return f"{base_url}{endpoint}?flesh={random.random()}"




def get_cache_ttl(cache_type: str) -> int:
    """Get cache TTL from config"""
    ttl_map = {
        'standings': current_config.LEAGUE_CACHE_TTL_STANDINGS,      # 12 hours
        'matches': current_config.LEAGUE_CACHE_TTL_MATCHES,          # 48 hours
        'full': current_config.LEAGUE_CACHE_TTL_FULL,                # 12 hours
        'info': current_config.LEAGUE_CACHE_TTL_INFO,                # 7 days
        'team_stats': current_config.LEAGUE_CACHE_TTL_TEAM_STATS,    # 12 hours
        'player_stats': current_config.LEAGUE_CACHE_TTL_PLAYER_STATS,# 24 hours
        'handicap': current_config.LEAGUE_CACHE_TTL_HANDICAP,        # 12 hours
        'current_round': current_config.LEAGUE_CACHE_TTL_CURRENT_ROUND,# 12 hours
        'odds': current_config.LEAGUE_CACHE_TTL_ODDS,                # 5 min
    }
    return ttl_map.get(cache_type, 43200)  # Default 12 hours


def fetch_league_page(url: str) -> str:
    """Fetch league page HTML to extract sub_league_id"""
    try:
        session = _get_http_session()
        response = session.get(
            url,
            headers={'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'},
            timeout=(current_config.HTTP_TIMEOUT_CONNECT, current_config.HTTP_TIMEOUT_READ)
        )
        response.raise_for_status()
        return response.text

    except Exception as e:
        logger.error(f"Failed to fetch league page from {url}: {e}")
        raise APIError(f"Failed to fetch league page: {str(e)}", 503)


def fetch_league_data(url: str, allow_cup: bool = True) -> str:
    """Fetch data from league/cup URL with failover support

    Args:
        url: The URL to fetch JS data from
        allow_cup: If True, also accept arrCup as valid content (for cup data)

    Returns:
        JavaScript content string

    Raises:
        APIError: If fetch fails or returns HTML instead of JS (common for cups without data)
    """
    try:
        # Use session for connection reuse
        session = _get_http_session()
        response = session.get(
            url,
            headers={'Referer': current_config.LEAGUE_DATA_SOURCE.rstrip('/') + '/'},
            timeout=(current_config.HTTP_TIMEOUT_CONNECT, current_config.HTTP_TIMEOUT_READ)
        )
        response.raise_for_status()

        content = response.text

        # Check if response is HTML instead of JS (common for cups without match data)
        if content.strip().startswith('<!DOCTYPE') or content.strip().startswith('<html'):
            logger.warning(f"Received HTML instead of JS data from {url} - cup/league may not have match data")
            raise APIError(
                "Match data not available for this league/cup. "
                "Some cups (knockout format) may not have detailed match data in this format.",
                404
            )

        # Verify content has expected JS variables
        has_league = 'arrLeague' in content
        has_cup = 'arrCup' in content
        has_team = 'arrTeam' in content

        if not has_team:
            logger.warning(f"JS content missing arrTeam from {url}")
            raise APIError(
                "Invalid league data format. The data source may have changed or is temporarily unavailable.",
                503
            )

        if not has_league and not (allow_cup and has_cup):
            logger.warning(f"JS content missing expected variables from {url}")
            raise APIError(
                "Invalid league data format. The data source may have changed or is temporarily unavailable.",
                503
            )

        return content

    except APIError:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch league data from {url}: {e}")
        raise APIError(f"Failed to fetch league data: {str(e)}", 503)


def fetch_league_or_cup_data(league_id: int, sub_league_id: Optional[int], season: str) -> tuple:
    """
    Smart 4-step waterfall fetch: COMP_INDEX → cache → direct fetch → fallback

    Strategy:
    1. COMP_INDEX lookup (in-memory, instant) → choose correct URL format
    2. Runtime cache for competition type (covers unknown competitions after 1st fetch)
    3. Direct fetch using the resolved URL format
    4. Waterfall fallback for truly unknown competitions

    Returns:
        Tuple of (js_content, is_cup)
    """
    cache = route_utils._cache_instance
    cache_key = f"comp_type:{league_id}"

    # STEP 1: COMP_INDEX lookup — covers all 957 known competitions instantly
    comp_info = COMP_INDEX.get(league_id)
    if comp_info:
        comp_type = comp_info['type']
        has_sub = comp_info['has_subleague']

        if comp_type == 'cup':
            cup_url = get_cup_data_url(league_id, season)
            logger.info(f"🏆 [INDEX] Cup {league_id} → {cup_url}")
            content = fetch_league_data(cup_url, allow_cup=True)
            if 'arrCup' in content:
                if cache:
                    cache.set(cache_key, 'cup', timeout=86400)
                return content, True
            # Cup URL returned league data (rare edge case) — fall through
            if 'arrLeague' in content:
                if cache:
                    cache.set(cache_key, 'league_nosub', timeout=86400)
                return content, False

        elif not has_sub:
            # Simple league — try s{id}_en.js directly, no HTML fetch needed
            league_url = get_league_data_url(league_id, None, season)
            logger.info(f"📊 [INDEX] League (no sub) {league_id} → {league_url}")
            try:
                content = fetch_league_data(league_url, allow_cup=True)
                if 'arrLeague' in content:
                    if cache:
                        cache.set(cache_key, 'league_nosub', timeout=86400)
                    return content, False
                if 'arrCup' in content:
                    # Index says league but data is cup — trust the data
                    if cache:
                        cache.set(cache_key, 'cup', timeout=86400)
                    return content, True
            except APIError:
                # Source returned HTML or failed — try cup format as fallback
                pass
            cup_url = get_cup_data_url(league_id, season)
            logger.info(f"🏆 [INDEX] League {league_id} failed, trying cup fallback")
            content = fetch_league_data(cup_url, allow_cup=True)
            if 'arrCup' in content:
                if cache:
                    cache.set(cache_key, 'cup', timeout=86400)
                return content, True

        else:
            # League with sub-leagues — sub_league_id must already be resolved by caller
            league_url = get_league_data_url(league_id, sub_league_id, season)
            logger.info(f"📊 [INDEX] League (has sub={sub_league_id}) {league_id} → {league_url}")
            content = fetch_league_data(league_url, allow_cup=True)
            if 'arrLeague' in content:
                if cache:
                    cache.set(cache_key, f'league_sub:{sub_league_id}', timeout=86400)
                return content, False

        # If we reach here the index entry didn't yield a clean result — fall through
        logger.warning(f"⚠️ COMP_INDEX entry for {league_id} did not yield valid data, using waterfall")

    # STEP 2: Runtime cache — covers competitions discovered dynamically
    if cache:
        cached_type = cache.get(cache_key)
        if cached_type == 'cup':
            cup_url = get_cup_data_url(league_id, season)
            logger.info(f"🏆 [CACHE] ID {league_id} is cup")
            try:
                content = fetch_league_data(cup_url, allow_cup=True)
                if 'arrCup' in content:
                    return content, True
            except APIError:
                pass
        elif cached_type == 'league_nosub':
            league_url = get_league_data_url(league_id, None, season)
            logger.info(f"📊 [CACHE] ID {league_id} is league (no sub)")
            try:
                content = fetch_league_data(league_url, allow_cup=True)
                if 'arrLeague' in content:
                    return content, False
            except APIError:
                pass
        elif cached_type and cached_type.startswith('league_sub:'):
            sub_id = int(cached_type.split(':')[1])
            league_url = get_league_data_url(league_id, sub_id, season)
            logger.info(f"📊 [CACHE] ID {league_id} is league (sub={sub_id})")
            try:
                content = fetch_league_data(league_url, allow_cup=True)
                if 'arrLeague' in content:
                    return content, False
            except APIError:
                pass

    # STEP 3: Waterfall fallback for unknown competitions
    # 3a. Try cup format first
    try:
        cup_url = get_cup_data_url(league_id, season)
        logger.info(f"🏆 [WATERFALL] Trying cup URL: {cup_url}")
        content = fetch_league_data(cup_url, allow_cup=True)
        if 'arrCup' in content:
            if cache:
                cache.set(cache_key, 'cup', timeout=86400)
            return content, True
    except APIError:
        pass

    # 3b. Try league without sub_league_id
    try:
        league_url = get_league_data_url(league_id, None, season)
        logger.info(f"📊 [WATERFALL] Trying league URL (no sub): {league_url}")
        content = fetch_league_data(league_url, allow_cup=True)
        if 'arrLeague' in content:
            if cache:
                cache.set(cache_key, 'league_nosub', timeout=86400)
            return content, False
    except APIError:
        pass

    # 3c. Try league with sub_league_id from HTML fetch
    sub_id = sub_league_id or get_sub_league_id(league_id)
    if sub_id:
        try:
            league_url = get_league_data_url(league_id, sub_id, season)
            logger.info(f"📊 [WATERFALL] Trying league URL (sub={sub_id}): {league_url}")
            content = fetch_league_data(league_url, allow_cup=True)
            if 'arrLeague' in content:
                if cache:
                    cache.set(cache_key, f'league_sub:{sub_id}', timeout=86400)
                return content, False
        except APIError:
            pass

    raise APIError("Match data not available for this competition.", 404)


def get_sub_league_id(league_id: int) -> Optional[int]:
    """
    Get sub_league_id for a league.

    Priority:
    1. Check cache
    2. Fetch from league page (HTTP request)

    Returns:
        sub_league_id if league has sub-leagues, None or 0 if not

    This is cached to avoid fetching the page on every request.
    """
    # 1. Check cache
    cache = route_utils._cache_instance
    cache_key = f"sub_league_id:{league_id}"

    if cache:
        cached = cache.get(cache_key)
        if cached is not None:
            return int(cached) if int(cached) > 0 else None

    # 2. Fetch league page (HTTP request)
    url = get_league_page_url(league_id)
    logger.info(f"🔍 Fetching league page to extract sub_league_id: {url}")

    html_content = fetch_league_page(url)
    sub_league_id = extract_sub_league_id(html_content)

    # Cache for 24 hours (sub_league_id rarely changes)
    # Cache 0 as well to avoid re-fetching for leagues without sub-leagues
    if cache:
        cache.set(cache_key, sub_league_id if sub_league_id else 0, timeout=86400)

    return sub_league_id


# ============================================================================
# ENDPOINTS
# ============================================================================

@league_data_bp.route('/leagues/<int:league_id>/standings', methods=['GET'])
def get_league_standings(league_id: int):
    """
    Get league standings/classification table

    Query params:
        - season: Season string like '2025-2026' (required)
        - type: 'overall' (default), 'home', or 'away'
        - sub_league_id: Sub-league ID for cups with multiple stages (optional)
                        Use /leagues/{id}/info to get available sub_league_ids

    Example: /api/v1/leagues/745/standings?season=2025-2026&type=overall
    Example: /api/v1/leagues/132/standings?season=2024-2025&sub_league_id=1843

    Note: Cups (knockout format) typically don't have standings data.
    """
    # Get query parameters
    season = request.args.get('season', '')
    standings_type = request.args.get('type', 'overall')
    custom_sub_league_id = request.args.get('sub_league_id', type=int)

    if not season:
        raise APIError("season is required (e.g., 2025-2026)", 400)

    if standings_type not in ['overall', 'home', 'away']:
        raise APIError("type must be 'overall', 'home', or 'away'", 400)

    # Use custom sub_league_id if provided, otherwise determine based on competition type
    if custom_sub_league_id:
        sub_league_id = custom_sub_league_id
        logger.info(f"Using custom sub_league_id: {sub_league_id}")
    elif is_cup(league_id):
        sub_league_id = None
        logger.info(f"🏆 [INDEX] Cup {league_id}, skipping sub_league_id lookup")
    else:
        comp_info = COMP_INDEX.get(league_id)
        if comp_info and not comp_info['has_subleague']:
            sub_league_id = None
            logger.info(f"📊 [INDEX] League {league_id} has no sub-league, skipping HTML fetch")
        else:
            sub_league_id = get_sub_league_id(league_id)

    # Cache key
    cache_key = f"league_standings:{league_id}:{sub_league_id}:{season}:{standings_type}"

    def fetch_standings():
        # Use fetch_league_or_cup_data to handle both leagues and cups
        js_content, is_cup = fetch_league_or_cup_data(league_id, sub_league_id, season)
        logger.info(f"📊 Fetching league standings (is_cup={is_cup})")

        parsed = league_data_parser.parse_league_data(js_content, is_cup=is_cup)

        if not parsed:
            raise APIError("Failed to parse league data", 500)

        standings = parsed['standings'].get(standings_type, [])

        return {
            'league': parsed['league'],
            'sub_league': parsed['sub_league'],
            'sub_league_id': sub_league_id,
            'standings_type': standings_type,
            'standings': standings,
            'teams_count': len(standings),
            'zones': parsed['zones'],
        }

    # Use cache with stale fallback
    cache = route_utils._cache_instance
    ttl = get_cache_ttl('standings')
    if cache:
        result = get_with_stale_fallback(
            cache_instance=cache,
            cache_key=cache_key,
            fetch_function=fetch_standings,
            fresh_ttl=ttl,
            stale_ttl=ttl * 2
        )
    else:
        result = fetch_standings()

    return build_success_response(result)


@league_data_bp.route('/leagues/<int:league_id>/matches', methods=['GET'])
def get_league_matches(league_id: int):
    """
    Get league matches by round

    Query params:
        - season: Season string like '2025-2026' (required)
        - round: Round number (optional, returns all if not specified)
        - sub_league_id: Sub-league ID for cups with multiple stages (optional)
                        Use /leagues/{id}/info to get available sub_league_ids

    Example: /api/v1/leagues/745/matches?season=2025-2026&round=17
    Example: /api/v1/leagues/132/matches?season=2024-2025&sub_league_id=1862  # Championship Group
    """
    # Get query parameters
    season = request.args.get('season', '')
    round_num = request.args.get('round', type=int)
    custom_sub_league_id = request.args.get('sub_league_id', type=int)

    if not season:
        raise APIError("season is required (e.g., 2025-2026)", 400)

    # Determine sub_league_id using COMP_INDEX (avoids HTML fetch for most leagues)
    if custom_sub_league_id:
        sub_league_id = custom_sub_league_id
        logger.info(f"Using custom sub_league_id: {sub_league_id}")
    elif is_cup(league_id):
        sub_league_id = None
        logger.info(f"🏆 [INDEX] Cup {league_id}, skipping sub_league_id lookup")
    else:
        comp_info = COMP_INDEX.get(league_id)
        if comp_info and not comp_info['has_subleague']:
            sub_league_id = None
            logger.info(f"📊 [INDEX] League {league_id} has no sub-league, skipping HTML fetch")
        else:
            sub_league_id = get_sub_league_id(league_id)

    # Cache key
    cache_key = f"league_matches:{league_id}:{sub_league_id}:{season}:{round_num or 'all'}"

    def fetch_matches():
        # Try cup first, then league
        js_content, is_cup = fetch_league_or_cup_data(league_id, sub_league_id, season)
        parsed = league_data_parser.parse_league_data(js_content, is_cup=is_cup)

        if not parsed:
            raise APIError("Failed to parse league data", 500)

        rounds_data = parsed['rounds']

        # Filter by round if specified
        if round_num is not None:
            if round_num not in rounds_data:
                raise APIError(f"Round {round_num} not found", 404)
            matches = rounds_data[round_num]
            result_rounds = {round_num: matches}
        else:
            result_rounds = rounds_data
            matches = []
            for r_matches in rounds_data.values():
                matches.extend(r_matches)

        result = {
            'league': parsed['league'],
            'sub_league': parsed['sub_league'],
            'sub_league_id': sub_league_id,
            'season': season,
            'round': round_num,
            'total_rounds': parsed['sub_league'].get('total_rounds') or len(rounds_data),
            'rounds': result_rounds if round_num is None else None,
            'matches': matches if round_num is not None else None,
            'match_count': len(matches) if round_num is not None else sum(len(m) for m in rounds_data.values()),
            'is_cup': is_cup,
        }

        # Add cup-specific data if available
        if is_cup and 'cup_rounds' in parsed:
            result['cup_rounds'] = parsed['cup_rounds']

        return result

    # Use cache with stale fallback
    cache = route_utils._cache_instance
    ttl = get_cache_ttl('matches')
    if cache:
        result = get_with_stale_fallback(
            cache_instance=cache,
            cache_key=cache_key,
            fetch_function=fetch_matches,
            fresh_ttl=ttl,
            stale_ttl=ttl * 2
        )
    else:
        result = fetch_matches()

    return build_success_response(result)




@league_data_bp.route('/leagues/<int:league_id>/full', methods=['GET'])
def get_league_full_data(league_id: int):
    """
    Get complete league data (standings + all matches)

    Query params:
        - season: Season string like '2025-2026' (required)

    Example: /api/v1/leagues/745/full?season=2025-2026
    """
    # Get query parameters
    season = request.args.get('season', '')

    if not season:
        raise APIError("season is required (e.g., 2025-2026)", 400)

    # Determine sub_league_id using COMP_INDEX
    if is_cup(league_id):
        sub_league_id = None
        logger.info(f"🏆 [INDEX] Cup {league_id}, skipping sub_league_id lookup")
    else:
        comp_info = COMP_INDEX.get(league_id)
        if comp_info and not comp_info['has_subleague']:
            sub_league_id = None
            logger.info(f"📊 [INDEX] League {league_id} has no sub-league, skipping HTML fetch")
        else:
            sub_league_id = get_sub_league_id(league_id)

    # Cache key
    cache_key = f"league_full:{league_id}:{sub_league_id}:{season}"

    def fetch_full_data():
        # Use fetch_league_or_cup_data to handle both leagues and cups
        js_content, is_cup = fetch_league_or_cup_data(league_id, sub_league_id, season)
        logger.info(f"📋 Fetching full league data (is_cup={is_cup})")

        parsed = league_data_parser.parse_league_data(js_content, is_cup=is_cup)

        if not parsed:
            raise APIError("Failed to parse league data", 500)

        return {
            'league': parsed['league'],
            'sub_league': parsed['sub_league'],
            'sub_league_id': sub_league_id,
            'teams': parsed['teams'],
            'standings': parsed['standings'],
            'rounds': parsed['rounds'],
            'zones': parsed['zones'],
            'total_matches': sum(len(m) for m in parsed['rounds'].values()),
        }

    # Use cache with stale fallback
    cache = route_utils._cache_instance
    ttl = get_cache_ttl('full')  # 12 hours
    if cache:
        result = get_with_stale_fallback(
            cache_instance=cache,
            cache_key=cache_key,
            fetch_function=fetch_full_data,
            fresh_ttl=ttl,
            stale_ttl=ttl * 2
        )
    else:
        result = fetch_full_data()

    return build_success_response(result)


@league_data_bp.route('/leagues/<int:league_id>/info', methods=['GET'])
def get_league_info(league_id: int):
    """
    Get league info including sub-leagues

    Returns available sub-leagues for a league (useful for cups with groups/stages).
    Use the sub_league_id values to query specific stages in /matches and /standings endpoints.

    Example: /api/v1/leagues/745/info
    Example: /api/v1/leagues/103/info  # Champions League
    """
    # Cache key
    cache_key = f"league_info:{league_id}"

    def fetch_info():
        # OPTIMIZATION: First check master data (instant, no HTTP)
        master_info = get_competition_info(league_id)

        if master_info:
            logger.info(f"ℹ️ [FAST] Got info from master data for ID {league_id}")
            is_cup_type = master_info['type'] == 'cup'

            result = {
                'league_id': league_id,
                'code': master_info['code'],
                'name': master_info['name'],
                'type': master_info['type'],
                'country': master_info['country'],
                'country_flag': master_info['country_flag'],
                'has_subleague': master_info['has_subleague'],
                'available_seasons': master_info['seasons'][:10],  # Last 10 seasons
                'current_season': master_info['seasons'][0] if master_info['seasons'] else None,
                'is_cup': is_cup_type,
                'data_source': 'master_data',
            }

            # For cups, add helpful note
            if is_cup_type:
                result['note'] = (
                    "This is a cup competition. Use /leagues/{id}/matches?season=YYYY-YYYY to get cup matches. "
                    "Cup data uses round/stage names instead of numbered rounds."
                )

            return result

        # FALLBACK: Fetch from website if not in master data
        logger.info(f"ℹ️ Fetching league info from website for ID {league_id}")
        url = get_league_page_url(league_id)

        html_content = fetch_league_page(url)
        sub_leagues = extract_all_sub_leagues(html_content)
        default_sub_id = extract_sub_league_id(html_content)

        # Determine if this is likely a cup (knockout) or league format
        is_cup_by_sub_id = default_sub_id is None or default_sub_id == 0
        has_multiple_stages = len(sub_leagues) > 1

        # Check if it's in our cup index
        is_cup_from_index = is_cup(league_id)

        # Try to detect if cup data exists (c{id} format)
        cup_data_available = False
        if is_cup_by_sub_id or is_cup_from_index:
            try:
                from datetime import datetime
                current_year = datetime.now().year
                test_season = f"{current_year}-{current_year + 1}"
                cup_url = get_cup_data_url(league_id, test_season)
                cup_content = fetch_league_data(cup_url, allow_cup=True)
                if 'arrCup' in cup_content:
                    cup_data_available = True
                    logger.info(f"✅ Cup data available for ID {league_id}")
            except Exception:
                pass

        result = {
            'league_id': league_id,
            'sub_league_id': default_sub_id,
            'sub_leagues': sub_leagues,
            'sub_leagues_count': len(sub_leagues),
            'has_multiple_stages': has_multiple_stages,
            'data_available': (default_sub_id is not None and default_sub_id > 0) or cup_data_available,
            'is_cup': is_cup_by_sub_id or is_cup_from_index,
            'cup_data_available': cup_data_available,
            'data_source': 'website',
        }

        # Add helpful message for cups
        if is_cup_by_sub_id or is_cup_from_index:
            if cup_data_available:
                result['note'] = (
                    "This is a cup competition. Use /leagues/{id}/matches?season=YYYY-YYYY to get cup matches. "
                    "Cup data uses a different format with round/stage names instead of numbered rounds."
                )
            else:
                result['note'] = (
                    "This cup/league may not have detailed match data available. "
                    "Some knockout format competitions don't provide structured standings or match data. "
                    "Try using /matches/date/{date} endpoint to get matches by date instead."
                )

        return result

    # Use cache with stale fallback
    cache = route_utils._cache_instance
    ttl = get_cache_ttl('info')  # 7 days
    if cache:
        result = get_with_stale_fallback(
            cache_instance=cache,
            cache_key=cache_key,
            fetch_function=fetch_info,
            fresh_ttl=ttl,
            stale_ttl=ttl * 2
        )
    else:
        result = fetch_info()

    return build_success_response(result)


# ============================================================================
# NEW ENDPOINTS - Seasons, Team Stats, Player Stats, Handicap Stats
# ============================================================================



def get_team_stats_url(league_id: int, season: str) -> str:
    """Build team tech stats URL - /jsdata/count/{season}/teamTech_{league_id}.js"""
    base_url = current_config.LEAGUE_DATA_SOURCE.rstrip('/')
    return f"{base_url}/jsdata/count/{season}/teamTech_{league_id}.js?r={random.random()}"


def get_player_stats_url(league_id: int, season: str) -> str:
    """Build player stats URL - /jsdata/count/{season}/playertech_{league_id}.js"""
    base_url = current_config.LEAGUE_DATA_SOURCE.rstrip('/')
    return f"{base_url}/jsdata/count/{season}/playertech_{league_id}.js?r={random.random()}"


def fetch_stats_data(url: str) -> str:
    """Fetch statistics data (player/team stats) with proper compression support

    This is different from fetch_league_data as it:
    1. Supports gzip/deflate compression
    2. Doesn't require arrTeam/arrLeague variables

    Returns:
        JavaScript content string
    """
    try:
        # Use session for connection reuse
        session = _get_http_session()
        response = session.get(
            url,
            headers={'Referer': current_config.LEAGUE_DATA_SOURCE.rstrip('/') + '/'},
            timeout=(current_config.HTTP_TIMEOUT_CONNECT, current_config.HTTP_TIMEOUT_READ)
        )
        response.raise_for_status()

        # Handle encoding - try utf-8-sig first for BOM, then utf-8
        try:
            content = response.content.decode('utf-8-sig')
        except UnicodeDecodeError:
            content = response.content.decode('utf-8', errors='replace')

        # Check if response is HTML instead of JS
        if content.strip().startswith('<!DOCTYPE') or content.strip().startswith('<html'):
            logger.warning(f"Received HTML instead of JS data from {url}")
            raise APIError("Stats data not available for this league", 404)

        return content

    except APIError:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch stats data from {url}: {e}")
        raise APIError(f"Failed to fetch stats data: {str(e)}", 503)


def get_handicap_stats_url(league_id: int, season: str) -> str:
    """Build handicap/letGoal stats URL - /jsData/letGoal/{season}/l{league_id}.js"""
    base_url = current_config.LEAGUE_DATA_SOURCE.rstrip('/')
    return f"{base_url}/jsData/letGoal/{season}/l{league_id}.js?r={random.random()}"






@league_data_bp.route('/leagues/<int:league_id>/team-stats', methods=['GET'])
def get_league_team_stats(league_id: int):
    """
    Get team technical statistics for a league

    Query params:
        - season: Season string like '2025-2026' (required)
        - type: 'total' (default), 'home', or 'guest'

    Example: /api/v1/leagues/37/team-stats?season=2025-2026

    Returns: shots, passes, corners, cards, xG, possession etc.
    """
    season = request.args.get('season', '')
    stats_type = request.args.get('type', 'Total')

    if not season:
        raise APIError("season is required (e.g., 2025-2026)", 400)

    if stats_type.lower() not in ['total', 'home', 'guest']:
        stats_type = 'Total'
    else:
        stats_type = stats_type.capitalize()
        if stats_type == 'Guest':
            stats_type = 'guest'  # API uses lowercase for guest

    cache_key = f"league_team_stats:{league_id}:{season}:{stats_type}"

    def fetch_team_stats():
        url = get_team_stats_url(league_id, season)
        logger.info(f"📊 Fetching team stats from: {url}")

        js_content = fetch_stats_data(url)

        # Parse techCout_Team object
        import re
        import json as json_lib

        # Extract the JSON-like object
        match = re.search(r'var\s+techCout_Team\s*=\s*(\{[\s\S]*?\});', js_content)
        if not match:
            raise APIError("Failed to parse team stats data", 500)

        try:
            # Parse the JavaScript object (it's almost JSON)
            js_obj = match.group(1)
            # Fix JavaScript to JSON differences
            js_obj = re.sub(r'(\w+):', r'"\1":', js_obj)  # Add quotes to keys
            data = json_lib.loads(js_obj)
        except Exception as e:
            logger.error(f"Failed to parse team stats JSON: {e}")
            raise APIError("Failed to parse team stats data", 500)

        teams = data.get('Tid', {})
        stats_data = data.get(stats_type, {})

        # Field mapping from documentation
        field_names = [
            'TeamID', 'SchSum', 'shots', 'target', 'offTarget', 'passBall',
            'passBallSuc', 'dribbles', 'yellow', 'red', 'shotsed', 'fouls',
            'Corner', 'offside', 'header', 'headerSuc', 'save', 'blocked',
            'tackle', 'throwIns', 'goal', 'fumble', 'ExpectedGoals', 'xGOpenPlay',
            'xGSetPlay', 'xGNonPenalty', 'xGOT', 'TIOBx', 'AccurateCrosses',
            'GroundDuelsWon', 'AerialDuelsWon', 'Clearances', 'avgControl'
        ]

        team_stats = []
        for team_values in stats_data.get('value', []):
            team_id = str(team_values[0]) if team_values else None
            team_info = teams.get(team_id, ['Unknown', 'Unknown', 'Unknown'])

            stats_dict = {
                'team_id': team_id,
                'team_name': team_info[2] if len(team_info) > 2 else 'Unknown',  # English name
            }

            for i, field in enumerate(field_names):
                if i < len(team_values):
                    stats_dict[field.lower()] = team_values[i]

            team_stats.append(stats_dict)

        return {
            'league_id': league_id,
            'season': season,
            'stats_type': stats_type,
            'teams': team_stats,
            'team_count': len(team_stats)
        }

    cache = route_utils._cache_instance
    ttl = get_cache_ttl('team_stats')  # 12 hours
    if cache:
        result = get_with_stale_fallback(
            cache_instance=cache,
            cache_key=cache_key,
            fetch_function=fetch_team_stats,
            fresh_ttl=ttl,
            stale_ttl=ttl * 2
        )
    else:
        result = fetch_team_stats()

    return build_success_response(result)


@league_data_bp.route('/leagues/<int:league_id>/handicap-stats', methods=['GET'])
def get_league_handicap_stats(league_id: int):
    """
    Get Asian Handicap and Over/Under statistics for a league

    Query params:
        - season: Season string like '2025-2026' (required)

    Example: /api/v1/leagues/37/handicap-stats?season=2025-2026

    Returns: AH stats, O/U stats, goal summaries
    """
    season = request.args.get('season', '')

    if not season:
        raise APIError("season is required (e.g., 2025-2026)", 400)

    cache_key = f"league_handicap_stats:{league_id}:{season}"

    def fetch_handicap_stats():
        url = get_handicap_stats_url(league_id, season)
        logger.info(f"🎯 Fetching handicap stats from: {url}")

        js_content = fetch_stats_data(url)

        import re
        import json

        # Extract variables
        def extract_array(var_name):
            pattern = rf'var\s+{var_name}\s*=\s*\[([\s\S]*?)\];'
            match = re.search(pattern, js_content)
            if match:
                return match.group(1)
            return None

        def parse_handicap_array(raw_str):
            """Parse handicap array like [[1,236,17,8,2,7,10,0,7,3,58.8,0,41.2],...]"""
            if not raw_str:
                return []
            try:
                # Wrap in brackets and parse as JSON
                parsed = json.loads(f"[{raw_str}]")
                result = []
                for row in parsed:
                    if len(row) >= 13:
                        result.append({
                            'rank': row[0],
                            'team_id': row[1],
                            'matches': row[2],
                            'over_goals': row[3],
                            'draw_goals': row[4],
                            'under_goals': row[5],
                            'win': row[6],
                            'draw': row[7],
                            'lose': row[8],
                            'net': row[9],
                            'win_pct': row[10],
                            'draw_pct': row[11],
                            'lose_pct': row[12]
                        })
                return result
            except (json.JSONDecodeError, IndexError) as e:
                logger.warning(f"Failed to parse handicap array: {e}")
                return []

        result = {
            'league_id': league_id,
            'season': season,
            'total_ah': [],
            'home_ah': [],
            'guest_ah': [],
            'summary': {}
        }

        # Parse handicap arrays
        result['total_ah'] = parse_handicap_array(extract_array('TotalPanLu'))
        result['home_ah'] = parse_handicap_array(extract_array('HomePanLu'))
        result['guest_ah'] = parse_handicap_array(extract_array('GuestPanLu'))

        # Parse addUp for summary
        add_up_str = extract_array('addUp')
        if add_up_str:
            values = re.findall(r'[\d.]+', add_up_str)
            if len(values) >= 5:
                result['summary'] = {
                    'total_matches': int(float(values[0])) if values[0] else 0,
                    'total_goals': int(float(values[1])) if values[1] else 0,
                    'avg_goals': float(values[2]) if values[2] else 0,
                    'over_count': int(float(values[3])) if values[3] else 0,
                    'under_count': int(float(values[4])) if values[4] else 0
                }

        return result

    cache = route_utils._cache_instance
    ttl = get_cache_ttl('handicap')  # 12 hours
    if cache:
        result = get_with_stale_fallback(
            cache_instance=cache,
            cache_key=cache_key,
            fetch_function=fetch_handicap_stats,
            fresh_ttl=ttl,
            stale_ttl=ttl * 2
        )
    else:
        result = fetch_handicap_stats()

    return build_success_response(result)


@league_data_bp.route('/leagues/<int:league_id>/player-stats', methods=['GET'])
def get_league_player_stats(league_id: int):
    """
    Get player statistics for a league

    Query params:
        - season: Season string like '2025-2026' (required)
        - category: 'offensive' (default), 'passing', 'defensive', 'summary'

    Example: /api/v1/leagues/37/player-stats?season=2025-2026

    Returns: Player stats including goals, assists, shots, passes, ratings etc.

    Note: This is a large response (~134KB), may take 1-2 seconds
    """
    season = request.args.get('season', '')
    category = request.args.get('category', 'offensive').lower()

    if not season:
        raise APIError("season is required (e.g., 2025-2026)", 400)

    if category not in ['offensive', 'passing', 'defensive', 'summary']:
        category = 'offensive'

    cache_key = f"league_player_stats:{league_id}:{season}:{category}"

    def fetch_player_stats():
        url = get_player_stats_url(league_id, season)
        logger.info(f"👤 Fetching player stats from: {url}")

        js_content = fetch_stats_data(url)

        import re
        import json as json_lib

        # Parse techCout_Player structure
        # var techCout_Player={"Pid":{...},"Tid":{...},"Total":{...}}
        # Find the JSON object - match balanced braces
        match = re.search(r'var\s+techCout_Player\s*=\s*(\{.+)', js_content, re.DOTALL)
        if not match:
            raise APIError("Failed to parse player stats data", 500)

        try:
            js_obj = match.group(1).strip()
            # Remove trailing semicolon if present
            if js_obj.endswith(';'):
                js_obj = js_obj[:-1].strip()
            # The data is already valid JSON, just parse it
            data = json_lib.loads(js_obj)
        except Exception as e:
            logger.error(f"Failed to parse player stats JSON: {e}")
            return {
                'league_id': league_id,
                'season': season,
                'category': category,
                'players': [],
                'player_count': 0,
                'parse_error': str(e)
            }

        # Get player info and team info
        player_info = data.get('Pid', {})
        teams = data.get('Tid', {})
        stats_data = data.get('Total', {})

        # Field mapping from key
        field_keys = stats_data.get('key', {})
        player_values = stats_data.get('value', [])

        players = []
        for player_data in player_values[:100]:  # Limit to top 100
            if not player_data or len(player_data) < 10:
                continue

            player_id = str(player_data[0])
            p_info = player_info.get(player_id, [['Unknown', 'Unknown', 'Unknown'], 0])

            # Get goals (index 52 = Goals according to key)
            goals_idx = field_keys.get('Goals', 52)
            non_penalty_idx = field_keys.get('notPenaltyGoals', 4)
            penalty_idx = field_keys.get('penaltyGoals', 5)
            shots_idx = field_keys.get('shots', 6)
            shots_target_idx = field_keys.get('shotsTarget', 7)
            rating_idx = field_keys.get('rating', 10)
            minutes_idx = field_keys.get('PlayingTime', 3)
            matches_idx = field_keys.get('SchSum', 1)
            assists_idx = field_keys.get('assist', 15)
            key_pass_idx = field_keys.get('keyPass', 14)
            pass_idx = field_keys.get('pass', 12)
            pass_suc_idx = field_keys.get('passSucPercent', 53)

            team_id = p_info[1] if isinstance(p_info, list) and len(p_info) > 1 else None
            team_info = teams.get(str(team_id), ['Unknown', 'Unknown', 'Unknown'])

            player = {
                'player_id': int(player_id),
                'player_name': p_info[0][2] if isinstance(p_info, list) and len(p_info) > 0 and len(p_info[0]) > 2 else 'Unknown',
                'team_id': team_id,
                'team_name': team_info[2] if len(team_info) > 2 else 'Unknown',
                'matches': player_data[matches_idx] if len(player_data) > matches_idx else 0,
                'minutes': player_data[minutes_idx] if len(player_data) > minutes_idx else 0,
                'rating': player_data[rating_idx] if len(player_data) > rating_idx else 0,
                'goals': player_data[goals_idx] if len(player_data) > goals_idx else 0,
                'non_penalty_goals': player_data[non_penalty_idx] if len(player_data) > non_penalty_idx else 0,
                'penalty_goals': player_data[penalty_idx] if len(player_data) > penalty_idx else 0,
                'shots': player_data[shots_idx] if len(player_data) > shots_idx else 0,
                'shots_on_target': player_data[shots_target_idx] if len(player_data) > shots_target_idx else 0,
                'assists': player_data[assists_idx] if len(player_data) > assists_idx else 0,
                'key_passes': player_data[key_pass_idx] if len(player_data) > key_pass_idx else 0,
                'passes': player_data[pass_idx] if len(player_data) > pass_idx else 0,
                'pass_accuracy': player_data[pass_suc_idx] if len(player_data) > pass_suc_idx else 0,
            }
            players.append(player)

        # Sort by goals descending
        players.sort(key=lambda x: (x['goals'], x['rating']), reverse=True)

        return {
            'league_id': league_id,
            'season': season,
            'category': category,
            'players': players,
            'player_count': len(players)
        }

    cache = route_utils._cache_instance
    ttl = get_cache_ttl('player_stats')  # 24 hours
    if cache:
        result = get_with_stale_fallback(
            cache_instance=cache,
            cache_key=cache_key,
            fetch_function=fetch_player_stats,
            fresh_ttl=ttl,
            stale_ttl=ttl * 2
        )
    else:
        result = fetch_player_stats()

    return build_success_response(result)




@league_data_bp.route('/leagues/<int:league_id>/current-round', methods=['GET'])
def get_current_round(league_id: int):
    """
    Get current/latest round for a league or cup

    Query params:
        - season: Season string like '2025-2026' (optional, defaults to 2025-2026)

    Example: /api/v1/leagues/36/current-round?season=2024-2025

    Returns: Current round number based on match dates and statuses
    """
    from datetime import datetime

    season = request.args.get('season', '2025-2026')

    # Determine sub_league_id using COMP_INDEX
    if is_cup(league_id):
        sub_league_id = None
        logger.info(f"🏆 [INDEX] Cup {league_id}, skipping sub_league_id lookup")
    else:
        comp_info = COMP_INDEX.get(league_id)
        if comp_info and not comp_info['has_subleague']:
            sub_league_id = None
            logger.info(f"📊 [INDEX] League {league_id} has no sub-league, skipping HTML fetch")
        else:
            sub_league_id = get_sub_league_id(league_id)

    cache_key = f"league_current_round:{league_id}:{sub_league_id}:{season}"

    def fetch_current_round():
        # Use fetch_league_or_cup_data to handle both leagues and cups
        js_content, is_cup = fetch_league_or_cup_data(league_id, sub_league_id, season)
        logger.info(f"🔄 Fetching current round (is_cup={is_cup})")

        parsed = league_data_parser.parse_league_data(js_content, is_cup=is_cup)

        if not parsed:
            raise APIError("Failed to parse league data", 500)

        rounds_data = parsed['rounds']
        total_rounds = len(rounds_data)

        current_round = None
        next_round = None
        last_completed_round = None
        first_incomplete_round = None

        sorted_rounds = sorted(rounds_data.keys())  # Keys are already integers

        for round_num in sorted_rounds:
            matches = rounds_data.get(round_num, [])  # Use integer key directly
            if not matches:
                continue

            finished_count = 0
            future_count = 0
            live_count = 0

            for match in matches:
                status = match.get('status', '')
                if status == 'finished':
                    finished_count += 1
                elif status in ['live', 'playing', '1H', '2H', 'HT']:
                    live_count += 1
                else:
                    future_count += 1

            total_matches = len(matches)

            # If there are live matches, this is definitely current round
            if live_count > 0:
                current_round = round_num
                last_completed_round = round_num - 1 if round_num > 1 else None
                next_round = round_num + 1 if round_num < total_rounds else None
                break

            # If all matches finished, update last completed
            if finished_count == total_matches:
                last_completed_round = round_num
                continue

            # If some finished and some future (mixed), this is current round
            if finished_count > 0 and future_count > 0:
                current_round = round_num
                next_round = round_num + 1 if round_num < total_rounds else None
                break

            # If all matches are in future and we have a last completed round
            if future_count == total_matches:
                if first_incomplete_round is None:
                    first_incomplete_round = round_num
                if last_completed_round:
                    current_round = last_completed_round
                    next_round = round_num
                    break

        # If we went through all rounds and all are finished (season complete)
        if current_round is None and last_completed_round:
            current_round = last_completed_round
            next_round = None  # Season is over

        # Fallback
        if current_round is None:
            current_round = first_incomplete_round or 1

        return {
            'league_id': league_id,
            'sub_league_id': sub_league_id,
            'season': season,
            'current_round': current_round,
            'next_round': next_round,
            'last_completed_round': last_completed_round,
            'total_rounds': total_rounds,
            'season_completed': current_round == total_rounds and next_round is None
        }

    cache = route_utils._cache_instance
    ttl = get_cache_ttl('current_round')  # 12 hours
    if cache:
        result = get_with_stale_fallback(
            cache_instance=cache,
            cache_key=cache_key,
            fetch_function=fetch_current_round,
            fresh_ttl=ttl,
            stale_ttl=ttl * 2
        )
    else:
        result = fetch_current_round()

    return build_success_response(result)
