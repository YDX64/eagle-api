"""
Team endpoints
"""
import logging
import random
from datetime import datetime
from flask import Blueprint, request

from parsers import MatchDateParser
from http_client import fetch_date_data_simple
from models import build_success_response, build_error_response
from app_config import current_config

# Create teams blueprint
teams_bp = Blueprint('teams', __name__)

# Initialize parser
date_parser = MatchDateParser()


@teams_bp.route('/teams/search', methods=['GET'])
def search_teams():
    """Takım ara"""
    try:
        query = request.args.get('q', '').strip()
        if not query:
            return build_error_response("Arama sorgusu gerekli (q parametresi)"), 400

        # Bugünkü maç verisini çek (recursive çağrı olmadan)
        formatted_date = f"{datetime.now().year}-{datetime.now().month}-{datetime.now().day}"

        # API URL'ini oluştur (config'den)
        base_url = current_config.NOWGOAL_BASE_URL
        endpoints = current_config.NOWGOAL_ENDPOINTS
        api_url = f"{base_url}{endpoints['matches_by_date'].format(date=formatted_date, random=random.random())}"

        response_text = fetch_date_data_simple(api_url)
        parsed_data = date_parser.parse_date_response(response_text)

        found_teams = []
        if parsed_data and 'matches' in parsed_data:
            for match in parsed_data['matches']:
                home_team = match.get('home_team', '')
                away_team = match.get('away_team', '')

                # Lig bilgisini hem string hem integer olarak ara
                league_id = match.get('league_id')
                league_info = parsed_data['leagues'].get(str(league_id), {}) or parsed_data['leagues'].get(league_id, {})

                # Takım adında arama sorgusu varsa ekle
                if query.lower() in home_team.lower() and home_team not in [t['name'] for t in found_teams]:
                    found_teams.append({
                        'name': home_team,
                        'type': 'home_team',
                        'match_id': match.get('match_id'),
                        'league': league_info.get('league_name', 'Unknown'),
                        'league_id': match.get('league_id')
                    })

                if query.lower() in away_team.lower() and away_team not in [t['name'] for t in found_teams]:
                    found_teams.append({
                        'name': away_team,
                        'type': 'away_team',
                        'match_id': match.get('match_id'),
                        'league': league_info.get('league_name', 'Unknown'),
                        'league_id': match.get('league_id')
                    })

        result = {
            'query': query,
            'teams': found_teams,
            'count': len(found_teams)
        }

        return build_success_response(result)

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.exception(f"Error searching teams with query='{query}'")
        # Import APIError
        from models import APIError
        # Raise APIError with exception chaining to preserve context
        raise APIError(f"Failed to search teams", 500) from e


@teams_bp.route('/teams/<path:team_name>/matches', methods=['GET'])
def get_team_matches(team_name):
    """Belirli bir takıma ait maçları getir"""
    try:
        # Bugünkü maç verisini çek (recursive çağrı olmadan)
        formatted_date = f"{datetime.now().year}-{datetime.now().month}-{datetime.now().day}"

        # API URL'ini oluştur (config'den)
        base_url = current_config.NOWGOAL_BASE_URL
        endpoints = current_config.NOWGOAL_ENDPOINTS
        api_url = f"{base_url}{endpoints['matches_by_date'].format(date=formatted_date, random=random.random())}"

        response_text = fetch_date_data_simple(api_url)
        parsed_data = date_parser.parse_date_response(response_text)

        team_matches = []
        if parsed_data and 'matches' in parsed_data:
            for match in parsed_data['matches']:
                home_team = match.get('home_team', '')
                away_team = match.get('away_team', '')

                if (home_team.lower() == team_name.lower() or
                    away_team.lower() == team_name.lower()):

                    # Lig bilgisini hem string hem integer olarak ara
                    league_id = match.get('league_id')
                    league_info = parsed_data['leagues'].get(str(league_id), {}) or parsed_data['leagues'].get(league_id, {})

                    team_matches.append({
                        'match_id': match['match_id'],
                        'home_team': match['home_team'],
                        'away_team': match['away_team'],
                        'match_time': match['match_time'].isoformat() if match['match_time'] else None,
                        'league': {
                            'id': match.get('league_id'),
                            'name': league_info.get('league_name', 'Unknown'),
                            'code': league_info.get('league_code', '')
                        },
                        'is_home': home_team.lower() == team_name.lower()
                    })

        result = {
            'team_name': team_name,
            'matches': team_matches,
            'count': len(team_matches)
        }

        return build_success_response(result)

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.exception(f"Error getting team matches for team_name='{team_name}'")
        # Import APIError
        from models import APIError
        # Raise APIError with exception chaining to preserve context
        raise APIError(f"Failed to fetch matches for team {team_name}", 500) from e
