"""
League endpoints - List all leagues and their information
"""
import json
import logging
import os
import random
from datetime import datetime
from flask import Blueprint, request

from parsers import MatchDateParser
from http_client import fetch_date_data_simple
from models import build_success_response, APIError
from app_config import current_config

# Create leagues blueprint
leagues_bp = Blueprint('leagues', __name__)

# Initialize parser
date_parser = MatchDateParser()
logger = logging.getLogger(__name__)

# Load leagues data from JSON file
LEAGUES_DATA = None

def load_leagues_data():
    """Load leagues data from JSON file"""
    global LEAGUES_DATA
    if LEAGUES_DATA is None:
        json_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'leagues.json')
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                LEAGUES_DATA = json.load(f)
                logger.info(f"Loaded {LEAGUES_DATA['metadata']['total_leagues']} leagues from JSON")
        except FileNotFoundError:
            logger.warning(f"Leagues JSON not found at {json_path}")
            LEAGUES_DATA = {"leagues": {}, "top_leagues": [], "cups": []}
        except Exception as e:
            logger.error(f"Error loading leagues JSON: {e}")
            LEAGUES_DATA = {"leagues": {}, "top_leagues": [], "cups": []}
    return LEAGUES_DATA


@leagues_bp.route('/leagues', methods=['GET'])
def get_leagues():
    """Tüm ligleri listele"""
    try:
        # Bugünkü tarihi al
        today = datetime.now().strftime('%Y-%m-%d')

        # Bugünkü maç verisini çek (recursive çağrı olmadan)
        formatted_date = f"{datetime.now().year}-{datetime.now().month}-{datetime.now().day}"

        # API URL'ini oluştur (config'den)
        base_url = current_config.NOWGOAL_BASE_URL
        endpoints = current_config.NOWGOAL_ENDPOINTS
        api_url = f"{base_url}{endpoints['matches_by_date'].format(date=formatted_date, random=random.random())}"

        response_text = fetch_date_data_simple(api_url)
        parsed_data = date_parser.parse_date_response(response_text)

        leagues = {}
        if parsed_data and 'leagues' in parsed_data:
            for league_key, league_info in parsed_data['leagues'].items():
                # league_key hem string hem integer olabilir, string'e çevir
                league_id = str(league_key)
                leagues[league_id] = {
                    'id': league_id,
                    'name': league_info.get('league_name', 'Unknown'),
                    'code': league_info.get('league_code', '')
                }

        # Ligleri ID'ye göre sırala
        leagues_list = sorted(leagues.values(), key=lambda x: int(x['id']))

        return build_success_response({
            'leagues': leagues_list,
            'count': len(leagues_list)
        })

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.exception(f"Error getting leagues")
        # Import APIError
        from models import APIError
        # Raise APIError with exception chaining to preserve context
        raise APIError("Failed to fetch leagues", 500) from e


# DEPRECATED: This route is replaced by the more comprehensive
# /leagues/<int:league_id>/matches endpoint in league_data.py
# which supports season and round parameters
#
# @leagues_bp.route('/leagues/<int:league_id>/matches', methods=['GET'])
# def get_league_matches(league_id):
#     """Belirli bir ligin maçlarını getir"""
#     ... (moved to routes/league_data.py)


@leagues_bp.route('/leagues/all', methods=['GET'])
def get_all_leagues():
    """
    Get all available leagues organized by country

    Query params:
        - country: Filter by country code (e.g., 'england', 'turkey')
        - type: Filter by type ('league', 'subleague', 'cup')

    Example: /api/v1/leagues/all
    Example: /api/v1/leagues/all?country=england
    Example: /api/v1/leagues/all?type=cup
    """
    try:
        data = load_leagues_data()

        country_filter = request.args.get('country', '').lower()
        type_filter = request.args.get('type', '').lower()

        result = {
            'metadata': data.get('metadata', {}),
            'top_leagues': data.get('top_leagues', []),
            'cups': data.get('cups', []),
            'leagues': {}
        }

        # Apply country filter
        if country_filter:
            if country_filter in data.get('leagues', {}):
                result['leagues'] = {country_filter: data['leagues'][country_filter]}
            else:
                result['leagues'] = {}
        else:
            result['leagues'] = data.get('leagues', {})

        # Apply type filter to cups
        if type_filter == 'cup':
            result['top_leagues'] = []
            result['leagues'] = {}
        elif type_filter in ['league', 'subleague']:
            result['cups'] = []
            # Filter leagues by type
            filtered_leagues = {}
            for country, leagues_list in result['leagues'].items():
                filtered = [l for l in leagues_list if l.get('type') == type_filter]
                if filtered:
                    filtered_leagues[country] = filtered
            result['leagues'] = filtered_leagues

        return build_success_response(result)

    except Exception as e:
        logger.exception("Error getting all leagues")
        raise APIError("Failed to fetch leagues data", 500) from e


@leagues_bp.route('/leagues/top', methods=['GET'])
def get_top_leagues():
    """
    Get top/popular leagues (Big 5 + major cups)

    Example: /api/v1/leagues/top
    """
    try:
        data = load_leagues_data()

        return build_success_response({
            'top_leagues': data.get('top_leagues', []),
            'major_cups': data.get('cups', [])[:5],  # Top 5 cups
            'count': len(data.get('top_leagues', [])) + 5
        })

    except Exception as e:
        logger.exception("Error getting top leagues")
        raise APIError("Failed to fetch top leagues", 500) from e


@leagues_bp.route('/leagues/countries', methods=['GET'])
def get_countries():
    """
    Get list of countries with leagues

    Example: /api/v1/leagues/countries
    """
    try:
        data = load_leagues_data()

        countries = []
        for country_code, leagues_list in data.get('leagues', {}).items():
            countries.append({
                'code': country_code,
                'name': country_code.replace('_', ' ').title(),
                'league_count': len(leagues_list)
            })

        # Sort by league count (descending)
        countries.sort(key=lambda x: x['league_count'], reverse=True)

        return build_success_response({
            'countries': countries,
            'count': len(countries)
        })

    except Exception as e:
        logger.exception("Error getting countries")
        raise APIError("Failed to fetch countries", 500) from e


@leagues_bp.route('/leagues/<int:league_id>/lookup', methods=['GET'])
def lookup_league(league_id: int):
    """
    Lookup league details by ID

    Example: /api/v1/leagues/36/lookup
    """
    try:
        data = load_leagues_data()

        # Search in top leagues
        for league in data.get('top_leagues', []):
            if league.get('id') == league_id:
                return build_success_response({
                    'league': league,
                    'found_in': 'top_leagues'
                })

        # Search in cups
        for cup in data.get('cups', []):
            if cup.get('id') == league_id:
                return build_success_response({
                    'league': cup,
                    'found_in': 'cups'
                })

        # Search in country leagues
        for country, leagues_list in data.get('leagues', {}).items():
            for league in leagues_list:
                if league.get('id') == league_id:
                    league_copy = league.copy()
                    league_copy['country'] = country
                    return build_success_response({
                        'league': league_copy,
                        'found_in': f'leagues.{country}'
                    })

        # Check sub_league_mappings
        sub_mappings = data.get('sub_league_mappings', {})
        if str(league_id) in sub_mappings:
            return build_success_response({
                'league': {
                    'id': league_id,
                    'name': sub_mappings[str(league_id)]['name'],
                    'sub_league_id': sub_mappings[str(league_id)]['sub_league_id'],
                    'type': 'subleague'
                },
                'found_in': 'sub_league_mappings'
            })

        raise APIError(f"League {league_id} not found", 404)

    except APIError:
        raise
    except Exception as e:
        logger.exception(f"Error looking up league {league_id}")
        raise APIError("Failed to lookup league", 500) from e
