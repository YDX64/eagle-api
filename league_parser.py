"""
League Data Parser - Parses league standings, matches, and odds data
from football.nowgoal26.com
"""
import re
import json
import logging
from typing import Dict, List, Optional, Any, Tuple

logger = logging.getLogger(__name__)


def extract_sub_league_id(html_content: str) -> Optional[int]:
    """
    Extract SubSclassID from league page HTML/JS

    The league page contains: var SubSclassID = 918;

    For cups with SubSclassID=0, tries to find first valid sub_league_id from arrSubLeague.

    Args:
        html_content: Raw HTML content from /league/{league_id} page

    Returns:
        sub_league_id or None if not found
    """
    if not html_content:
        return None

    try:
        # Look for: var SubSclassID = 918;
        match = re.search(r'var\s+SubSclassID\s*=\s*(\d+)\s*;', html_content)
        if match:
            sub_league_id = int(match.group(1))

            # If SubSclassID is 0, try to get first valid ID from arrSubLeague
            # (Inline parsing to avoid circular dependency with extract_all_sub_leagues)
            if sub_league_id == 0:
                logger.debug("SubSclassID is 0, checking arrSubLeague for valid ID")

                # Look for arrSubLeague definition - inline parsing
                arr_match = re.search(r'var\s+arrSubLeague\s*=\s*\[(.*?)\];', html_content, re.DOTALL)
                if arr_match:
                    arr_content = arr_match.group(1)
                    # Find first valid sub_league_id
                    sub_ids = re.findall(r'\[(\d+),', arr_content)
                    for sid in sub_ids:
                        sid_int = int(sid)
                        if sid_int > 0:
                            logger.info(f"Found valid sub_league_id from arrSubLeague: {sid_int}")
                            return sid_int

                # SubSclassID=0 and no valid arrSubLeague - this is a cup without sub-leagues
                logger.debug("SubSclassID=0 and no valid arrSubLeague found")
                return None

            logger.debug(f"Extracted SubSclassID: {sub_league_id}")
            return sub_league_id

        # Fallback: Look for subleastanding URL pattern
        # /subleastanding/2025-2026/745/918
        match = re.search(r'/subleastanding/[\d-]+/\d+/(\d+)', html_content)
        if match:
            sub_league_id = int(match.group(1))
            if sub_league_id > 0:
                logger.debug(f"Extracted SubSclassID from URL: {sub_league_id}")
                return sub_league_id

        logger.warning("SubSclassID not found in page content")
        return None

    except Exception as e:
        logger.warning(f"Error extracting SubSclassID: {e}")
        return None


def extract_all_sub_leagues(html_content: str) -> List[Dict]:
    """
    Extract all sub-leagues from league page

    Some leagues have multiple sub-leagues (groups, stages, etc.)
    arrSubLeague = [[918, 'League', ...], [919, 'Group A', ...], ...]

    Args:
        html_content: Raw HTML content from /league/{league_id} page

    Returns:
        List of sub-league info dicts
    """
    sub_leagues = []

    if not html_content:
        return sub_leagues

    try:
        # First get the default SubSclassID
        default_id = extract_sub_league_id(html_content)

        # Look for arrSubLeague definition
        # arrSubLeague = [[918,'联赛','聯賽','League',1,46,22,0,1,21], ...]
        match = re.search(r'var\s+arrSubLeague\s*=\s*\[(.*?)\];', html_content, re.DOTALL)
        if match:
            arr_content = match.group(1)
            # Find all sub-league arrays
            sub_matches = re.findall(r'\[(\d+),([^\]]+)\]', arr_content)

            for sub_match in sub_matches:
                sub_id = int(sub_match[0])
                rest = sub_match[1].split(',')

                # Extract name (4th element, English name)
                name = 'League'
                for i, val in enumerate(rest):
                    val = val.strip().strip("'\"")
                    if val and len(val) > 1 and i >= 2:
                        name = val
                        break

                sub_leagues.append({
                    'id': sub_id,
                    'name': name,
                    'is_default': sub_id == default_id
                })

        # If no arrSubLeague but we have default_id, create single entry
        if not sub_leagues and default_id:
            sub_leagues.append({
                'id': default_id,
                'name': 'League',
                'is_default': True
            })

    except Exception as e:
        logger.warning(f"Error extracting sub leagues: {e}")

    return sub_leagues


class LeagueDataParser:
    """Parser for league standings and match data from JS files"""

    def __init__(self):
        self.teams_cache = {}
        self.cup_rounds_cache = {}  # Cache for cup round names

    def parse_league_data(self, js_content: str, is_cup: bool = False) -> Optional[Dict]:
        """
        Parse league data from JS content

        Args:
            js_content: Raw JavaScript content from matchResult endpoint
            is_cup: Whether this is cup data (uses arrCup instead of arrLeague)

        Returns:
            Parsed league data dictionary
        """
        if not js_content:
            logger.warning("Empty JS content received")
            return None

        try:
            # Parse teams FIRST and cache them before parsing standings/rounds
            teams = self._parse_teams(js_content)
            self.teams_cache = {t['id']: t for t in teams}
            logger.debug(f"Cached {len(self.teams_cache)} teams")

            # Detect if this is cup data (has arrCup instead of arrLeague)
            if 'arrCup' in js_content:
                is_cup = True
                logger.info("Detected cup data format (arrCup)")

            if is_cup:
                # Parse cup-specific data
                cup_rounds = self._parse_cup_rounds(js_content)
                self.cup_rounds_cache = cup_rounds

                result = {
                    'league': self._parse_cup_info(js_content),
                    'teams': teams,
                    'sub_league': {'id': None, 'name': 'Cup', 'total_rounds': len(cup_rounds), 'total_teams': len(teams)},
                    'standings': {'overall': [], 'home': [], 'away': []},  # Cups don't have standings
                    'rounds': self._parse_cup_matches(js_content),
                    'cup_rounds': cup_rounds,  # Round/stage definitions
                    'zones': {},
                    'is_cup': True,
                }
            else:
                result = {
                    'league': self._parse_league_info(js_content),
                    'teams': teams,
                    'sub_league': self._parse_sub_league(js_content),
                    'standings': {
                        'overall': self._parse_standings(js_content, 'totalScore'),
                        'home': self._parse_standings(js_content, 'homeScore'),
                        'away': self._parse_standings(js_content, 'guestScore'),
                    },
                    'rounds': self._parse_rounds(js_content),
                    'zones': self._parse_zones(js_content),
                    'is_cup': False,
                }

            logger.info(f"✅ Parsed {'cup' if is_cup else 'league'} data: {result['league'].get('name', 'Unknown')} - {len(teams)} teams")
            return result

        except Exception as e:
            logger.exception(f"Error parsing league data: {e}")
            return None

    def _parse_cup_info(self, js_content: str) -> Dict:
        """Parse arrCup variable for cup info"""
        try:
            # arrCup = [90,'','','England FA Cup','','','ENG FAC','2025-2026','image.png','#0000cc','description']
            match = re.search(r'var\s+arrCup\s*=\s*\[(.*?)\];', js_content, re.DOTALL)
            if match:
                arr_str = match.group(1)
                values = self._parse_js_array(arr_str)

                return {
                    'id': values[0] if len(values) > 0 else None,
                    'name': values[3] if len(values) > 3 else 'Unknown Cup',
                    'short_name': values[6] if len(values) > 6 else '',
                    'season': values[7] if len(values) > 7 else '',
                    'image': values[8] if len(values) > 8 else '',
                    'color': values[9] if len(values) > 9 else '#FFFFFF',
                    'type': 'cup',
                }
        except Exception as e:
            logger.warning(f"Error parsing cup info: {e}")

        return {'id': None, 'name': 'Unknown Cup', 'season': '', 'color': '#FFFFFF', 'type': 'cup'}

    def _parse_cup_rounds(self, js_content: str) -> Dict[int, Dict]:
        """Parse arrCupKind to get round/stage definitions"""
        cup_rounds = {}
        try:
            # arrCupKind = [[25188,0,'预赛','預賽','Qual',0,0,0], [25306,0,'资格赛1','資格賽1','Qualifi 1',0,0,0], ...]
            match = re.search(r'var\s+arrCupKind\s*=\s*\[(.*?)\];', js_content, re.DOTALL)
            if match:
                arr_str = match.group(1)
                # Find all round arrays
                round_arrays = re.findall(r'\[([^\[\]]+)\]', arr_str)

                for round_arr in round_arrays:
                    values = self._parse_js_array(round_arr)
                    if len(values) >= 5:
                        round_id = int(values[0]) if values[0] else 0
                        cup_rounds[round_id] = {
                            'id': round_id,
                            'name': values[4] if len(values) > 4 else f'Round {round_id}',  # English name at index 4
                            'name_cn': values[2] if len(values) > 2 else '',
                            'type': values[1] if len(values) > 1 else 0,
                        }

                logger.debug(f"Parsed {len(cup_rounds)} cup rounds/stages")

        except Exception as e:
            logger.warning(f"Error parsing cup rounds: {e}")

        return cup_rounds

    def _parse_cup_matches(self, js_content: str) -> Dict[int, List[Dict]]:
        """Parse cup matches from jh["G{round_id}"] format"""
        rounds = {}
        try:
            # Find all jh["G{id}"] = [...] entries
            # Pattern: jh["G25188"] = [[match1], [match2], ...]
            pattern = r'jh\["G(\d+)"\]\s*=\s*\[(.*?)\];'
            matches = re.findall(pattern, js_content, re.DOTALL)

            for round_id_str, matches_str in matches:
                round_id = int(round_id_str)
                match_list = []

                # Get round name from cache
                round_info = self.cup_rounds_cache.get(round_id, {})
                round_name = round_info.get('name', f'Round {round_id}')

                # Find all match arrays
                match_rows = re.findall(r'\[([^\[\]]+)\]', matches_str)

                for row in match_rows:
                    values = self._parse_js_array(row)
                    if len(values) >= 8:
                        # Cup match format: [match_id, cup_id, status, datetime, home_id, away_id, score, ht_score, ...]
                        home_id = int(values[4]) if values[4] else 0
                        away_id = int(values[5]) if values[5] else 0

                        home_info = self.teams_cache.get(home_id, {})
                        away_info = self.teams_cache.get(away_id, {})

                        # Parse status: -1 = finished, 0 = not started, 1+ = live minute
                        status_val = int(values[2]) if values[2] else 0
                        if status_val == -1:
                            status = 'finished'
                        elif status_val == 0:
                            status = 'not_started'
                        else:
                            status = 'live'

                        match_list.append({
                            'match_id': int(values[0]) if values[0] else 0,
                            'datetime': values[3] if len(values) > 3 else '',
                            'status': status,
                            'match_type': 'cup',
                            'round_name': round_name,
                            'home_team': {
                                'id': home_id,
                                'name': home_info.get('name', f'Team {home_id}'),
                                'logo': home_info.get('logo', ''),
                            },
                            'away_team': {
                                'id': away_id,
                                'name': away_info.get('name', f'Team {away_id}'),
                                'logo': away_info.get('logo', ''),
                            },
                            'score': {
                                'full_time': values[6] if len(values) > 6 else None,
                                'half_time': values[7] if len(values) > 7 else None,
                            }
                        })

                if match_list:
                    rounds[round_id] = match_list
                    logger.debug(f"Parsed {len(match_list)} matches for round {round_name} (G{round_id})")

            logger.info(f"📋 Parsed {len(rounds)} cup rounds with {sum(len(m) for m in rounds.values())} total matches")

        except Exception as e:
            logger.warning(f"Error parsing cup matches: {e}")

        return rounds

    def _parse_league_info(self, js_content: str) -> Dict:
        """Parse arrLeague variable"""
        try:
            # arrLeague = [35, '', '', 'England League 2', '2025-2026', '#FFBA75', ...]
            match = re.search(r'var\s+arrLeague\s*=\s*\[(.*?)\];', js_content, re.DOTALL)
            if match:
                # Parse array values
                arr_str = match.group(1)
                # Extract values carefully handling strings and numbers
                values = self._parse_js_array(arr_str)

                return {
                    'id': values[0] if len(values) > 0 else None,
                    'name': values[3] if len(values) > 3 else 'Unknown',
                    'season': values[4] if len(values) > 4 else '',
                    'color': values[5] if len(values) > 5 else '#FFFFFF',
                }
        except Exception as e:
            logger.warning(f"Error parsing league info: {e}")

        return {'id': None, 'name': 'Unknown', 'season': '', 'color': '#FFFFFF'}

    def _parse_teams(self, js_content: str) -> List[Dict]:
        """Parse arrTeam variable"""
        teams = []
        try:
            # arrTeam = [[48, '', '', 'Gillingham', '', 'images/48/...', 0], ...]
            match = re.search(r'var\s+arrTeam\s*=\s*\[(.*?)\];', js_content, re.DOTALL)
            if match:
                arr_str = match.group(1)

                # More robust parsing: find each team array by balanced brackets
                # Format: [id, '', '', 'Team Name', '', 'images/xxx.png', 0]
                team_arrays = re.findall(r'\[(\d+)([^\]]*)\]', arr_str)

                for team_match in team_arrays:
                    try:
                        team_id = int(team_match[0])
                        rest_str = team_match[1]

                        # Parse the rest of the array
                        # Split by comma but preserve quoted strings
                        parts = []
                        current = ''
                        in_quote = False
                        quote_char = None

                        for char in rest_str:
                            if char in '"\'':
                                if not in_quote:
                                    in_quote = True
                                    quote_char = char
                                elif char == quote_char:
                                    in_quote = False
                                    quote_char = None
                                current += char
                            elif char == ',' and not in_quote:
                                parts.append(current.strip())
                                current = ''
                            else:
                                current += char

                        if current.strip():
                            parts.append(current.strip())

                        # Clean up parts (remove empty first element if exists)
                        if parts and parts[0] == '':
                            parts = parts[1:]

                        # Team name is at index 2 (0-indexed after removing leading comma)
                        # Format after id: '', '', 'Team Name', '', 'images/...', 0
                        team_name = 'Unknown'
                        logo = ''

                        for i, val in enumerate(parts):
                            val = val.strip().strip("'\"")
                            if not val:
                                continue

                            # Team name is typically at index 2 (3rd element after ID)
                            if i == 2 and val and not val.startswith('images/'):
                                team_name = val
                            elif 'images/' in val:
                                logo = val

                        # Fallback: find first non-empty string that's not an image
                        if team_name == 'Unknown':
                            for val in parts:
                                val = val.strip().strip("'\"")
                                if val and len(val) > 1 and not val.startswith('images/') and not val.isdigit():
                                    team_name = val
                                    break

                        if team_id > 0:  # Skip invalid team IDs
                            teams.append({
                                'id': team_id,
                                'name': team_name,
                                'logo': logo
                            })
                            logger.debug(f"Parsed team: {team_id} -> {team_name}")

                    except Exception as e:
                        logger.warning(f"Error parsing team entry: {e}")
                        continue

                logger.info(f"📋 Parsed {len(teams)} teams from arrTeam")

        except Exception as e:
            logger.warning(f"Error parsing teams: {e}")

        return teams

    def _parse_sub_league(self, js_content: str) -> Dict:
        """Parse arrSubLeague variable"""
        try:
            # arrSubLeague = [[139, '联赛', '聯賽', 'League', 1, 46, 22, 0, 1, 21], ...]
            match = re.search(r'var\s+arrSubLeague\s*=\s*\[\[(.*?)\]', js_content)
            if match:
                values = self._parse_js_array(match.group(1))
                return {
                    'id': values[0] if len(values) > 0 else None,
                    'name': values[3] if len(values) > 3 else 'League',
                    'total_rounds': values[5] if len(values) > 5 else 0,
                    'total_teams': values[6] if len(values) > 6 else 0,
                }
        except Exception as e:
            logger.warning(f"Error parsing sub league: {e}")

        return {'id': None, 'name': 'League', 'total_rounds': 0, 'total_teams': 0}

    def _parse_standings(self, js_content: str, table_name: str) -> List[Dict]:
        """Parse standings table (totalScore, homeScore, guestScore)"""
        standings = []
        try:
            # Actual format from nowgoal:
            # [[zone, rank, team_id, ?, played, won, drawn, lost, gf, ga, gd, win%, draw%, loss%, ..., points, ...], ...]
            # Example: [0, 1, 19, 0, 17, 12, 3, 2, 31, 10, 21, '70.6', '17.6', '11.8', 1.82, 0.59, 39, ...]
            # Indices:  0  1   2  3   4   5  6  7   8   9  10    11     12       13    14    15   16
            pattern = rf'var\s+{table_name}\s*=\s*\[(.*?)\];'
            match = re.search(pattern, js_content, re.DOTALL)

            if match:
                arr_str = match.group(1)
                # Find all team rows
                rows = re.findall(r'\[([^\[\]]+)\]', arr_str)

                for row in rows:
                    values = self._parse_js_array(row)
                    if len(values) >= 11:
                        # Correct indices based on actual data format
                        zone = int(values[0]) if values[0] is not None else 0
                        rank = int(values[1]) if values[1] is not None else 0
                        team_id = int(values[2]) if values[2] is not None else 0
                        team_info = self.teams_cache.get(team_id, {})

                        # Parse stats with correct indices
                        played = int(values[4]) if len(values) > 4 and values[4] is not None else 0
                        won = int(values[5]) if len(values) > 5 and values[5] is not None else 0
                        drawn = int(values[6]) if len(values) > 6 and values[6] is not None else 0
                        lost = int(values[7]) if len(values) > 7 and values[7] is not None else 0
                        goals_for = int(values[8]) if len(values) > 8 and values[8] is not None else 0
                        goals_against = int(values[9]) if len(values) > 9 and values[9] is not None else 0
                        goal_difference = int(values[10]) if len(values) > 10 and values[10] is not None else 0

                        # Points at index 16
                        points = int(values[16]) if len(values) > 16 and values[16] is not None else 0

                        # Win percentage at index 11 (as string like '70.6')
                        win_pct = 0.0
                        if len(values) > 11 and values[11] is not None:
                            try:
                                win_pct = float(str(values[11]).strip("'\""))
                            except (ValueError, TypeError):
                                pass

                        standings.append({
                            'rank': rank,
                            'team_id': team_id,
                            'team_name': team_info.get('name', f'Team {team_id}'),
                            'team_logo': team_info.get('logo', ''),
                            'played': played,
                            'won': won,
                            'drawn': drawn,
                            'lost': lost,
                            'goals_for': goals_for,
                            'goals_against': goals_against,
                            'goal_difference': goal_difference,
                            'points': points,
                            'win_percentage': win_pct,
                            'zone': zone,  # -1=relegation, 0=mid-table, 1=promotion
                        })

        except Exception as e:
            logger.warning(f"Error parsing {table_name}: {e}")

        return standings

    def _parse_rounds(self, js_content: str) -> Dict[int, List[Dict]]:
        """Parse match data by round/stage

        Supports multiple key formats:
        - jh["R_N"] - Regular rounds (most common)
        - jh["G_N"] - Group stage matches (cups)
        - jh["K_N"] - Knockout stage matches (cups)
        - jh["S_N"] - Stage matches (alternative format)
        """
        rounds = {}
        try:
            # Try multiple key patterns for different competition formats
            # Pattern 1: Regular rounds (R_1, R_2, ...)
            # Pattern 2: Group matches (G_1, G_2, ...)
            # Pattern 3: Knockout matches (K_1, K_2, ...)
            # Pattern 4: Stage matches (S_1, S_2, ...)
            key_patterns = [
                (r'jh\["R_(\d+)"\]\s*=\s*\[(.*?)\];', 'round'),
                (r'jh\["G_(\d+)"\]\s*=\s*\[(.*?)\];', 'group'),
                (r'jh\["K_(\d+)"\]\s*=\s*\[(.*?)\];', 'knockout'),
                (r'jh\["S_(\d+)"\]\s*=\s*\[(.*?)\];', 'stage'),
            ]

            all_matches_found = False
            for pattern, match_type in key_patterns:
                round_matches = re.findall(pattern, js_content, re.DOTALL)
                if round_matches:
                    all_matches_found = True
                    logger.debug(f"Found {len(round_matches)} {match_type} entries")

                for round_num, matches_str in round_matches:
                    round_num = int(round_num)
                    matches = []

                    # Find all match arrays
                    match_rows = re.findall(r'\[([^\[\]]+)\]', matches_str)

                    for row in match_rows:
                        values = self._parse_js_array(row)
                        if len(values) >= 8:
                            home_id = int(values[4]) if values[4] else 0
                            away_id = int(values[5]) if values[5] else 0

                            home_info = self.teams_cache.get(home_id, {})
                            away_info = self.teams_cache.get(away_id, {})

                            # Parse status: -1 = finished, 0 = not started, 1+ = live minute
                            status_val = int(values[2]) if values[2] else 0
                            if status_val == -1:
                                status = 'finished'
                            elif status_val == 0:
                                status = 'not_started'
                            else:
                                status = 'live'

                            matches.append({
                                'match_id': int(values[0]) if values[0] else 0,
                                'datetime': values[3] if len(values) > 3 else '',
                                'status': status,
                                'match_type': match_type,  # round, group, knockout, stage
                                'home_team': {
                                    'id': home_id,
                                    'name': home_info.get('name', f'Team {home_id}'),
                                    'logo': home_info.get('logo', ''),
                                    'rank': values[8] if len(values) > 8 else None,
                                },
                                'away_team': {
                                    'id': away_id,
                                    'name': away_info.get('name', f'Team {away_id}'),
                                    'logo': away_info.get('logo', ''),
                                    'rank': values[9] if len(values) > 9 else None,
                                },
                                'score': {
                                    'full_time': values[6] if len(values) > 6 else None,
                                    'half_time': values[7] if len(values) > 7 else None,
                                }
                            })

                    if matches:
                        # Use round number as key, append if already exists (different match types)
                        if round_num in rounds:
                            rounds[round_num].extend(matches)
                        else:
                            rounds[round_num] = matches

            if not all_matches_found:
                logger.warning("No match data found with any known key pattern (R_N, G_N, K_N, S_N)")

        except Exception as e:
            logger.warning(f"Error parsing rounds: {e}")

        return rounds

    def _parse_zones(self, js_content: str) -> Dict:
        """Parse promotion/relegation zone colors"""
        zones = {
            'promotion': [],
            'playoff': [],
            'relegation': [],
        }

        try:
            # Look for color definitions like '#CCCCFF|升级球队' (promotion)
            if '#CCCCFF' in js_content or '升级球队' in js_content:
                zones['promotion'] = [1, 2, 3]  # Default top 3
            if '#00CCCC' in js_content or '升级附加' in js_content:
                zones['playoff'] = [4, 5, 6, 7]  # Default playoff spots
            if '#B1A7A7' in js_content or '降级球队' in js_content:
                zones['relegation'] = [22, 23, 24]  # Default bottom 3

        except Exception as e:
            logger.warning(f"Error parsing zones: {e}")

        return zones

    def _parse_js_array(self, arr_str: str) -> List:
        """Parse JavaScript array string to Python list"""
        values = []
        try:
            # Split by comma, handling quoted strings
            parts = re.split(r',(?=(?:[^"\']*["\'][^"\']*["\'])*[^"\']*$)', arr_str)

            for part in parts:
                part = part.strip().strip("'\"")

                # Try to convert to int/float if possible
                if part == '' or part.lower() == 'null':
                    values.append(None)
                else:
                    try:
                        if '.' in part:
                            values.append(float(part))
                        else:
                            values.append(int(part))
                    except ValueError:
                        values.append(part)

        except Exception as e:
            logger.warning(f"Error parsing JS array: {e}")

        return values


class LeagueOddsParser:
    """Parser for league odds data from AJAX endpoint"""

    def parse_odds_data(self, js_content: str, matches_info: Optional[Dict] = None) -> Optional[Dict]:
        """
        Parse league odds data

        Args:
            js_content: Raw JavaScript content from LeagueOddsAjax endpoint
            matches_info: Optional match info to enrich odds data

        Returns:
            Parsed odds data dictionary
        """
        if not js_content:
            logger.warning("Empty odds content received")
            return None

        try:
            result = {
                'odds': [],
                'match_count': 0
            }

            # Parse odds data: O_matchId, L_matchId, T_matchId
            # O = 1X2 (Match Result)
            # L = Asian Handicap (Line)
            # T = Over/Under (Total)

            odds_data = {}

            # Find all odds entries
            patterns = {
                '1x2': r"O_(\d+):\s*\[(.*?)\]",
                'asian_handicap': r"L_(\d+):\s*\[(.*?)\]",
                'over_under': r"T_(\d+):\s*\[(.*?)\]"
            }

            for odds_type, pattern in patterns.items():
                matches = re.findall(pattern, js_content, re.DOTALL)
                for match_id, odds_str in matches:
                    match_id = int(match_id)

                    if match_id not in odds_data:
                        odds_data[match_id] = {
                            'match_id': match_id,
                            'odds': {},
                            'odds_history': []
                        }

                    # Parse odds arrays
                    odds_values = self._parse_odds_array(odds_str)
                    if odds_values:
                        odds_data[match_id]['odds'][odds_type] = odds_values[-1] if odds_values else None
                        odds_data[match_id]['odds_history'] = odds_values

            result['odds'] = list(odds_data.values())
            result['match_count'] = len(odds_data)

            logger.info(f"✅ Parsed odds for {result['match_count']} matches")
            return result

        except Exception as e:
            logger.exception(f"Error parsing odds data: {e}")
            return None

    def _parse_odds_array(self, arr_str: str) -> List[Dict]:
        """Parse odds array to list of odds snapshots"""
        odds_list = []
        try:
            # [[16, 3.9, 3.5, 1.9], [18, 3.1, 3.5, 2.15], ...]
            snapshots = re.findall(r'\[([^\[\]]+)\]', arr_str)

            for snapshot in snapshots:
                values = [v.strip() for v in snapshot.split(',')]
                if len(values) >= 4:
                    try:
                        odds_list.append({
                            'bookmaker_id': int(values[0]) if values[0] else 0,
                            'home': float(values[1]) if values[1] else 0,
                            'line': float(values[2]) if values[2] else 0,
                            'away': float(values[3]) if values[3] else 0,
                        })
                    except ValueError:
                        continue

        except Exception as e:
            logger.warning(f"Error parsing odds array: {e}")

        return odds_list


# Singleton instances
league_data_parser = LeagueDataParser()
league_odds_parser = LeagueOddsParser()
