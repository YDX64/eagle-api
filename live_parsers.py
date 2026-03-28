"""
Live Match Data Parsers

Parses real-time data from NowGoal live endpoints:
- bf_en-idn.js: Live match list with scores
- detail.js: Technical stats (shots, corners, possession, etc.)
- runOddsData_8.txt: Live odds from Bet365
- sbCorner.js: Corner statistics
- change_en.xml: Real-time score updates
"""
import re
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)

# ============================================================================
# PRE-COMPILED REGEX PATTERNS (Performance optimization)
# Compiling once at module load instead of every function call
# ============================================================================

# Live match metadata patterns
RE_LAST_CREATE_TIME = re.compile(r'lastCreateTime_bfIndex="([^"]+)"')
RE_MATCH_COUNT = re.compile(r'var matchcount=(\d+)')

# JavaScript array patterns for live data
RE_LIVE_MATCH_ARRAY = re.compile(r"A\[(\d+)\]=\[([^\]]+)\]")
RE_LIVE_LEAGUE_ARRAY = re.compile(r"B\[(\d+)\]=\[([^\]]+)\]")
RE_LIVE_COUNTRY_ARRAY = re.compile(r"C\[(\d+)\]=\[([^\]]+)\]")

# Technical stats pattern (tc[] entries)
RE_TECH_STATS = re.compile(r'tc\[(\d+)\]="([^"]+)"')

# Events pattern (rq[] entries)
RE_EVENTS = re.compile(r'rq\[(\d+)\]="([^"]+)"')

# Corner data pattern
RE_CORNER_DATA = re.compile(r'sCornerData\[(\d+)\]="([^"]*)"')

# HTML tag removal pattern
RE_HTML_TAGS = re.compile(r'<[^>]+>')


# ============================================================================
# MATCH STATUS MAPPING
# ============================================================================
MATCH_STATUS_MAP = {
    0: 'not_started',
    1: 'first_half',
    2: 'half_time',
    3: 'second_half',
    4: 'extra_time',
    5: 'penalty',
    -1: 'finished',
    -10: 'cancelled',
    -11: 'postponed',
    -12: 'interrupted',
    -13: 'suspended',
    -14: 'abandoned',
}


# ============================================================================
# TECHNICAL STATS FIELD MAPPING (Based on NowGoal detail.js tc[] format)
# ============================================================================
# NowGoal tc[] stat ID mappings - VERIFIED against real data
# Note: Red/Yellow cards come from match data (parts[13]/[14]), NOT from tc[] stats
TECH_STATS_MAP = {
    3: 'shots',               # Total shots
    4: 'shots_on_target',     # Shots on goal
    5: 'fouls',               # Fouls committed
    6: 'corners',             # Corner kicks
    8: 'free_kicks',          # Free kicks
    9: 'offsides',            # Offsides
    14: 'possession',         # Ball possession %
    15: 'aerials',            # Aerial duels
    16: 'saves',              # Goalkeeper saves
    19: 'successful_tackles', # Successful tackles
    20: 'interceptions',      # Interceptions
    21: 'long_passes',        # Long passes
    24: 'crosses',            # Crosses
    34: 'shots_off_target',   # Shots off goal
    37: 'blocked',            # Blocked shots
    38: 'tackles',            # Total tackles
    39: 'dribbles',           # Successful dribbles
    40: 'throw_ins',          # Throw-ins
    41: 'total_passes',       # Total passes
    42: 'pass_success',       # Pass success rate %
    43: 'attacks',            # Total attacks
    44: 'dangerous_attacks',  # Dangerous attacks
    45: 'corners_ht',         # Corners at half-time
    46: 'possession_ht',      # Possession at half-time %
}


class LiveMatchParser:
    """Parser for live match data from bf_en-idn.js"""

    def parse(self, js_content: str) -> Dict[str, Any]:
        """
        Parse bf_en-idn.js content

        Returns:
            {
                'matches': [...],
                'leagues': {...},
                'countries': {...},
                'last_update': '2025-12-24 15:30:00',
                'total_matches': 76,
                'live_count': 12
            }
        """
        try:
            result = {
                'matches': [],
                'leagues': {},
                'countries': {},
                'last_update': None,
                'total_matches': 0,
                'live_count': 0
            }

            # Extract lastCreateTime (pre-compiled pattern)
            time_match = RE_LAST_CREATE_TIME.search(js_content)
            if time_match:
                result['last_update'] = time_match.group(1)

            # Extract matchcount (pre-compiled pattern)
            count_match = RE_MATCH_COUNT.search(js_content)
            if count_match:
                result['total_matches'] = int(count_match.group(1))

            # Parse A array (matches)
            result['matches'] = self._parse_matches(js_content)

            # Parse B array (leagues)
            result['leagues'] = self._parse_leagues(js_content)

            # Parse C array (countries)
            result['countries'] = self._parse_countries(js_content)

            # Count live matches
            result['live_count'] = len([m for m in result['matches'] if m.get('is_live')])

            logger.info(f"Parsed {len(result['matches'])} matches, {result['live_count']} live")
            return result

        except Exception as e:
            logger.error(f"Error parsing live matches: {e}")
            return {'matches': [], 'error': str(e)}

    def _parse_matches(self, js_content: str) -> List[Dict]:
        """Parse A[n]=[...] match arrays"""
        matches = []

        # Pattern: A[1]=[2882312,6,18907,3734,'Team1','Team2',...]
        # Using pre-compiled pattern
        for match in RE_LIVE_MATCH_ARRAY.finditer(js_content):
            try:
                index = int(match.group(1))
                data_str = match.group(2)

                match_data = self._parse_single_match(data_str)
                if match_data:
                    match_data['index'] = index
                    matches.append(match_data)

            except Exception as e:
                logger.debug(f"Error parsing match at index {index}: {e}")
                continue

        return matches

    def _parse_single_match(self, data_str: str) -> Optional[Dict]:
        """Parse single match data string"""
        try:
            # Split by comma, handling quoted strings
            parts = self._smart_split(data_str)

            if len(parts) < 12:
                return None

            # Extract match status
            state = self._safe_int(parts[8]) if len(parts) > 8 else 0
            status = MATCH_STATUS_MAP.get(state, 'unknown')
            is_live = state in [1, 2, 3, 4, 5]

            # Extract scores
            home_score = self._safe_int(parts[9]) if len(parts) > 9 else None
            away_score = self._safe_int(parts[10]) if len(parts) > 10 else None

            # Extract half-time scores
            ht_home = self._safe_int(parts[11]) if len(parts) > 11 else None
            ht_away = self._safe_int(parts[12]) if len(parts) > 12 else None

            # Determine half from status
            half = 1 if state == 1 else (2 if state == 3 else None)

            # Calculate minute from start_time (parts[7]) dynamically
            # start_time represents when current half started
            minute = None
            start_time_str = parts[7] if len(parts) > 7 else None
            if start_time_str and is_live:
                try:
                    start_dt = datetime.strptime(start_time_str, '%Y-%m-%d %H:%M:%S')
                    now = datetime.utcnow()
                    elapsed = int((now - start_dt).total_seconds() / 60)

                    if state == 1:  # First half
                        minute = min(elapsed, 45)  # Cap at 45 for first half
                    elif state == 2:  # Half time
                        minute = 45
                    elif state == 3:  # Second half
                        minute = 45 + min(elapsed, 45)  # 45 + elapsed, cap at 90
                    elif state == 4:  # Extra time
                        minute = 90 + elapsed
                    elif state == 5:  # Penalty shootout
                        minute = 120
                except Exception as e:
                    logger.debug(f"Error calculating minute: {e}")
                    minute = None

            # Clean team names (remove HTML tags)
            home_team = self._clean_team_name(parts[4]) if len(parts) > 4 else ''
            away_team = self._clean_team_name(parts[5]) if len(parts) > 5 else ''

            return {
                'match_id': self._safe_int(parts[0]),
                'league_id': self._safe_int(parts[1]),
                'home_team_id': self._safe_int(parts[2]),
                'away_team_id': self._safe_int(parts[3]),
                'home_team': home_team,
                'away_team': away_team,
                'match_time': parts[6] if len(parts) > 6 else None,
                'start_time': parts[7] if len(parts) > 7 else None,
                'state': state,
                'status': status,
                'is_live': is_live,
                'home_score': home_score,
                'away_score': away_score,
                'ht_home_score': ht_home,
                'ht_away_score': ht_away,
                'minute': minute,
                'half': half,
                'home_red_cards': self._safe_int(parts[13]) if len(parts) > 13 else 0,
                'away_red_cards': self._safe_int(parts[14]) if len(parts) > 14 else 0,
            }

        except Exception as e:
            logger.debug(f"Error parsing match: {e}")
            return None

    def _parse_leagues(self, js_content: str) -> Dict:
        """Parse B[n]=[...] league arrays"""
        leagues = {}

        # Using pre-compiled pattern
        for match in RE_LIVE_LEAGUE_ARRAY.finditer(js_content):
            try:
                index = int(match.group(1))
                parts = self._smart_split(match.group(2))

                if len(parts) >= 4:
                    leagues[index] = {
                        'league_id': self._safe_int(parts[0]),
                        'short_name': self._clean_string(parts[1]),
                        'name': self._clean_string(parts[2]),
                        'country_id': self._safe_int(parts[3]) if len(parts) > 3 else None,
                    }
            except:
                continue

        return leagues

    def _parse_countries(self, js_content: str) -> Dict:
        """Parse C[n]=[...] country arrays"""
        countries = {}

        # Using pre-compiled pattern
        for match in RE_LIVE_COUNTRY_ARRAY.finditer(js_content):
            try:
                index = int(match.group(1))
                parts = self._smart_split(match.group(2))

                if len(parts) >= 2:
                    countries[index] = {
                        'country_id': self._safe_int(parts[0]),
                        'name': self._clean_string(parts[1]),
                    }
            except:
                continue

        return countries

    def _smart_split(self, data_str: str) -> List[str]:
        """Split string by comma, handling quoted strings"""
        parts = []
        current = ""
        in_quotes = False
        quote_char = None

        for char in data_str:
            if char in ["'", '"'] and not in_quotes:
                in_quotes = True
                quote_char = char
            elif char == quote_char and in_quotes:
                in_quotes = False
                quote_char = None
            elif char == ',' and not in_quotes:
                parts.append(current.strip().strip("'\""))
                current = ""
                continue
            else:
                current += char

        if current:
            parts.append(current.strip().strip("'\""))

        return parts

    def _safe_int(self, value) -> Optional[int]:
        """Safely convert to int"""
        try:
            if value is None or value == '':
                return None
            return int(str(value).strip())
        except:
            return None

    def _clean_string(self, value: str) -> str:
        """Clean string value"""
        if not value:
            return ''
        return str(value).strip().strip("'\"")

    def _clean_team_name(self, name: str) -> str:
        """Remove HTML tags from team name"""
        if not name:
            return ''
        # Remove HTML tags like <font color=#880000>(N)</font>
        # Using pre-compiled pattern
        clean = RE_HTML_TAGS.sub('', str(name))
        return clean.strip()

    def _calculate_minute(self, start_time_str: str, state: int) -> Optional[int]:
        """
        Calculate match minute from start time.

        Args:
            start_time_str: Match start time (e.g., '2025-12-24 17:30:00')
            state: Match state (1=first_half, 2=half_time, 3=second_half)

        Returns:
            Current match minute (1-90+)
        """
        if not start_time_str or state not in [1, 2, 3]:
            return None

        try:
            from datetime import datetime

            # Parse start time
            start_time = datetime.strptime(start_time_str, '%Y-%m-%d %H:%M:%S')
            now = datetime.now()

            # Calculate elapsed time in minutes
            elapsed = (now - start_time).total_seconds() / 60

            if elapsed < 0:
                return None

            # Adjust for match state
            if state == 1:  # First half
                # First half is 0-45 minutes
                minute = min(int(elapsed), 45)
            elif state == 2:  # Half time
                minute = 45
            elif state == 3:  # Second half
                # Second half starts after ~15 min break
                # Subtract break time and add 45
                if elapsed > 60:  # More than 60 min since start = likely in 2nd half
                    minute = 45 + int(elapsed - 60)  # Assume 15 min break
                else:
                    minute = 45 + max(0, int(elapsed - 45))
                minute = min(minute, 90)  # Cap at 90 for normal time
            else:
                minute = int(elapsed)

            return max(1, minute)

        except Exception as e:
            logger.debug(f"Error calculating minute: {e}")
            return None


class LiveStatsParser:
    """Parser for live technical statistics from detail.js"""

    def parse(self, js_content: str) -> Dict[int, Dict]:
        """
        Parse detail.js content for tc[] array (technical stats)

        Returns:
            {
                match_id: {
                    'shots': {'home': 10, 'away': 8},
                    'corners': {'home': 5, 'away': 3},
                    ...
                }
            }
        """
        stats_by_match = {}

        try:
            # Find all tc[] entries
            # Format: tc[0]="2788696^6,11,1;45,6,0;11,0,3;..."
            # Using pre-compiled pattern
            for match in RE_TECH_STATS.finditer(js_content):
                try:
                    index = int(match.group(1))
                    data = match.group(2)

                    # Split by ^ to get match_id and stats
                    parts = data.split('^')
                    if len(parts) < 2:
                        continue

                    match_id = int(parts[0])
                    stats_str = parts[1] if len(parts) > 1 else ''

                    # Parse stats
                    stats = self._parse_stats(stats_str)
                    if stats:
                        stats_by_match[match_id] = stats

                except Exception as e:
                    logger.debug(f"Error parsing tc[{index}]: {e}")
                    continue

            logger.info(f"Parsed stats for {len(stats_by_match)} matches")
            return stats_by_match

        except Exception as e:
            logger.error(f"Error parsing live stats: {e}")
            return {}

    def _parse_stats(self, stats_str: str) -> Dict:
        """Parse stats string like '6,11,1;45,6,0;11,0,3'"""
        result = {}

        try:
            # Split by semicolon for each stat entry
            entries = stats_str.split(';')

            for entry in entries:
                if not entry:
                    continue

                parts = entry.split(',')
                if len(parts) < 3:
                    continue

                stat_id = int(parts[0])
                home_val = self._safe_float(parts[1])
                away_val = self._safe_float(parts[2])

                # Map stat_id to name
                stat_name = TECH_STATS_MAP.get(stat_id)
                if stat_name:
                    result[stat_name] = {
                        'home': home_val,
                        'away': away_val
                    }

            return result

        except Exception as e:
            logger.debug(f"Error parsing stats string: {e}")
            return {}

    def _safe_float(self, value) -> float:
        """Safely convert to float, handles percentage values like '67%'"""
        try:
            if value is None or value == '':
                return 0
            value_str = str(value).strip().rstrip('%')
            return float(value_str)
        except:
            return 0


class LiveEventsParser:
    """Parser for live match events from detail.js"""

    EVENT_TYPES = {
        1: 'goal',
        2: 'own_goal',
        3: 'penalty_goal',
        4: 'penalty_missed',
        5: 'yellow_card',
        6: 'red_card',
        7: 'second_yellow',
        8: 'substitution_in',
        9: 'substitution_out',
        10: 'var_goal',
        11: 'var_no_goal',
    }

    def parse(self, js_content: str) -> Dict[int, List[Dict]]:
        """
        Parse detail.js content for rq[] array (events)

        Returns:
            {
                match_id: [
                    {'type': 'goal', 'minute': 45, 'player': 'Player Name', ...},
                    ...
                ]
            }
        """
        events_by_match = {}

        try:
            # Find all rq[] entries
            # Format: rq[0]="2788696^1^1^2^Mahrez R.^101117^14057577^176934^0"
            # Using pre-compiled pattern
            for match in RE_EVENTS.finditer(js_content):
                try:
                    data = match.group(2)
                    parts = data.split('^')

                    if len(parts) < 5:
                        continue

                    match_id = int(parts[0])
                    event = self._parse_event(parts)

                    if event:
                        if match_id not in events_by_match:
                            events_by_match[match_id] = []
                        events_by_match[match_id].append(event)

                except Exception as e:
                    logger.debug(f"Error parsing event: {e}")
                    continue

            logger.info(f"Parsed events for {len(events_by_match)} matches")
            return events_by_match

        except Exception as e:
            logger.error(f"Error parsing live events: {e}")
            return {}

    def _parse_event(self, parts: List[str]) -> Optional[Dict]:
        """Parse single event from parts"""
        try:
            if len(parts) < 5:
                return None

            is_home = parts[1] == '1'
            event_type_id = int(parts[2]) if parts[2] else 0
            minute = int(parts[3]) if parts[3] else 0
            player_name = parts[4] if len(parts) > 4 else ''

            return {
                'is_home': is_home,
                'type_id': event_type_id,
                'type': self.EVENT_TYPES.get(event_type_id, 'unknown'),
                'minute': minute,
                'player': player_name,
            }

        except:
            return None


class LiveOddsParser:
    """Parser for live odds from runOddsData_8.txt"""

    def parse(self, content: str) -> Dict[int, Dict]:
        """
        Parse runOddsData_8.txt content

        Format: match_id!group1!group2!group3!group4!group5!group6$next_match...

        Returns:
            {
                match_id: {
                    'asian_handicap': {'home': 1.05, 'line': -0.5, 'away': 0.75},
                    'match_result': {'home': 1.80, 'draw': 3.50, 'away': 4.20},
                    'over_under': {'over': 1.90, 'line': 2.5, 'under': 1.90},
                    ...
                }
            }
        """
        odds_by_match = {}

        try:
            # Split by $ for each match
            matches = content.strip().split('$')

            for match_data in matches:
                if not match_data:
                    continue

                try:
                    match_odds = self._parse_match_odds(match_data)
                    if match_odds:
                        match_id = match_odds.pop('match_id')
                        odds_by_match[match_id] = match_odds
                except Exception as e:
                    logger.debug(f"Error parsing match odds: {e}")
                    continue

            logger.info(f"Parsed odds for {len(odds_by_match)} matches")
            return odds_by_match

        except Exception as e:
            logger.error(f"Error parsing live odds: {e}")
            return {}

    def _parse_match_odds(self, match_data: str) -> Optional[Dict]:
        """Parse single match odds data"""
        try:
            # Split by ! for groups
            groups = match_data.split('!')

            if len(groups) < 2:
                return None

            match_id = int(groups[0])

            result = {'match_id': match_id}

            # Group 1: Asian Handicap (home, line, away, opening_home, opening_line, opening_away, ...)
            if len(groups) > 1 and groups[1]:
                result['asian_handicap'] = self._parse_asian_handicap(groups[1])

            # Group 2: Match Result 1X2 (home, draw, away, opening_home, opening_draw, opening_away, ...)
            if len(groups) > 2 and groups[2]:
                result['match_result'] = self._parse_1x2(groups[2])

            # Group 3: Over/Under (over, line, under, opening_over, opening_line, opening_under, ...)
            if len(groups) > 3 and groups[3]:
                result['over_under'] = self._parse_over_under(groups[3])

            # Group 4: Both Teams to Score
            if len(groups) > 4 and groups[4]:
                result['btts'] = self._parse_btts(groups[4])

            # Group 5: Double Chance
            if len(groups) > 5 and groups[5]:
                result['double_chance'] = self._parse_double_chance(groups[5])

            # Group 6: Half-time Result
            if len(groups) > 6 and groups[6]:
                result['half_time'] = self._parse_1x2(groups[6])

            return result

        except Exception as e:
            logger.debug(f"Error parsing match odds: {e}")
            return None

    def _parse_asian_handicap(self, data: str) -> Dict:
        """Parse Asian Handicap odds"""
        try:
            parts = data.split(',')
            if len(parts) >= 3:
                return {
                    'home': self._safe_float(parts[0]),
                    'line': self._safe_float(parts[1]),
                    'away': self._safe_float(parts[2]),
                    'opening_home': self._safe_float(parts[3]) if len(parts) > 3 else None,
                    'opening_line': self._safe_float(parts[4]) if len(parts) > 4 else None,
                    'opening_away': self._safe_float(parts[5]) if len(parts) > 5 else None,
                }
        except:
            pass
        return {}

    def _parse_1x2(self, data: str) -> Dict:
        """Parse 1X2 odds"""
        try:
            parts = data.split(',')
            if len(parts) >= 3:
                return {
                    'home': self._safe_float(parts[0]),
                    'draw': self._safe_float(parts[1]),
                    'away': self._safe_float(parts[2]),
                    'opening_home': self._safe_float(parts[3]) if len(parts) > 3 else None,
                    'opening_draw': self._safe_float(parts[4]) if len(parts) > 4 else None,
                    'opening_away': self._safe_float(parts[5]) if len(parts) > 5 else None,
                }
        except:
            pass
        return {}

    def _parse_over_under(self, data: str) -> Dict:
        """Parse Over/Under odds"""
        try:
            parts = data.split(',')
            if len(parts) >= 3:
                return {
                    'over': self._safe_float(parts[0]),
                    'line': self._safe_float(parts[1]),
                    'under': self._safe_float(parts[2]),
                    'opening_over': self._safe_float(parts[3]) if len(parts) > 3 else None,
                    'opening_line': self._safe_float(parts[4]) if len(parts) > 4 else None,
                    'opening_under': self._safe_float(parts[5]) if len(parts) > 5 else None,
                }
        except:
            pass
        return {}

    def _parse_btts(self, data: str) -> Dict:
        """Parse Both Teams to Score odds"""
        try:
            parts = data.split(',')
            if len(parts) >= 2:
                return {
                    'yes': self._safe_float(parts[0]),
                    'no': self._safe_float(parts[1]),
                }
        except:
            pass
        return {}

    def _parse_double_chance(self, data: str) -> Dict:
        """Parse Double Chance odds"""
        try:
            parts = data.split(',')
            if len(parts) >= 3:
                return {
                    'home_draw': self._safe_float(parts[0]),
                    'home_away': self._safe_float(parts[1]),
                    'draw_away': self._safe_float(parts[2]),
                }
        except:
            pass
        return {}

    def _safe_float(self, value) -> Optional[float]:
        """Safely convert to float"""
        try:
            if value is None or value == '':
                return None
            return float(str(value).strip())
        except:
            return None


class CornerStatsParser:
    """Parser for corner statistics from sbCorner.js"""

    def parse(self, js_content: str) -> Dict[int, Dict]:
        """
        Parse sbCorner.js content

        Format: sCornerData[match_id]="data^odds^stats^events"

        Returns:
            {
                match_id: {
                    'total': {'home': 5, 'away': 3},
                    'first_half': {'home': 2, 'away': 1},
                    'odds': {...}
                }
            }
        """
        corners_by_match = {}

        try:
            # Pattern: sCornerData[2860703]="..."
            # Using pre-compiled pattern
            for match in RE_CORNER_DATA.finditer(js_content):
                try:
                    match_id = int(match.group(1))
                    data = match.group(2)

                    corner_data = self._parse_corner_data(data)
                    if corner_data:
                        corners_by_match[match_id] = corner_data

                except Exception as e:
                    logger.debug(f"Error parsing corner data: {e}")
                    continue

            logger.info(f"Parsed corners for {len(corners_by_match)} matches")
            return corners_by_match

        except Exception as e:
            logger.error(f"Error parsing corner stats: {e}")
            return {}

    def _parse_corner_data(self, data: str) -> Optional[Dict]:
        """Parse corner data string"""
        try:
            if not data:
                return None

            # Split by ^ for sections
            sections = data.split('^')

            result = {}

            # Section 2: Corner odds (index 1)
            if len(sections) > 1 and sections[1]:
                odds_parts = sections[1].split(',')
                if len(odds_parts) >= 6:
                    result['odds'] = {
                        'over': self._safe_float(odds_parts[0]),
                        'line': self._safe_float(odds_parts[1]),
                        'under': self._safe_float(odds_parts[2]),
                        'home': self._safe_float(odds_parts[3]),
                        'handicap': self._safe_float(odds_parts[4]),
                        'away': self._safe_float(odds_parts[5]),
                    }

            # Section 3: Corner stats (index 2)
            if len(sections) > 2 and sections[2]:
                stats_parts = sections[2].split(',')
                if len(stats_parts) >= 4:
                    result['stats'] = {
                        'home_first_half': int(stats_parts[0]) if stats_parts[0] else 0,
                        'away_first_half': int(stats_parts[1]) if stats_parts[1] else 0,
                        'home_total': int(stats_parts[2]) if stats_parts[2] else 0,
                        'away_total': int(stats_parts[3]) if stats_parts[3] else 0,
                    }
                    result['total'] = {
                        'home': result['stats']['home_total'],
                        'away': result['stats']['away_total']
                    }
                    result['first_half'] = {
                        'home': result['stats']['home_first_half'],
                        'away': result['stats']['away_first_half']
                    }

            return result if result else None

        except Exception as e:
            logger.debug(f"Error parsing corner data: {e}")
            return None

    def _safe_float(self, value) -> Optional[float]:
        """Safely convert to float"""
        try:
            if value is None or value == '':
                return None
            return float(str(value).strip())
        except:
            return None


# ============================================================================
# COMBINED LIVE DATA PARSER
# ============================================================================
class LiveDataParser:
    """Combined parser for all live data endpoints"""

    def __init__(self):
        self.match_parser = LiveMatchParser()
        self.stats_parser = LiveStatsParser()
        self.events_parser = LiveEventsParser()
        self.odds_parser = LiveOddsParser()
        self.corner_parser = CornerStatsParser()

    def parse_all(
        self,
        matches_js: str = None,
        stats_js: str = None,
        odds_txt: str = None,
        corners_js: str = None
    ) -> Dict[str, Any]:
        """
        Parse all live data sources and combine into unified response

        Returns:
            {
                'matches': [...],
                'stats': {match_id: {...}},
                'odds': {match_id: {...}},
                'corners': {match_id: {...}},
                'events': {match_id: [...]},
                'meta': {...}
            }
        """
        result = {
            'matches': [],
            'stats': {},
            'odds': {},
            'corners': {},
            'events': {},
            'meta': {
                'parsed_at': datetime.now().isoformat(),
            }
        }

        # Parse matches
        if matches_js:
            matches_data = self.match_parser.parse(matches_js)
            result['matches'] = matches_data.get('matches', [])
            result['leagues'] = matches_data.get('leagues', {})
            result['countries'] = matches_data.get('countries', {})
            result['meta']['last_update'] = matches_data.get('last_update')
            result['meta']['total_matches'] = matches_data.get('total_matches', 0)
            result['meta']['live_count'] = matches_data.get('live_count', 0)

        # Parse stats
        if stats_js:
            parsed = self.stats_parser.parse(stats_js)
            result['stats'] = parsed

            # Also parse events from same file
            result['events'] = self.events_parser.parse(stats_js)

        # Parse odds
        if odds_txt:
            result['odds'] = self.odds_parser.parse(odds_txt)

        # Parse corners
        if corners_js:
            result['corners'] = self.corner_parser.parse(corners_js)

        return result

    def enrich_matches_with_stats(self, matches: List[Dict], stats: Dict, odds: Dict, corners: Dict) -> List[Dict]:
        """
        Enrich match list with stats, odds, and corners

        Args:
            matches: List of parsed matches
            stats: Stats by match_id
            odds: Odds by match_id
            corners: Corners by match_id

        Returns:
            Enriched match list
        """
        enriched = []

        for match in matches:
            match_id = match.get('match_id')
            if not match_id:
                continue

            enriched_match = match.copy()

            # Add stats
            if match_id in stats:
                enriched_match['stats'] = stats[match_id]

            # Add odds
            if match_id in odds:
                enriched_match['odds'] = odds[match_id]

            # Add corners
            if match_id in corners:
                enriched_match['corners'] = corners[match_id]

            enriched.append(enriched_match)

        return enriched
