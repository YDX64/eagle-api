"""
Live Match Endpoints

Real-time match data with live statistics and odds.
Data sources:
- bf_en-idn.js: Live match list
- detail.js: Technical stats + events
- runOddsData_8.txt: Live odds (Bet365)
- sbCorner.js: Corner statistics
"""
import logging
import time
from flask import Blueprint, request, jsonify

from models import build_success_response, build_error_response, APIError
from app_config import current_config

logger = logging.getLogger(__name__)

# Create live blueprint
live_bp = Blueprint('live', __name__)


# ============================================================================
# LIVE ENDPOINTS
# ============================================================================

@live_bp.route('/matches/live', methods=['GET'])
def get_live_matches():
    """
    Get all currently live matches with real-time statistics and odds.

    Query Parameters:
        include_stats (bool): Include technical stats (default: true)
        include_odds (bool): Include live odds (default: true)
        include_corners (bool): Include corner stats (default: false)
        league_id (int): Filter by league ID
        only_live (bool): Only return live matches, exclude upcoming (default: false)

    Returns:
        JSON response with live matches, stats, and odds
    """
    start_time = time.time()

    try:
        # Parse query parameters
        include_stats = request.args.get('include_stats', 'true').lower() == 'true'
        include_odds = request.args.get('include_odds', 'true').lower() == 'true'
        include_corners = request.args.get('include_corners', 'false').lower() == 'true'
        league_id = request.args.get('league_id', type=int)
        only_live = request.args.get('only_live', 'false').lower() == 'true'

        logger.info(f"📥 REQUEST: /matches/live (stats={include_stats}, odds={include_odds}, corners={include_corners})")

        # Import here to avoid circular imports
        from routes.live_utils import fetch_live_data_cached

        # Fetch live data (cached 30 seconds)
        data = fetch_live_data_cached(
            include_stats=include_stats,
            include_odds=include_odds,
            include_corners=include_corners
        )

        if not data or 'error' in data:
            raise APIError("Failed to fetch live data", 503)

        # Filter matches
        matches = data.get('matches', [])

        # Filter by only_live
        if only_live:
            matches = [m for m in matches if m.get('is_live', False)]

        # Filter by league_id
        if league_id:
            matches = [m for m in matches if m.get('league_id') == league_id]

        # Build response
        response_data = {
            'matches': matches,
            'meta': {
                'total_matches': len(matches),
                'live_count': len([m for m in matches if m.get('is_live')]),
                'last_update': data.get('meta', {}).get('last_update'),
                'cache_ttl': 30,
            }
        }

        # Include leagues info if available
        if data.get('leagues'):
            response_data['leagues'] = data['leagues']

        elapsed_time = time.time() - start_time
        logger.info(f"✅ SUCCESS: /matches/live returned {len(matches)} matches in {elapsed_time:.2f}s")

        return build_success_response(response_data)

    except APIError:
        raise
    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.exception(f"💥 EXCEPTION: /matches/live failed in {elapsed_time:.2f}s - {str(e)}")
        raise APIError("Failed to fetch live matches", 500) from e


@live_bp.route('/matches/live/<int:match_id>', methods=['GET'])
def get_live_match_details(match_id: int):
    """
    Get detailed live data for a specific match.

    Args:
        match_id: Match ID

    Returns:
        JSON response with match details, stats, odds, and events
    """
    start_time = time.time()

    try:
        logger.info(f"📥 REQUEST: /matches/live/{match_id}")

        # Import here to avoid circular imports
        from routes.live_utils import fetch_live_match_details_cached

        # Fetch live match details (cached 30 seconds)
        data = fetch_live_match_details_cached(match_id)

        if not data:
            raise APIError(f"Match {match_id} not found", 404)

        if 'error' in data:
            raise APIError(data['error'], 503)

        elapsed_time = time.time() - start_time
        logger.info(f"✅ SUCCESS: /matches/live/{match_id} in {elapsed_time:.2f}s")

        return build_success_response(data)

    except APIError:
        raise
    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.exception(f"💥 EXCEPTION: /matches/live/{match_id} failed in {elapsed_time:.2f}s - {str(e)}")
        raise APIError(f"Failed to fetch live match {match_id}", 500) from e


@live_bp.route('/matches/live/<int:match_id>/stats', methods=['GET'])
def get_live_match_stats(match_id: int):
    """
    Get technical statistics for a specific live match.

    Stats include:
    - Shots (total, on target, off target)
    - Possession percentage
    - Corners
    - Fouls
    - Yellow/Red cards
    - Attacks & Dangerous attacks
    - Passes & Pass accuracy

    Args:
        match_id: Match ID

    Returns:
        JSON response with match statistics
    """
    start_time = time.time()

    try:
        logger.info(f"📥 REQUEST: /matches/live/{match_id}/stats")

        # Import here to avoid circular imports
        from routes.live_utils import fetch_live_stats_cached

        # Fetch stats (cached 30 seconds)
        data = fetch_live_stats_cached(match_id)

        if not data:
            raise APIError(f"Stats not found for match {match_id}", 404)

        elapsed_time = time.time() - start_time
        logger.info(f"✅ SUCCESS: /matches/live/{match_id}/stats in {elapsed_time:.2f}s")

        return build_success_response({
            'match_id': match_id,
            'stats': data,
            'cache_ttl': 30
        })

    except APIError:
        raise
    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.exception(f"💥 EXCEPTION: /matches/live/{match_id}/stats failed in {elapsed_time:.2f}s")
        raise APIError(f"Failed to fetch stats for match {match_id}", 500) from e


@live_bp.route('/matches/live/<int:match_id>/odds', methods=['GET'])
def get_live_match_odds(match_id: int):
    """
    Get live odds for a specific match.

    Odds include:
    - Asian Handicap (home, line, away)
    - Match Result 1X2 (home, draw, away)
    - Over/Under (over, line, under)
    - Both Teams to Score
    - Double Chance

    Args:
        match_id: Match ID

    Returns:
        JSON response with match odds
    """
    start_time = time.time()

    try:
        logger.info(f"📥 REQUEST: /matches/live/{match_id}/odds")

        # Import here to avoid circular imports
        from routes.live_utils import fetch_live_odds_cached

        # Fetch odds (cached 15 seconds - odds change more frequently)
        data = fetch_live_odds_cached(match_id)

        if not data:
            raise APIError(f"Odds not found for match {match_id}", 404)

        elapsed_time = time.time() - start_time
        logger.info(f"✅ SUCCESS: /matches/live/{match_id}/odds in {elapsed_time:.2f}s")

        return build_success_response({
            'match_id': match_id,
            'odds': data,
            'bookmaker': 'Bet365',
            'cache_ttl': 15
        })

    except APIError:
        raise
    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.exception(f"💥 EXCEPTION: /matches/live/{match_id}/odds failed in {elapsed_time:.2f}s")
        raise APIError(f"Failed to fetch odds for match {match_id}", 500) from e


@live_bp.route('/matches/live/<int:match_id>/corners', methods=['GET'])
def get_live_match_corners(match_id: int):
    """
    Get corner statistics for a specific match.

    Returns:
    - Total corners (home/away)
    - First half corners
    - Corner odds (over/under, handicap)

    Args:
        match_id: Match ID

    Returns:
        JSON response with corner statistics
    """
    start_time = time.time()

    try:
        logger.info(f"📥 REQUEST: /matches/live/{match_id}/corners")

        # Import here to avoid circular imports
        from routes.live_utils import fetch_live_corners_cached

        # Fetch corners (cached 30 seconds)
        data = fetch_live_corners_cached(match_id)

        if not data:
            raise APIError(f"Corner data not found for match {match_id}", 404)

        elapsed_time = time.time() - start_time
        logger.info(f"✅ SUCCESS: /matches/live/{match_id}/corners in {elapsed_time:.2f}s")

        return build_success_response({
            'match_id': match_id,
            'corners': data,
            'cache_ttl': 30
        })

    except APIError:
        raise
    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.exception(f"💥 EXCEPTION: /matches/live/{match_id}/corners failed in {elapsed_time:.2f}s")
        raise APIError(f"Failed to fetch corners for match {match_id}", 500) from e


@live_bp.route('/matches/live/<int:match_id>/events', methods=['GET'])
def get_live_match_events(match_id: int):
    """
    Get live events for a specific match.

    Events include:
    - Goals
    - Yellow/Red cards
    - Substitutions
    - VAR decisions

    Args:
        match_id: Match ID

    Returns:
        JSON response with match events
    """
    start_time = time.time()

    try:
        logger.info(f"📥 REQUEST: /matches/live/{match_id}/events")

        # Import here to avoid circular imports
        from routes.live_utils import fetch_live_events_cached

        # Fetch events (cached 30 seconds)
        data = fetch_live_events_cached(match_id)

        if data is None:
            raise APIError(f"Events not found for match {match_id}", 404)

        elapsed_time = time.time() - start_time
        logger.info(f"✅ SUCCESS: /matches/live/{match_id}/events in {elapsed_time:.2f}s")

        return build_success_response({
            'match_id': match_id,
            'events': data,
            'cache_ttl': 30
        })

    except APIError:
        raise
    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.exception(f"💥 EXCEPTION: /matches/live/{match_id}/events failed in {elapsed_time:.2f}s")
        raise APIError(f"Failed to fetch events for match {match_id}", 500) from e


