"""
Unit tests for leagues system

Tests cover:
- load_leagues_data() function
- /leagues endpoint
- /leagues/all endpoint
- /leagues/top endpoint
- /leagues/countries endpoint
- /leagues/<id>/lookup endpoint
"""
import json
import pytest
from unittest.mock import patch, MagicMock, mock_open


class TestLoadLeaguesData:
    """Tests for load_leagues_data function"""

    def test_load_leagues_data_success(self, sample_leagues_data):
        """Test successful loading of leagues data from JSON"""
        from routes.leagues import load_leagues_data, LEAGUES_DATA
        import routes.leagues as leagues_module

        # Reset global state
        leagues_module.LEAGUES_DATA = None

        json_content = json.dumps(sample_leagues_data)

        with patch('builtins.open', mock_open(read_data=json_content)):
            result = load_leagues_data()

        assert result is not None
        assert 'metadata' in result
        assert 'top_leagues' in result
        assert 'cups' in result
        assert 'leagues' in result

        # Reset for other tests
        leagues_module.LEAGUES_DATA = None

    def test_load_leagues_data_file_not_found(self):
        """Test handling of missing JSON file"""
        from routes.leagues import load_leagues_data
        import routes.leagues as leagues_module

        # Reset global state
        leagues_module.LEAGUES_DATA = None

        with patch('builtins.open', side_effect=FileNotFoundError):
            result = load_leagues_data()

        assert result == {"leagues": {}, "top_leagues": [], "cups": []}

        # Reset for other tests
        leagues_module.LEAGUES_DATA = None

    def test_load_leagues_data_json_error(self):
        """Test handling of invalid JSON"""
        from routes.leagues import load_leagues_data
        import routes.leagues as leagues_module

        # Reset global state
        leagues_module.LEAGUES_DATA = None

        with patch('builtins.open', mock_open(read_data="invalid json")):
            result = load_leagues_data()

        assert result == {"leagues": {}, "top_leagues": [], "cups": []}

        # Reset for other tests
        leagues_module.LEAGUES_DATA = None

    def test_load_leagues_data_caching(self, sample_leagues_data):
        """Test that data is cached after first load"""
        import routes.leagues as leagues_module

        # Reset global state
        leagues_module.LEAGUES_DATA = None

        json_content = json.dumps(sample_leagues_data)

        open_mock = mock_open(read_data=json_content)
        with patch('builtins.open', open_mock):
            result1 = leagues_module.load_leagues_data()
            result2 = leagues_module.load_leagues_data()

        # Should only open file once due to caching
        assert open_mock.call_count == 1
        assert result1 is result2

        # Reset for other tests
        leagues_module.LEAGUES_DATA = None


class TestGetLeaguesEndpoint:
    """Tests for /leagues endpoint"""

    def test_get_leagues_success(self, client, sample_date_response):
        """Test successful leagues fetch"""
        with patch('routes.leagues.fetch_date_data_simple') as mock_fetch, \
             patch.object(__import__('routes.leagues', fromlist=['date_parser']).date_parser,
                         'parse_date_response', return_value=sample_date_response):
            mock_fetch.return_value = "mocked"

            response = client.get('/api/v1/leagues')

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert 'leagues' in data['data']
        assert 'count' in data['data']

    def test_get_leagues_empty_result(self, client):
        """Test leagues endpoint with empty response"""
        with patch('routes.leagues.fetch_date_data_simple') as mock_fetch, \
             patch.object(__import__('routes.leagues', fromlist=['date_parser']).date_parser,
                         'parse_date_response', return_value={}):
            mock_fetch.return_value = "mocked"

            response = client.get('/api/v1/leagues')

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['data']['leagues'] == []
        assert data['data']['count'] == 0

    def test_get_leagues_sorts_by_id(self, client):
        """Test that leagues are sorted by ID"""
        sample_response = {
            "leagues": {
                "100": {"league_name": "League Z", "league_code": "Z"},
                "50": {"league_name": "League A", "league_code": "A"},
                "75": {"league_name": "League M", "league_code": "M"}
            }
        }

        with patch('routes.leagues.fetch_date_data_simple') as mock_fetch, \
             patch.object(__import__('routes.leagues', fromlist=['date_parser']).date_parser,
                         'parse_date_response', return_value=sample_response):
            mock_fetch.return_value = "mocked"

            response = client.get('/api/v1/leagues')

        assert response.status_code == 200
        data = response.get_json()
        leagues = data['data']['leagues']

        # Verify sorted by ID
        ids = [int(l['id']) for l in leagues]
        assert ids == sorted(ids)


class TestGetAllLeaguesEndpoint:
    """Tests for /leagues/all endpoint"""

    def test_get_all_leagues_success(self, client, sample_leagues_data):
        """Test successful fetch of all leagues"""
        import routes.leagues as leagues_module
        leagues_module.LEAGUES_DATA = sample_leagues_data

        response = client.get('/api/v1/leagues/all')

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert 'metadata' in data['data']
        assert 'top_leagues' in data['data']
        assert 'cups' in data['data']
        assert 'leagues' in data['data']

        leagues_module.LEAGUES_DATA = None

    def test_get_all_leagues_filter_by_country(self, client, sample_leagues_data):
        """Test filtering by country"""
        import routes.leagues as leagues_module
        leagues_module.LEAGUES_DATA = sample_leagues_data

        response = client.get('/api/v1/leagues/all?country=england')

        assert response.status_code == 200
        data = response.get_json()
        assert 'england' in data['data']['leagues']
        assert 'turkey' not in data['data']['leagues']
        assert 'germany' not in data['data']['leagues']

        leagues_module.LEAGUES_DATA = None

    def test_get_all_leagues_filter_by_country_not_found(self, client, sample_leagues_data):
        """Test filtering by non-existent country"""
        import routes.leagues as leagues_module
        leagues_module.LEAGUES_DATA = sample_leagues_data

        response = client.get('/api/v1/leagues/all?country=nonexistent')

        assert response.status_code == 200
        data = response.get_json()
        assert data['data']['leagues'] == {}

        leagues_module.LEAGUES_DATA = None

    def test_get_all_leagues_filter_by_type_cup(self, client, sample_leagues_data):
        """Test filtering by cup type"""
        import routes.leagues as leagues_module
        leagues_module.LEAGUES_DATA = sample_leagues_data

        response = client.get('/api/v1/leagues/all?type=cup')

        assert response.status_code == 200
        data = response.get_json()
        assert data['data']['top_leagues'] == []
        assert data['data']['leagues'] == {}
        assert len(data['data']['cups']) > 0

        leagues_module.LEAGUES_DATA = None

    def test_get_all_leagues_filter_by_type_league(self, client, sample_leagues_data):
        """Test filtering by league type"""
        import routes.leagues as leagues_module
        leagues_module.LEAGUES_DATA = sample_leagues_data

        response = client.get('/api/v1/leagues/all?type=league')

        assert response.status_code == 200
        data = response.get_json()
        assert data['data']['cups'] == []
        # Should only contain leagues with type='league'
        for country, leagues in data['data']['leagues'].items():
            for league in leagues:
                assert league.get('type') == 'league'

        leagues_module.LEAGUES_DATA = None

    def test_get_all_leagues_filter_by_type_subleague(self, client, sample_leagues_data):
        """Test filtering by subleague type"""
        import routes.leagues as leagues_module
        leagues_module.LEAGUES_DATA = sample_leagues_data

        response = client.get('/api/v1/leagues/all?type=subleague')

        assert response.status_code == 200
        data = response.get_json()
        assert data['data']['cups'] == []
        # Should only contain subleagues
        for country, leagues in data['data']['leagues'].items():
            for league in leagues:
                assert league.get('type') == 'subleague'

        leagues_module.LEAGUES_DATA = None


class TestGetTopLeaguesEndpoint:
    """Tests for /leagues/top endpoint"""

    def test_get_top_leagues_success(self, client, sample_leagues_data):
        """Test successful fetch of top leagues"""
        import routes.leagues as leagues_module
        leagues_module.LEAGUES_DATA = sample_leagues_data

        response = client.get('/api/v1/leagues/top')

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert 'top_leagues' in data['data']
        assert 'major_cups' in data['data']
        assert 'count' in data['data']

        leagues_module.LEAGUES_DATA = None

    def test_get_top_leagues_contains_expected_leagues(self, client, sample_leagues_data):
        """Test that top leagues contain expected data"""
        import routes.leagues as leagues_module
        leagues_module.LEAGUES_DATA = sample_leagues_data

        response = client.get('/api/v1/leagues/top')

        data = response.get_json()
        top_leagues = data['data']['top_leagues']

        # Verify Premier League is in top leagues
        pl_found = any(l['name'] == 'English Premier League' for l in top_leagues)
        assert pl_found

        leagues_module.LEAGUES_DATA = None

    def test_get_top_leagues_limits_cups_to_five(self, client, sample_leagues_data):
        """Test that major cups are limited to 5"""
        import routes.leagues as leagues_module
        # Add more cups to test limit
        data_with_many_cups = sample_leagues_data.copy()
        data_with_many_cups['cups'] = [{'id': i, 'name': f'Cup {i}'} for i in range(10)]
        leagues_module.LEAGUES_DATA = data_with_many_cups

        response = client.get('/api/v1/leagues/top')

        data = response.get_json()
        assert len(data['data']['major_cups']) == 5

        leagues_module.LEAGUES_DATA = None

    def test_get_top_leagues_empty_data(self, client):
        """Test with empty leagues data"""
        import routes.leagues as leagues_module
        leagues_module.LEAGUES_DATA = {"leagues": {}, "top_leagues": [], "cups": []}

        response = client.get('/api/v1/leagues/top')

        assert response.status_code == 200
        data = response.get_json()
        assert data['data']['top_leagues'] == []
        assert data['data']['major_cups'] == []
        assert data['data']['count'] == 5  # 0 + 5 (even with empty cups, count includes 5)

        leagues_module.LEAGUES_DATA = None


class TestGetCountriesEndpoint:
    """Tests for /leagues/countries endpoint"""

    def test_get_countries_success(self, client, sample_leagues_data):
        """Test successful fetch of countries"""
        import routes.leagues as leagues_module
        leagues_module.LEAGUES_DATA = sample_leagues_data

        response = client.get('/api/v1/leagues/countries')

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert 'countries' in data['data']
        assert 'count' in data['data']

        leagues_module.LEAGUES_DATA = None

    def test_get_countries_sorted_by_league_count(self, client, sample_leagues_data):
        """Test that countries are sorted by league count (descending)"""
        import routes.leagues as leagues_module
        leagues_module.LEAGUES_DATA = sample_leagues_data

        response = client.get('/api/v1/leagues/countries')

        data = response.get_json()
        countries = data['data']['countries']

        # Verify sorted by league_count descending
        league_counts = [c['league_count'] for c in countries]
        assert league_counts == sorted(league_counts, reverse=True)

        leagues_module.LEAGUES_DATA = None

    def test_get_countries_correct_count(self, client, sample_leagues_data):
        """Test that country count is correct"""
        import routes.leagues as leagues_module
        leagues_module.LEAGUES_DATA = sample_leagues_data

        response = client.get('/api/v1/leagues/countries')

        data = response.get_json()
        assert data['data']['count'] == 3  # england, turkey, germany

        leagues_module.LEAGUES_DATA = None

    def test_get_countries_name_formatting(self, client, sample_leagues_data):
        """Test that country names are properly formatted"""
        import routes.leagues as leagues_module
        leagues_module.LEAGUES_DATA = sample_leagues_data

        response = client.get('/api/v1/leagues/countries')

        data = response.get_json()
        countries = data['data']['countries']

        # Find england
        england = next((c for c in countries if c['code'] == 'england'), None)
        assert england is not None
        assert england['name'] == 'England'

        leagues_module.LEAGUES_DATA = None

    def test_get_countries_empty_leagues(self, client):
        """Test with no leagues"""
        import routes.leagues as leagues_module
        leagues_module.LEAGUES_DATA = {"leagues": {}, "top_leagues": [], "cups": []}

        response = client.get('/api/v1/leagues/countries')

        assert response.status_code == 200
        data = response.get_json()
        assert data['data']['countries'] == []
        assert data['data']['count'] == 0

        leagues_module.LEAGUES_DATA = None


class TestLookupLeagueEndpoint:
    """Tests for /leagues/<id>/lookup endpoint"""

    def test_lookup_league_in_top_leagues(self, client, sample_leagues_data):
        """Test looking up a top league"""
        import routes.leagues as leagues_module
        leagues_module.LEAGUES_DATA = sample_leagues_data

        response = client.get('/api/v1/leagues/36/lookup')

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['data']['found_in'] == 'top_leagues'
        assert data['data']['league']['name'] == 'English Premier League'

        leagues_module.LEAGUES_DATA = None

    def test_lookup_league_in_cups(self, client, sample_leagues_data):
        """Test looking up a cup"""
        import routes.leagues as leagues_module
        leagues_module.LEAGUES_DATA = sample_leagues_data

        response = client.get('/api/v1/leagues/90/lookup')

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['data']['found_in'] == 'cups'
        assert data['data']['league']['name'] == 'FA Cup'

        leagues_module.LEAGUES_DATA = None

    def test_lookup_league_in_country_leagues(self, client, sample_leagues_data):
        """Test looking up a league by country"""
        import routes.leagues as leagues_module
        leagues_module.LEAGUES_DATA = sample_leagues_data

        response = client.get('/api/v1/leagues/52/lookup')

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['data']['found_in'] == 'leagues.turkey'
        assert data['data']['league']['name'] == 'Super Lig'
        assert data['data']['league']['country'] == 'turkey'

        leagues_module.LEAGUES_DATA = None

    def test_lookup_league_in_sub_mappings(self, client, sample_leagues_data):
        """Test looking up a subleague from mappings"""
        import routes.leagues as leagues_module
        leagues_module.LEAGUES_DATA = sample_leagues_data

        response = client.get('/api/v1/leagues/37/lookup')

        assert response.status_code == 200
        data = response.get_json()
        # Should find in country leagues first
        assert data['success'] is True

        leagues_module.LEAGUES_DATA = None

    def test_lookup_league_not_found(self, client, sample_leagues_data):
        """Test looking up non-existent league"""
        import routes.leagues as leagues_module
        leagues_module.LEAGUES_DATA = sample_leagues_data

        response = client.get('/api/v1/leagues/99999/lookup')

        assert response.status_code == 404
        data = response.get_json()
        assert 'error' in data

        leagues_module.LEAGUES_DATA = None

    def test_lookup_league_invalid_id(self, client, sample_leagues_data):
        """Test looking up with invalid ID format"""
        import routes.leagues as leagues_module
        leagues_module.LEAGUES_DATA = sample_leagues_data

        response = client.get('/api/v1/leagues/invalid/lookup')

        assert response.status_code == 404  # Flask returns 404 for route mismatch

        leagues_module.LEAGUES_DATA = None


class TestEdgeCases:
    """Edge case tests for leagues system"""

    def test_concurrent_load_leagues_data(self, sample_leagues_data):
        """Test thread safety of load_leagues_data"""
        import routes.leagues as leagues_module
        import threading

        leagues_module.LEAGUES_DATA = None
        json_content = json.dumps(sample_leagues_data)
        results = []

        def load_data():
            with patch('builtins.open', mock_open(read_data=json_content)):
                result = leagues_module.load_leagues_data()
                results.append(result)

        threads = [threading.Thread(target=load_data) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All results should be the same object
        assert all(r is results[0] for r in results)

        leagues_module.LEAGUES_DATA = None

    def test_special_characters_in_country_name(self, client):
        """Test country names with underscores are formatted correctly"""
        import routes.leagues as leagues_module
        leagues_module.LEAGUES_DATA = {
            "leagues": {
                "south_korea": [{"id": 1, "name": "K League", "type": "league"}]
            },
            "top_leagues": [],
            "cups": []
        }

        response = client.get('/api/v1/leagues/countries')

        data = response.get_json()
        country = data['data']['countries'][0]
        assert country['name'] == 'South Korea'

        leagues_module.LEAGUES_DATA = None

    def test_leagues_with_missing_fields(self, client):
        """Test handling of leagues with missing optional fields"""
        import routes.leagues as leagues_module
        leagues_module.LEAGUES_DATA = {
            "leagues": {
                "test": [{"id": 1}]  # Minimal league data
            },
            "top_leagues": [],
            "cups": []
        }

        response = client.get('/api/v1/leagues/all')

        assert response.status_code == 200

        leagues_module.LEAGUES_DATA = None

    def test_empty_string_filter(self, client, sample_leagues_data):
        """Test filtering with empty string returns all data"""
        import routes.leagues as leagues_module
        leagues_module.LEAGUES_DATA = sample_leagues_data

        response = client.get('/api/v1/leagues/all?country=')

        assert response.status_code == 200
        data = response.get_json()
        # Empty filter should return all leagues
        assert len(data['data']['leagues']) == 3

        leagues_module.LEAGUES_DATA = None

    def test_case_insensitive_country_filter(self, client, sample_leagues_data):
        """Test that country filter is case insensitive"""
        import routes.leagues as leagues_module
        leagues_module.LEAGUES_DATA = sample_leagues_data

        response = client.get('/api/v1/leagues/all?country=ENGLAND')

        assert response.status_code == 200
        data = response.get_json()
        assert 'england' in data['data']['leagues']

        leagues_module.LEAGUES_DATA = None
