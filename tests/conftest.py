"""
Test configuration and fixtures for Golsinyali API tests
"""
import os
import sys
import json
import pytest
from unittest.mock import patch, MagicMock

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set testing environment before importing app
os.environ['FLASK_ENV'] = 'testing'
os.environ['TESTING'] = 'true'

from app import app as flask_app


@pytest.fixture
def app():
    """Create application for testing"""
    flask_app.config.update({
        'TESTING': True,
    })
    return flask_app


@pytest.fixture
def client(app):
    """Create test client"""
    return app.test_client()


@pytest.fixture
def sample_leagues_data():
    """Sample leagues data for testing"""
    return {
        "metadata": {
            "source": "test",
            "fetched_at": "2025-12-27T02:08:26.489691",
            "total_countries": 3,
            "total_leagues": 10
        },
        "top_leagues": [
            {
                "id": 36,
                "code": "ENG PR",
                "name": "English Premier League",
                "type": "league",
                "country": "England",
                "continent": "europe",
                "current_season": "2025-2026",
                "available_seasons": ["2025-2026", "2024-2025"]
            },
            {
                "id": 31,
                "code": "SPA D1",
                "name": "La Liga",
                "type": "league",
                "country": "Spain",
                "continent": "europe",
                "current_season": "2025-2026",
                "available_seasons": ["2025-2026", "2024-2025"]
            }
        ],
        "cups": [
            {
                "id": 90,
                "code": "ENG FAC",
                "name": "FA Cup",
                "type": "cup",
                "country": "England",
                "continent": "europe",
                "current_season": "2025-2026",
                "available_seasons": ["2025-2026"]
            },
            {
                "id": 132,
                "code": "UCL",
                "name": "UEFA Champions League",
                "type": "cup",
                "country": "Europe",
                "continent": "europe",
                "current_season": "2025-2026",
                "available_seasons": ["2025-2026"]
            }
        ],
        "leagues": {
            "england": [
                {
                    "id": 36,
                    "code": "ENG PR",
                    "name": "English Premier League",
                    "type": "league"
                },
                {
                    "id": 37,
                    "code": "ENG CH",
                    "name": "Championship",
                    "type": "subleague"
                }
            ],
            "turkey": [
                {
                    "id": 52,
                    "code": "TUR D1",
                    "name": "Super Lig",
                    "type": "league"
                }
            ],
            "germany": [
                {
                    "id": 8,
                    "code": "GER D1",
                    "name": "Bundesliga",
                    "type": "league"
                }
            ]
        },
        "sub_league_mappings": {
            "37": {
                "name": "Championship",
                "sub_league_id": 2
            }
        }
    }


@pytest.fixture
def sample_date_response():
    """Sample date response from parser"""
    return {
        "leagues": {
            "36": {
                "league_name": "English Premier League",
                "league_code": "ENG PR"
            },
            "52": {
                "league_name": "Super Lig",
                "league_code": "TUR D1"
            }
        }
    }


@pytest.fixture
def mock_fetch_date_data():
    """Mock for fetch_date_data_simple"""
    return "mocked response text"
