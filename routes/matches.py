"""
Match endpoints
"""
import logging
import random
from datetime import datetime, timedelta
from flask import Blueprint, request

from parsers import MatchDateParser
from http_client import fetch_date_data_simple
from models import build_success_response, build_error_response, APIError
from routes.utils import fetch_h2h_data_cached, fetch_odds_data_cached, fetch_date_matches_cached, fetch_match_data_with_analysis_cached
from app_config import current_config

# Create matches blueprint
matches_bp = Blueprint('matches', __name__)

# Initialize parser
date_parser = MatchDateParser()


@matches_bp.route('/match/<int:match_id>', methods=['GET'])
def get_match_details(match_id):
    """
    Get comprehensive match details including team info, statistics and analysis.
    Note: Heavy data (H2H details, odds) are excluded from this response.
    Use /match/<match_id>/h2h for detailed H2H data.
    Use /match/<match_id>/odds for detailed odds data.

    Query Parameters:
        fields (str): Comma-separated list of fields to return (e.g., 'match_id,home_team,away_team')

    Args:
        match_id (int): The unique identifier for the match

    Returns:
        JSON response with match details or error
    """
    logger = logging.getLogger(__name__)
    import time
    start_time = time.time()

    try:
        logger.info(f"📥 REQUEST: /match/{match_id} from {request.remote_addr}")

        # Get field selection parameter
        requested_fields = request.args.get('fields', '')

        # ✅ OPTIMIZED: Fetch with analysis cached together
        # This saves ~1-2 seconds on cache hits (no analysis recalculation)
        data = fetch_match_data_with_analysis_cached(match_id)

        # H2H details ve odds bilgilerini response'dan çıkar (ağır veri)
        # Client sadece analysis sonuçlarını görecek, raw data'yı değil
        data.pop('h2h_details', None)
        data.pop('corner_odds', None)
        data.pop('correct_score_odds', None)
        data.pop('double_chance_odds', None)
        data.pop('first_half_odds', None)
        data.pop('odds_comp', None)

        # Build response
        response = build_success_response(data)

        elapsed_time = time.time() - start_time
        logger.info(f"✅ SUCCESS: /match/{match_id} completed in {elapsed_time:.2f}s")

        return response

    except APIError as e:
        elapsed_time = time.time() - start_time
        # All intermediate errors logged as WARNING - error handler will log as ERROR if needed
        logger.warning(f"⚠️ APIError: /match/{match_id} failed in {elapsed_time:.2f}s - {e.message} (status: {e.status_code})")
        # Re-raise APIError as-is (Flask error handler will catch it)
        raise
    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.warning(f"⚠️ Exception: /match/{match_id} failed in {elapsed_time:.2f}s - {str(e)}")
        # Raise APIError with exception chaining to preserve context
        raise APIError(f"Failed to fetch match details for match {match_id}", 500) from e


@matches_bp.route('/match/<int:match_id>/h2h', methods=['GET'])
def get_match_h2h_details(match_id):
    """
    Get detailed Head-to-Head information for a specific match.

    This endpoint provides comprehensive H2H data including:
    - Head-to-head match history
    - Home team previous matches
    - Away team previous matches
    - Team standings
    - Injuries and suspensions
    - Last match lineups
    - Fixture information

    Args:
        match_id (int): The unique identifier for the match

    Returns:
        JSON response with detailed H2H data
    """
    try:
        # Fetch cached H2H data (3 dakika cache)
        logger = logging.getLogger(__name__)
        data = fetch_h2h_data_cached(match_id)

        # H2H details'i al
        h2h_details = data.get('h2h_details', {})

        if not h2h_details:
            return build_error_response("H2H details not available for this match"), 404

        response = build_success_response(data)
        return response

    except APIError:
        # Re-raise APIError as-is (Flask error handler will catch it)
        raise
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.exception(f"Unexpected error in get_match_h2h_details for match_id={match_id}")
        # Raise APIError with exception chaining to preserve context
        raise APIError(f"Failed to fetch H2H details for match {match_id}", 500) from e


@matches_bp.route('/match/<int:match_id>/odds', methods=['GET'])
def get_match_odds(match_id):
    """
    Get detailed odds information for a specific match.

    This endpoint provides comprehensive odds data including:
    - Corner odds (corner betting markets)
    - Correct score odds (exact score predictions)
    - Double chance odds (combined outcome betting)
    - First half odds (half-time betting markets)
    - Odds comparison (full market odds from multiple bookmakers)

    Args:
        match_id (int): The unique identifier for the match

    Returns:
        JSON response with detailed odds data
    """
    try:
        # Fetch cached odds data (3 dakika cache)
        logger = logging.getLogger(__name__)
        data = fetch_odds_data_cached(match_id)

        # Odds bilgilerini al
        odds_data = data.get('odds_data', {})

        # En az bir oran verisi var mı kontrol et
        has_odds = any([
            odds_data.get('corner_odds'),
            odds_data.get('correct_score_odds'),
            odds_data.get('double_chance_odds'),
            odds_data.get('first_half_odds'),
            odds_data.get('odds_comp')
        ])

        if not has_odds:
            return build_error_response("Odds data not available for this match"), 404

        response = build_success_response(data)
        return response

    except APIError:
        # Re-raise APIError as-is (Flask error handler will catch it)
        raise
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.exception(f"Unexpected error in get_match_odds for match_id={match_id}")
        # Raise APIError with exception chaining to preserve context
        raise APIError(f"Failed to fetch odds data for match {match_id}", 500) from e


@matches_bp.route('/matches/date/<date_str>', methods=['GET'])
def get_matches_by_date(date_str):
    """
    Belirli bir tarihteki maçları getirir.

    Query Parameters:
        sort_by_time (str): Maçları saat sırasına göre sırala (varsayılan: true)

    Args:
        date_str (str): Tarih formatı (YYYY-MM-DD)

    Returns:
        JSON response with matches for the specified date
    """
    try:
        # sort_by_time parametresini oku
        sort_by_time = request.args.get('sort_by_time', 'true').lower() == 'true'

        # Tarih formatını doğrula
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            return build_error_response("Geçersiz tarih formatı. YYYY-MM-DD formatını kullanın"), 400

        # Fetch cached date matches (3 dakika cache)
        logger = logging.getLogger(__name__)
        result = fetch_date_matches_cached(date_str, sort_by_time=sort_by_time)

        if not result or not result.get('matches'):
            return build_error_response("Bu tarih için maç verisi bulunamadı"), 404

        return build_success_response(result)

    except APIError:
        # Re-raise APIError as-is (Flask error handler will catch it)
        raise
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.exception(f"Error getting matches for date {date_str}")
        # Raise APIError with exception chaining to preserve context
        raise APIError(f"Failed to fetch matches for date {date_str}", 500) from e


@matches_bp.route('/matches/today', methods=['GET'])
def get_today_matches():
    """
    Bugünkü maçları getirir.

    Query Parameters:
        sort_by_time (str): Maçları saat sırasına göre sırala (varsayılan: true)

    Returns:
        JSON response with today's matches
    """
    try:
        logger = logging.getLogger(__name__)
        today = datetime.now().strftime('%Y-%m-%d')
        logger.info(f"📅 Getting matches for today: {today}")

        # get_matches_by_date fonksiyonunu çağır
        return get_matches_by_date(today)

    except APIError:
        # Re-raise APIError as-is (Flask error handler will catch it)
        raise
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.exception(f"Error getting today's matches")
        # Raise APIError with exception chaining to preserve context
        raise APIError("Failed to fetch today's matches", 500) from e


@matches_bp.route('/matches/tomorrow', methods=['GET'])
def get_tomorrow_matches():
    """
    Yarınki maçları getirir.

    Query Parameters:
        sort_by_time (str): Maçları saat sırasına göre sırala (varsayılan: true)

    Returns:
        JSON response with tomorrow's matches
    """
    try:
        tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')

        # get_matches_by_date fonksiyonunu çağır
        return get_matches_by_date(tomorrow)

    except APIError:
        # Re-raise APIError as-is (Flask error handler will catch it)
        raise
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.exception(f"Error getting tomorrow's matches")
        # Raise APIError with exception chaining to preserve context
        raise APIError("Failed to fetch tomorrow's matches", 500) from e


@matches_bp.route('/matches/yesterday', methods=['GET'])
def get_yesterday_matches():
    """
    Dünkü maçları getirir.

    Query Parameters:
        sort_by_time (str): Maçları saat sırasına göre sırala (varsayılan: true)

    Returns:
        JSON response with yesterday's matches
    """
    try:
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

        # get_matches_by_date fonksiyonunu çağır
        return get_matches_by_date(yesterday)

    except APIError:
        # Re-raise APIError as-is (Flask error handler will catch it)
        raise
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.exception(f"Error getting yesterday's matches")
        # Raise APIError with exception chaining to preserve context
        raise APIError("Failed to fetch yesterday's matches", 500) from e


