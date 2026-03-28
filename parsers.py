"""
Data parsing utilities for match information
"""
import re
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# ============================================================================
# PRE-COMPILED REGEX PATTERNS (Performance optimization)
# Compiling once at module load instead of every function call
# ============================================================================

# JavaScript array patterns for match data parsing
RE_MATCH_ARRAY = re.compile(r"A\[(\d+)\]=\[(.*?)\];")
RE_LEAGUE_ARRAY = re.compile(r"B\[(\d+)\]=\[(.*?)\];")
RE_COUNTRY_ARRAY = re.compile(r"C\[(\d+)\]=\[(.*?)\];")

# HTML table parsing patterns
RE_TABLE_ROW_ID = re.compile(r"tr\d+_\d+")
RE_FSCORE_CLASS = re.compile(r"fscore_")
RE_HSCORE_CLASS = re.compile(r"hscore_")
RE_FCORNER_CLASS = re.compile(r"fcorner_")
RE_HCORNER_CLASS = re.compile(r"hcorner_")

# Date and league extraction patterns
RE_FORMAT_DATE = re.compile(r"formatDate\('([^']+)'")
RE_LEAGUE_ID_URL = re.compile(r'/(leagueinfo|league|subleague)/(\d+)')
RE_LEAGUE_CLASS = re.compile(r'league', re.IGNORECASE)
RE_COMPETITION_CLASS = re.compile(r'competition', re.IGNORECASE)
RE_LEAGUE_HREF = re.compile(r'(league|competition|sclass)', re.IGNORECASE)

class MatchDateParser:
    """Parser for date-based match data from JavaScript responses"""
    
    def __init__(self):
        self.leagues = {}  # B dizisi cache
        self.countries = {}  # C dizisi cache
    
    def parse_date_response(self, response_text):
        """date.txt formatındaki veriyi parse et"""
        try:
            logger.info(f"[SEARCH] Parsing date response, length: {len(response_text) if response_text else 0}")

            # JSON içindeki JavaScript kodunu çıkar
            json_data = json.loads(response_text)
            logger.info(f"[INFO] JSON parsed successfully, keys: {list(json_data.keys())}")

            js_code = json_data.get('Data', '')
            logger.info(f"📦 JavaScript code length: {len(js_code)}")

            if not js_code:
                logger.error("[ERROR] No JavaScript code found in 'Data' field")
                return None

            # A, B, C dizilerini parse et
            matches = self._parse_matches(js_code)
            logger.info(f"⚽ Parsed {len(matches)} matches")

            leagues = self._parse_leagues(js_code)
            logger.info(f"🏆 Parsed {len(leagues)} leagues")

            countries = self._parse_countries(js_code)
            logger.info(f"🌍 Parsed {len(countries)} countries")

            result = {
                'matches': matches,
                'leagues': leagues,
                'countries': countries
            }

            if not matches:
                logger.warning("[WARN] No matches found in parsed data")

            return result

        except json.JSONDecodeError as e:
            logger.error(f"[ERROR] JSON decode error: {e}")
            logger.error(f"[ERROR] Response text preview: {response_text[:500] if response_text else 'None'}")
            return None
        except Exception as e:
            logger.error(f"[ERROR] Parse error: {e}")
            import traceback
            logger.error(f"[ERROR] Traceback: {traceback.format_exc()}")
            return None
    
    def _parse_matches(self, js_code):
        """A dizisini parse et - maç bilgileri"""
        matches = []

        # A[n]=[...] formatındaki satırları bul (pre-compiled pattern kullan)
        for match in RE_MATCH_ARRAY.finditer(js_code):
            try:
                index = int(match.group(1))
                data_str = match.group(2)
                
                # Veriyi parse et
                match_data = self._parse_match_data(data_str)
                if match_data:
                    matches.append(match_data)
                    
            except Exception as e:
                logger.warning(f"Match parse error for index {index}: {e}")
                continue
        
        return matches
    
    def _parse_match_data(self, data_str):
        """Tek maç verisini parse et"""
        try:
            # JavaScript array parsing
            parts = []
            current = ""
            in_quotes = False
            
            for char in data_str:
                if char == "'" and not in_quotes:
                    in_quotes = True
                elif char == "'" and in_quotes:
                    in_quotes = False
                    parts.append(current)
                    current = ""
                elif char == "," and not in_quotes:
                    if current.strip():
                        parts.append(current.strip())
                    current = ""
                else:
                    current += char
            
            if current.strip():
                parts.append(current.strip())
            
            # En az 7 alan olmalı
            if len(parts) < 7:
                return None
            
            # Tarih parse et
            datetime_str = parts[6] if len(parts) > 6 else ""
            match_time = self._parse_datetime(datetime_str)
            
            return {
                'match_id': int(parts[0]) if parts[0].isdigit() else None,
                'league_id': int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None,
                'home_team_id': int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None,
                'away_team_id': int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else None,
                'home_team': parts[4] if len(parts) > 4 else "",
                'away_team': parts[5] if len(parts) > 5 else "",
                'match_time': match_time,
                'match_datetime_raw': datetime_str
            }
            
        except Exception as e:
            logger.error(f"Match data parse error: {e}")
            return None
    
    def _parse_datetime(self, datetime_str):
        """
        Parse datetime from multiple formats:
        - New format: '2024-12-27 16:00' or '2024-12-27 16:00:00'
        - Old format: '2025,7,24,13,00,00'
        """
        if not datetime_str:
            return None

        try:
            # Yeni format: YYYY-MM-DD HH:MM veya YYYY-MM-DD HH:MM:SS
            if '-' in datetime_str:
                # Önce saniyeli formatı dene
                for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M']:
                    try:
                        return datetime.strptime(datetime_str.strip(), fmt)
                    except ValueError:
                        continue

            # Eski format: virgül ile ayrılmış (2026,0,1,17,30,00)
            # NOT: Ay 0-indexed geliyor (0=Ocak, 11=Aralık), +1 eklenmeli
            parts = datetime_str.split(',')
            if len(parts) >= 6:
                year = int(parts[0])
                month = int(parts[1]) + 1  # JavaScript 0-indexed ay -> Python 1-indexed
                day = int(parts[2])
                hour = int(parts[3])
                minute = int(parts[4])
                second = int(parts[5])
                return datetime(year, month, day, hour, minute, second)
        except Exception as e:
            logger.debug(f"DateTime parse error for '{datetime_str}': {e}")

        return None
    
    def _parse_leagues(self, js_code):
        """B dizisini parse et - lig bilgileri"""
        leagues = {}

        # Pre-compiled pattern kullan
        for match in RE_LEAGUE_ARRAY.finditer(js_code):
            try:
                index = int(match.group(1))
                data_str = match.group(2)
                
                # Basit parse
                parts = [p.strip().strip("'\"") for p in data_str.split(',')]
                if len(parts) >= 3:
                    leagues[index] = {
                        'league_id': parts[0],
                        'league_code': parts[1],
                        'league_name': parts[2],
                        'color': parts[3] if len(parts) > 3 else None
                    }
            except:
                continue
        
        return leagues
    
    def _parse_countries(self, js_code):
        """C dizisini parse et - ülke bilgileri"""
        countries = {}

        # Pre-compiled pattern kullan
        for match in RE_COUNTRY_ARRAY.finditer(js_code):
            try:
                index = int(match.group(1))
                data_str = match.group(2)
                
                parts = [p.strip().strip("'\"") for p in data_str.split(',')]
                if len(parts) >= 2:
                    countries[index] = {
                        'country_id': parts[0],
                        'country_name': parts[1]
                    }
            except:
                continue
        
        return countries


# --- HTML Parsing Functions ---

def clean_score_data(text):
    """Clean score data by removing parentheses and extra whitespace"""
    if not text:
        return ""
    
    # Remove parentheses and clean whitespace
    cleaned = text.strip()
    if cleaned.startswith('(') and cleaned.endswith(')'):
        cleaned = cleaned[1:-1]  # Remove outer parentheses
    
    return cleaned.strip()

def debug_table_structure(soup, table_id):
    """Debug function to analyze table structure"""
    table = soup.find('table', id=table_id)
    if not table:
        return {"error": f"Table with id '{table_id}' not found"}
    
    debug_info = {
        "table_id": table_id,
        "total_rows": 0,
        "sample_row_structure": []
    }
    
    data_rows = table.find_all('tr', id=RE_TABLE_ROW_ID)
    debug_info["total_rows"] = len(data_rows)
    
    # Analyze first few rows
    for i, row in enumerate(data_rows[:3]):  # First 3 rows
        cells = row.find_all('td')
        row_structure = {
            "row_index": i,
            "cell_count": len(cells),
            "cells": []
        }
        
        for j, cell in enumerate(cells):
            cell_info = {
                "index": j,
                "text": cell.text.strip()[:50] + "..." if len(cell.text.strip()) > 50 else cell.text.strip(),
                "has_spans": len(cell.find_all('span')) > 0,
                "span_classes": [span.get('class', []) for span in cell.find_all('span')]
            }
            row_structure["cells"].append(cell_info)
        
        debug_info["sample_row_structure"].append(row_structure)
    
    return debug_info

def parse_player_list(container):
    """Helper function to parse a list of players from a container."""
    if not container:
        return []
    player_list = []
    player_rows = container.find_all('div', class_='player-row')
    for player_row in player_rows:
        player_data = {
            "player_id": player_row.get("playerid"),
            "position": player_row.find('b').text.strip() if player_row.find('b') else "",
            "number": player_row.find('span').text.strip() if player_row.find('span') else "",
            "name": player_row.find('a').text.strip() if player_row.find('a') else ""
        }
        player_list.append(player_data)
    return player_list

def parse_standings_table(table):
    """Parses a standings table into a structured dictionary."""
    data = {"full_time": [], "half_time": []}
    all_rows = table.find_all('tr')
    def parse_block(rows_block):
        parsed_data = []
        if not rows_block or len(rows_block) < 2:
            return parsed_data
        headers = [th.text.strip() for th in rows_block[0].find_all('th')]
        for data_row in rows_block[1:]:
            cells = data_row.find_all('td')
            if len(cells) == len(headers):
                row_data = {headers[i]: cells[i].text.strip() for i in range(len(headers))}
                parsed_data.append(row_data)
        return parsed_data
    split_index = -1
    for i, row in enumerate(all_rows):
        if "HT" in row.text and row.find('th'):
            split_index = i
            break
    if split_index != -1:
        ft_rows = all_rows[2:split_index]
        ht_rows = all_rows[split_index+1:]
        ft_headers_row = all_rows[1]
        ht_headers_row = all_rows[split_index]
        data["full_time"] = parse_block([ft_headers_row] + ft_rows)
        data["half_time"] = parse_block([ht_headers_row] + ht_rows)
    return data

def parse_match_list_table(soup, table_id):
    """Parse match list table with given ID"""
    table = soup.find('table', id=table_id)
    if not table:
        return []
    rows = []
    data_rows = table.find_all('tr', id=RE_TABLE_ROW_ID)
    for row in data_rows:
        cells = row.find_all('td')
        if len(cells) < 8:
            continue
        
        # Get score cells with fallback (pre-compiled patterns)
        score_cell = cells[3].find('span', class_=RE_FSCORE_CLASS)
        ht_score_cell = cells[3].find('span', class_=RE_HSCORE_CLASS)
        corner_cell = cells[5].find('span', class_=RE_FCORNER_CLASS)
        ht_corner_cell = cells[5].find('span', class_=RE_HCORNER_CLASS)
        
        # Extract date - try multiple approaches
        date_text = ""
        if len(cells) > 1:
            # Try data-t attribute first (most reliable)
            date_span = cells[1].find('span', {'data-t': True})
            if date_span:
                date_text = date_span.get('data-t', '').strip()
            else:
                # Fallback: Try direct text
                date_text = cells[1].text.strip()
                # If empty, try looking for nested elements
                if not date_text:
                    date_element = cells[1].find('span') or cells[1].find('a')
                    if date_element:
                        date_text = date_element.text.strip()

                # Last resort: Try to extract from JavaScript formatDate function
                if not date_text:
                    script_element = cells[1].find('script')
                    if script_element and 'formatDate' in script_element.text:
                        # Extract date from formatDate('2025,8-1,17,17,30,00', 3)
                        match = RE_FORMAT_DATE.search(script_element.text)
                        if match:
                            js_date = match.group(1)
                            # Convert JavaScript date format to standard format
                            date_text = self._convert_js_date_format(js_date)
        
        # Extract result - try multiple positions and approaches
        result_text = ""
        if len(cells) > 11:
            result_text = cells[11].text.strip()
        elif len(cells) > 7:
            result_text = cells[7].text.strip()
        
        # If still empty, try looking in other cells or nested elements
        if not result_text:
            for cell_idx in [6, 7, 8, 9, 10, 11]:
                if len(cells) > cell_idx:
                    potential_result = cells[cell_idx].text.strip()
                    if potential_result and potential_result not in ['', '-', '?']:
                        result_text = potential_result
                        break
        
        row_data = {
            "league": cells[0].text.strip() if len(cells) > 0 else "",
            "date": date_text,
            "home_team": cells[2].text.strip() if len(cells) > 2 else "",
            "score": clean_score_data(score_cell.text) if score_cell else "",
            "ht_score": clean_score_data(ht_score_cell.text) if ht_score_cell else "",
            "away_team": cells[4].text.strip() if len(cells) > 4 else "",
            "corner": clean_score_data(corner_cell.text) if corner_cell else "",
            "ht_corner": clean_score_data(ht_corner_cell.text) if ht_corner_cell else "",
            "result": result_text
        }
        rows.append(row_data)
    return rows

@staticmethod
def _convert_js_date_format(js_date):
    """
    Convert JavaScript date format to standard format.
    Supports:
    - Old comma format: '2025,8,17,17,30,00' or '2025,8-1,17,17,30,00'
    - New format: '2024-12-27 16:00' or '2024-12-27 16:00:00'
    """
    if not js_date:
        return ""

    try:
        # Yeni format: YYYY-MM-DD HH:MM veya YYYY-MM-DD HH:MM:SS
        if '-' in js_date and ':' in js_date:
            for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M']:
                try:
                    dt = datetime.strptime(js_date.strip(), fmt)
                    return dt.strftime('%Y-%m-%d %H:%M:%S')
                except ValueError:
                    continue

        # Eski format: '2026,0,1,17,30,00' veya '2025,8-1,17,17,30,00'
        # NOT: Ay 0-indexed geliyor (0=Ocak, 11=Aralık), +1 eklenmeli
        parts = js_date.split(',')
        if len(parts) >= 6:
            year = int(parts[0])
            month = int(parts[1]) + 1  # JavaScript 0-indexed ay -> Python 1-indexed
            day = int(parts[2])
            hour = int(parts[3])
            minute = int(parts[4])
            second = int(parts[5])

            dt = datetime(year, month, day, hour, minute, second)
            return dt.strftime('%Y-%m-%d %H:%M:%S')
    except Exception as e:
        logger.warning(f"Error converting JS date format {js_date}: {e}")
        return ""

def parse_standings(soup):
    """Parse team standings from soup"""
    standings = {}
    standings_parent_div = soup.find('div', id='porletP4')
    if not standings_parent_div:
        return standings
    home_div = standings_parent_div.find('div', class_='home-div')
    guest_div = standings_parent_div.find('div', class_='guest-div')
    if home_div:
        home_table = home_div.find('table', class_='team-table-home')
        if home_table:
            standings['home_team_standings'] = parse_standings_table(home_table)
    if guest_div:
        guest_table = guest_div.find('table', class_='team-table-guest')
        if guest_table:
            standings['away_team_standings'] = parse_standings_table(guest_table)
    return standings

def parse_injury_suspension(soup):
    """Parse injury and suspension data"""
    injury_section = soup.find('div', id='porletP13')
    if not injury_section:
        return {"error": "Injury and Suspension section (porletP13) not found."}
    data = {"home_team": [], "away_team": []}
    home_div = injury_section.find('div', id='injuryH')
    if home_div:
        data["home_team"] = parse_player_list(home_div.find('div', class_='player-list'))
    guest_div = injury_section.find('div', id='injuryG')
    if guest_div:
        data["away_team"] = parse_player_list(guest_div.find('div', class_='player-list'))
    return data

def parse_last_match_lineups(soup):
    """Parse last match lineups"""
    lineup_section = soup.find('div', id='porletP14')
    if not lineup_section:
        return {"error": "Last Match Lineups section (porletP14) not found."}
    data = {"home_team": {}, "away_team": {}}
    home_div = lineup_section.find('div', id='lineupH')
    if home_div:
        formation = home_div.find('div', class_='injury').text.strip() if home_div.find('div', class_='injury') else ""
        player_lists = home_div.find_all('div', class_='player-list')
        starters = parse_player_list(player_lists[0]) if len(player_lists) > 0 else []
        substitutes = parse_player_list(player_lists[1]) if len(player_lists) > 1 else []
        data["home_team"] = {"formation": formation, "starters": starters, "substitutes": substitutes}
    guest_div = lineup_section.find('div', id='lineupG')
    if guest_div:
        formation = guest_div.find('div', class_='injury').text.strip() if guest_div.find('div', class_='injury') else ""
        player_lists = guest_div.find_all('div', class_='player-list')
        starters = parse_player_list(player_lists[0]) if len(player_lists) > 0 else []
        substitutes = parse_player_list(player_lists[1]) if len(player_lists) > 1 else []
        data["away_team"] = {"formation": formation, "starters": starters, "substitutes": substitutes}
    return data

def parse_fixture(soup):
    """Parse fixture data"""
    fixture_section = soup.find('div', id='porletP12')
    if not fixture_section:
        return {"error": "Fixture section (porletP12) not found."}
    data = {"home_team_fixture": [], "away_team_fixture": []}
    def parse_fixture_table(table):
        fixtures = []
        if not table:
            return fixtures
        rows = table.find_all('tr')[1:]
        for row in rows:
            cells = row.find_all('td')
            if len(cells) == 5:
                # Extract date - try multiple approaches
                date_text = ""
                if len(cells) > 1:
                    # Try data-t attribute first (most reliable)
                    date_span = cells[1].find('span', {'data-t': True})
                    if date_span:
                        date_text = date_span.get('data-t', '').strip()
                    else:
                        # Fallback: Try direct text
                        date_text = cells[1].text.strip()
                        # If empty, try looking for nested elements
                        if not date_text:
                            date_element = cells[1].find('span') or cells[1].find('a')
                            if date_element:
                                date_text = date_element.text.strip()

                        # Last resort: Try to extract from JavaScript formatDate function
                        if not date_text:
                            script_element = cells[1].find('script')
                            if script_element and 'formatDate' in script_element.text:
                                match = RE_FORMAT_DATE.search(script_element.text)
                                if match:
                                    js_date = match.group(1)
                                    # Convert JavaScript date format to standard format
                                    date_text = self._convert_js_date_format(js_date)

                fixtures.append({
                    "league": cells[0].get('title', ''),
                    "date": date_text,
                    "type": cells[2].text.strip(),
                    "opponent": cells[3].text.strip(),
                    "countdown": cells[4].text.strip()
                })
        return fixtures
    home_div = fixture_section.find('div', class_='home-div')
    if home_div:
        data["home_team_fixture"] = parse_fixture_table(home_div.find('table'))
    guest_div = fixture_section.find('div', class_='guest-div')
    if guest_div:
        data["away_team_fixture"] = parse_fixture_table(guest_div.find('table'))
    return data

def parse_match_info(soup):
    """Parse match header information"""
    header = soup.find('div', id='fbheader')
    if not header:
        return {"error": "Match info header (fbheader) not found."}

    def get_logo_url(img_tag):
        if not img_tag: return ""
        src = img_tag.get('src', '')
        return f"https:{src}" if src.startswith('//') else src

    home_team_div = header.find('div', class_='home')
    guest_team_div = header.find('div', class_='guest')
    other_info_div = header.find('div', id='otherInfo')
    
    # League bilgisini bulmak için birden fazla yöntem dene
    league_text = ""
    league_id = None

    # Yöntem 1: 'sclassLink' class'ı (en yaygın)
    league_span = header.find('span', class_='sclassLink')
    league_type = None  # 'league' veya 'subleague'

    if league_span:
        league_text = ' '.join(league_span.text.split())
        # League ID ve tipini onclick URL'inden çıkar
        # Örnek: onclick="window.open('//football.nowgoal26.com/leagueinfo/1465')"
        # veya: onclick="window.open('//football.nowgoal26.com/league/31')"
        # veya: onclick="window.open('//football.nowgoal26.com/subleague/1465')"
        onclick_attr = league_span.get('onclick', '')

        # Önce leagueinfo pattern'ini dene (en yaygın) - pre-compiled pattern
        league_id_match = RE_LEAGUE_ID_URL.search(onclick_attr)
        if league_id_match:
            url_type = league_id_match.group(1)
            league_id = int(league_id_match.group(2))
            # leagueinfo genellikle subleague anlamına geliyor
            if url_type == 'leagueinfo':
                league_type = 'subleague'
            else:
                league_type = url_type
    
    # Yöntem 2: Eğer hala boşsa, 'league' içeren class'ları dene (pre-compiled)
    if not league_text:
        league_elem = header.find('span', class_=RE_LEAGUE_CLASS)
        if league_elem:
            league_text = ' '.join(league_elem.text.split())
    
    # Yöntem 3: Eğer hala boşsa, 'competition' içeren class'ları dene (pre-compiled)
    if not league_text:
        competition_elem = header.find('span', class_=RE_COMPETITION_CLASS)
        if competition_elem:
            league_text = ' '.join(competition_elem.text.split())
    
    # Yöntem 4: Eğer hala boşsa, header içindeki tüm a etiketlerini kontrol et (pre-compiled)
    if not league_text:
        league_links = header.find_all('a', href=RE_LEAGUE_HREF)
        if league_links:
            # İlk bulunan link'in text'ini al
            league_text = ' '.join(league_links[0].text.split())
    
    # Yöntem 5: Son çare - header içinde takım adı olmayan tüm span'ları kontrol et
    if not league_text:
        all_spans = header.find_all('span')
        for span in all_spans:
            span_text = span.text.strip()
            # Takım adları veya skor gibi değilse ve yeterince uzunsa
            if span_text and len(span_text) > 3 and not span_text.isdigit():
                # Takım adı olmadığından emin ol
                home_team_name = home_team_div.find('div', class_='sclassName').text.strip() if home_team_div and home_team_div.find('div', class_='sclassName') else ""
                away_team_name = guest_team_div.find('div', class_='sclassName').text.strip() if guest_team_div and guest_team_div.find('div', class_='sclassName') else ""
                
                if home_team_name not in span_text and away_team_name not in span_text:
                    league_text = ' '.join(span_text.split())
                    break

    stadium = ""
    weather = ""
    if other_info_div:
        stadium_icon = other_info_div.find('i', class_='icon-font-animation')
        if stadium_icon and stadium_icon.parent:
            stadium = stadium_icon.parent.text.strip()
        weather_icon = other_info_div.find('i', class_='icon-weather')
        if weather_icon and weather_icon.next_sibling:
            weather = str(weather_icon.next_sibling).strip()

    # Score parsing logic
    score_info = {
        "status": "",
        "home_score": "",
        "away_score": "",
        "ht_score": "",
        "ht_home_score": "",
        "ht_away_score": ""
    }
    
    score_container = header.find('div', id='mScore')
    if score_container:
        state_div = score_container.find('div', class_='state')
        if state_div:
            score_info["status"] = state_div.text.strip()

        scores = score_container.find_all('div', class_='score')
        if len(scores) == 2:
            score_info["home_score"] = scores[0].text.strip()
            score_info["away_score"] = scores[1].text.strip()

        ht_score_span = score_container.find('span', title='Score 1st Half')
        if ht_score_span:
            ht_score_full = ht_score_span.text.strip()
            score_info["ht_score"] = ht_score_full
            if '-' in ht_score_full:
                parts = ht_score_full.split('-')
                score_info["ht_home_score"] = parts[0]
                score_info["ht_away_score"] = parts[1]


    return {
        "league": league_text,
        "league_id": league_id,
        "league_type": league_type,  # 'league' veya 'subleague'
        "match_time_utc": header.find('span', class_='time').get('data-t', '') if header.find('span', class_='time') else "",
        "home_team_name": home_team_div.find('div', class_='sclassName').text.strip() if home_team_div and home_team_div.find('div', class_='sclassName') else "",
        "home_team_logo_url": get_logo_url(home_team_div.find('img')) if home_team_div else "",
        "away_team_name": guest_team_div.find('div', class_='sclassName').text.strip() if guest_team_div and guest_team_div.find('div', class_='sclassName') else "",
        "away_team_logo_url": get_logo_url(guest_team_div.find('img')) if guest_team_div else "",
        "stadium": stadium,
        "weather": weather,
        "score_info": score_info
    }

def parse_first_half_odds(json_data):
    """Parse first half odds JSON data with readable names"""
    try:
        if not json_data or not isinstance(json_data, dict):
            return {"error": "Invalid JSON data for first half odds"}

        # Extract main data structure
        error_code = json_data.get('ErrCode', -1)
        data = json_data.get('Data', {})
        match_state = json_data.get('MatchState', -1)

        if error_code != 0:
            return {"error": f"API returned error code: {error_code}"}

        # Parse mixodds (betting company odds)
        mixodds = data.get('mixodds', [])
        parsed_odds = []

        for odds_entry in mixodds:
            try:
                company_data = {
                    "company_id": odds_entry.get('cid'),
                    "company_name": odds_entry.get('cn', ''),
                    "odds_type": "first_half_odds"
                }

                # Parse European odds (1X2) - g = draw
                euro_data = odds_entry.get('euro', {})
                if euro_data:
                    company_data["european_odds"] = parse_first_half_odds_section(euro_data, 'draw')

                # Parse Asian Handicap odds - g = line
                ah_data = odds_entry.get('ah', {})
                if ah_data:
                    company_data["asian_handicap"] = parse_first_half_odds_section(ah_data, 'line')

                # Parse Over/Under odds - g = line
                ou_data = odds_entry.get('ou', {})
                if ou_data:
                    company_data["over_under"] = parse_first_half_odds_section(ou_data, 'line')

                parsed_odds.append(company_data)
            except Exception as e:
                logger.warning(f"Error parsing first half odds entry: {e}")
                continue

        return {
            "error_code": error_code,
            "match_state": match_state,
            "betting_companies_count": len(parsed_odds),
            "first_half_odds": parsed_odds
        }

    except Exception as e:
        logger.error(f"Error parsing first half odds: {e}")
        return {"error": f"Failed to parse first half odds: {str(e)}"}

def parse_first_half_odds_section(odds_section, line_type):
    """Parse a section of first half odds (f, l, r)"""
    try:
        result = {
            "first_odds": {},
            "pre_match_odds": {},
            "live_odds": {},
            "has_changed": odds_section.get('hr', False)
        }

        # Parse first odds (f)
        first_odds = odds_section.get('f', {})
        for key, value in first_odds.items():
            if value and value.strip():
                try:
                    numeric_value = float(value)
                    readable_key = get_first_half_odds_name(key, line_type)
                    # For European odds, don't add +1 to any values
                    if line_type == 'draw':
                        # European odds: no +1 addition
                        result["first_odds"][readable_key] = f"{numeric_value:.2f}"
                    elif key in ['d', 'u']:
                        # For Asian Handicap/Over-Under: add +1 to away/home
                        adjusted_value = numeric_value + 1
                        result["first_odds"][readable_key] = f"{adjusted_value:.2f}"
                    else:
                        # For line values in ah/ou, don't add +1
                        result["first_odds"][readable_key] = f"{numeric_value:.2f}"
                except ValueError:
                    result["first_odds"][get_first_half_odds_name(key, line_type)] = value

        # Parse pre-match odds (l)
        pre_match_odds = odds_section.get('l', {})
        for key, value in pre_match_odds.items():
            if value and value.strip():
                try:
                    numeric_value = float(value)
                    readable_key = get_first_half_odds_name(key, line_type)
                    # For European odds, don't add +1 to any values
                    if line_type == 'draw':
                        # European odds: no +1 addition
                        result["pre_match_odds"][readable_key] = f"{numeric_value:.2f}"
                    elif key in ['d', 'u']:
                        # For Asian Handicap/Over-Under: add +1 to away/home
                        adjusted_value = numeric_value + 1
                        result["pre_match_odds"][readable_key] = f"{adjusted_value:.2f}"
                    else:
                        # For line values in ah/ou, don't add +1
                        result["pre_match_odds"][readable_key] = f"{numeric_value:.2f}"
                except ValueError:
                    result["pre_match_odds"][get_first_half_odds_name(key, line_type)] = value

        # Parse live odds (r)
        live_odds = odds_section.get('r', {})
        for key, value in live_odds.items():
            if value and value.strip():
                try:
                    numeric_value = float(value)
                    readable_key = get_first_half_odds_name(key, line_type)
                    # For European odds, don't add +1 to any values
                    if line_type == 'draw':
                        # European odds: no +1 addition
                        result["live_odds"][readable_key] = f"{numeric_value:.2f}"
                    elif key in ['d', 'u']:
                        # For Asian Handicap/Over-Under: add +1 to away/home
                        adjusted_value = numeric_value + 1
                        result["live_odds"][readable_key] = f"{adjusted_value:.2f}"
                    else:
                        # For line values in ah/ou, don't add +1
                        result["live_odds"][readable_key] = f"{numeric_value:.2f}"
                except ValueError:
                    result["live_odds"][get_first_half_odds_name(key, line_type)] = value

        return result

    except Exception as e:
        logger.error(f"Error parsing first half odds section: {e}")
        return {}

def get_first_half_odds_name(key, line_type):
    """Convert first half odds key to readable name based on odds type"""
    base_mapping = {
        'd': 'away',      # Deplasman
        'u': 'home',      # Ev sahibi
    }

    if line_type == 'draw':
        # European odds: g = draw
        base_mapping['g'] = 'draw'
    else:
        # Asian Handicap/Over-Under: g = line
        base_mapping['g'] = 'line'

    return base_mapping.get(key, key)

def parse_odds_comp(json_data):
    """Parse odds comparison JSON data with readable names"""
    try:
        if not json_data or not isinstance(json_data, dict):
            return {"error": "Invalid JSON data for odds comparison"}

        # Extract main data structure
        error_code = json_data.get('ErrCode', -1)
        data = json_data.get('Data', {})
        match_state = json_data.get('MatchState', -1)

        if error_code != 0:
            return {"error": f"API returned error code: {error_code}"}

        # Parse mixodds (betting company odds)
        mixodds = data.get('mixodds', [])
        parsed_odds = []

        for odds_entry in mixodds:
            try:
                company_data = {
                    "company_id": odds_entry.get('cid'),
                    "company_name": odds_entry.get('cn', ''),
                    "odds_type": "odds_comparison"
                }

                # Parse European odds (1X2) - g = draw
                euro_data = odds_entry.get('euro', {})
                if euro_data:
                    company_data["european_odds"] = parse_odds_comp_section(euro_data, 'draw')

                # Parse Asian Handicap odds - g = line
                ah_data = odds_entry.get('ah', {})
                if ah_data:
                    company_data["asian_handicap"] = parse_odds_comp_section(ah_data, 'line')

                # Parse Over/Under odds - g = line
                ou_data = odds_entry.get('ou', {})
                if ou_data:
                    company_data["over_under"] = parse_odds_comp_section(ou_data, 'line')

                parsed_odds.append(company_data)
            except Exception as e:
                logger.warning(f"Error parsing odds comparison entry: {e}")
                continue

        return {
            "error_code": error_code,
            "match_state": match_state,
            "betting_companies_count": len(parsed_odds),
            "odds_comparison": parsed_odds
        }

    except Exception as e:
        logger.error(f"Error parsing odds comparison: {e}")
        return {"error": f"Failed to parse odds comparison: {str(e)}"}

def parse_odds_comp_section(odds_section, line_type):
    """Parse a section of odds comparison (f, l, r)"""
    try:
        result = {
            "first_odds": {},
            "pre_match_odds": {},
            "live_odds": {},
            "has_changed": odds_section.get('hr', False)
        }

        # Parse first odds (f)
        first_odds = odds_section.get('f', {})
        for key, value in first_odds.items():
            if value and value.strip():
                try:
                    numeric_value = float(value)
                    readable_key = get_first_half_odds_name(key, line_type)
                    # For European odds, don't add +1 to any values
                    if line_type == 'draw':
                        # European odds: no +1 addition
                        result["first_odds"][readable_key] = f"{numeric_value:.2f}"
                    elif key in ['d', 'u']:
                        # For Asian Handicap/Over-Under: add +1 to away/home
                        adjusted_value = numeric_value + 1
                        result["first_odds"][readable_key] = f"{adjusted_value:.2f}"
                    else:
                        # For line values in ah/ou, don't add +1
                        result["first_odds"][readable_key] = f"{numeric_value:.2f}"
                except ValueError:
                    result["first_odds"][get_first_half_odds_name(key, line_type)] = value

        # Parse pre-match odds (l)
        pre_match_odds = odds_section.get('l', {})
        for key, value in pre_match_odds.items():
            if value and value.strip():
                try:
                    numeric_value = float(value)
                    readable_key = get_first_half_odds_name(key, line_type)
                    # For European odds, don't add +1 to any values
                    if line_type == 'draw':
                        # European odds: no +1 addition
                        result["pre_match_odds"][readable_key] = f"{numeric_value:.2f}"
                    elif key in ['d', 'u']:
                        # For Asian Handicap/Over-Under: add +1 to away/home
                        adjusted_value = numeric_value + 1
                        result["pre_match_odds"][readable_key] = f"{adjusted_value:.2f}"
                    else:
                        # For line values in ah/ou, don't add +1
                        result["pre_match_odds"][readable_key] = f"{numeric_value:.2f}"
                except ValueError:
                    result["pre_match_odds"][get_first_half_odds_name(key, line_type)] = value

        # Parse live odds (r)
        live_odds = odds_section.get('r', {})
        for key, value in live_odds.items():
            if value and value.strip():
                try:
                    numeric_value = float(value)
                    readable_key = get_first_half_odds_name(key, line_type)
                    # For European odds, don't add +1 to any values
                    if line_type == 'draw':
                        # European odds: no +1 addition
                        result["live_odds"][readable_key] = f"{numeric_value:.2f}"
                    elif key in ['d', 'u']:
                        # For Asian Handicap/Over-Under: add +1 to away/home
                        adjusted_value = numeric_value + 1
                        result["live_odds"][readable_key] = f"{adjusted_value:.2f}"
                    else:
                        # For line values in ah/ou, don't add +1
                        result["live_odds"][readable_key] = f"{numeric_value:.2f}"
                except ValueError:
                    result["live_odds"][get_first_half_odds_name(key, line_type)] = value

        return result

    except Exception as e:
        logger.error(f"Error parsing odds comparison section: {e}")
        return {}

def parse_correct_score_odds(json_data):
    """Parse correct score odds JSON data with readable score names"""
    try:
        if not json_data or not isinstance(json_data, dict):
            return {"error": "Invalid JSON data for correct score odds"}

        # Extract main data structure
        error_code = json_data.get('ErrCode', -1)
        data = json_data.get('Data', {})
        match_state = json_data.get('MatchState', -1)

        if error_code != 0:
            return {"error": f"API returned error code: {error_code}"}

        # Odds mapping for readable score names
        score_mapping = {
            'g1': '0:1', 'g2': '0:2', 'g3': '1:2', 'g4': '0:3', 'g5': '1:3',
            'g6': '2:3', 'g7': '0:4', 'g8': '1:4', 'g9': '2:4', 'g10': '3:4',
            'd1': '0:0', 'd2': '1:1', 'd3': '2:2', 'd4': '3:3', 'd5': '4:4',
            'h1': '1:0', 'h2': '2:0', 'h3': '2:1', 'h4': '3:0', 'h5': '3:1',
            'h6': '3:2', 'h7': '4:0', 'h8': '4:1', 'h9': '4:2', 'h10': '4:3',
            'o': 'Other'
        }

        # Parse odds list
        odds_list = data.get('oddsList', [])
        parsed_odds = []

        for odds_entry in odds_list:
            try:
                company_data = {
                    "company_id": odds_entry.get('cid'),
                    "company_name": odds_entry.get('cn', ''),
                    "odds": {},
                    "prevOdds": {}
                }

                # Parse current odds
                current_odds = odds_entry.get('odds', {})
                for key, value in current_odds.items():
                    if key in score_mapping:
                        readable_key = score_mapping[key]
                        company_data["odds"][readable_key] = value

                # Parse previous odds
                prev_odds = odds_entry.get('prevOdds', {})
                for key, value in prev_odds.items():
                    if key in score_mapping:
                        readable_key = score_mapping[key]
                        company_data["prevOdds"][readable_key] = value

                parsed_odds.append(company_data)
            except Exception as e:
                logger.warning(f"Error parsing correct score odds entry: {e}")
                continue

        return {
            "error_code": error_code,
            "match_state": match_state,
            "betting_companies_count": len(parsed_odds),
            "correct_score_odds": parsed_odds
        }

    except Exception as e:
        logger.error(f"Error parsing correct score odds: {e}")
        return {"error": f"Failed to parse correct score odds: {str(e)}"}

def parse_double_chance_odds(json_data):
    """Parse double chance odds JSON data with readable names"""
    try:
        if not json_data or not isinstance(json_data, dict):
            return {"error": "Invalid JSON data for double chance odds"}

        # Extract main data structure
        error_code = json_data.get('ErrCode', -1)
        data = json_data.get('Data', {})
        match_state = json_data.get('MatchState', -1)

        if error_code != 0:
            return {"error": f"API returned error code: {error_code}"}

        # Parse odds list
        odds_list = data.get('oddsList', [])
        parsed_odds = []

        for odds_entry in odds_list:
            try:
                company_data = {
                    "company_id": odds_entry.get('cid'),
                    "company_name": odds_entry.get('cn', ''),
                    "current_odds": {},
                    "previous_odds": {}
                }

                # Parse current odds (fodds) - add +1 to each value
                current_odds = odds_entry.get('fodds', {})
                for key, value in current_odds.items():
                    if value and value.strip():  # Only process non-empty values
                        try:
                            numeric_value = float(value)
                            adjusted_value = numeric_value + 1
                            readable_key = get_double_chance_name(key)
                            company_data["current_odds"][readable_key] = f"{adjusted_value:.2f}"
                        except ValueError:
                            company_data["current_odds"][get_double_chance_name(key)] = value

                # Parse previous odds (lodds) - add +1 to each value
                previous_odds = odds_entry.get('lodds', {})
                for key, value in previous_odds.items():
                    if value and value.strip():  # Only process non-empty values
                        try:
                            numeric_value = float(value)
                            adjusted_value = numeric_value + 1
                            readable_key = get_double_chance_name(key)
                            company_data["previous_odds"][readable_key] = f"{adjusted_value:.2f}"
                        except ValueError:
                            company_data["previous_odds"][get_double_chance_name(key)] = value

                parsed_odds.append(company_data)
            except Exception as e:
                logger.warning(f"Error parsing double chance odds entry: {e}")
                continue

        return {
            "error_code": error_code,
            "match_state": match_state,
            "betting_companies_count": len(parsed_odds),
            "double_chance_odds": parsed_odds
        }

    except Exception as e:
        logger.error(f"Error parsing double chance odds: {e}")
        return {"error": f"Failed to parse double chance odds: {str(e)}"}

def get_double_chance_name(key):
    """Convert double chance key to readable name"""
    mapping = {
        'd': 'X2',
        'g': '12',
        'u': '1X'
    }
    return mapping.get(key, key)

def parse_corner_odds(json_data):
    """Parse corner odds JSON data with readable names"""
    try:
        if not json_data or not isinstance(json_data, dict):
            return {"error": "Invalid JSON data for corner odds"}

        # Extract main data structure
        error_code = json_data.get('ErrCode', -1)
        data = json_data.get('Data', {})
        match_state = json_data.get('MatchState', -1)

        if error_code != 0:
            return {"error": f"API returned error code: {error_code}"}

        # Parse odds list
        odds_list = data.get('oddsList', [])
        parsed_odds = []

        for odds_entry in odds_list:
            try:
                company_data = {
                    "company_id": odds_entry.get('cid'),
                    "company_name": odds_entry.get('cn', ''),
                    "odds_type": "corner_odds",
                    "first_odds": {},
                    "pre_match_odds": {},
                    "live_odds": {},
                    "has_changed": odds_entry.get('odds', {}).get('hr', False)
                }

                odds_data = odds_entry.get('odds', {})

                # Parse first odds (f)
                first_odds = odds_data.get('f', {})
                for key, value in first_odds.items():
                    if value and value.strip():
                        try:
                            numeric_value = float(value)
                            readable_key = get_corner_odds_name(key)
                            # Only add +1 for away and home, not for line
                            if key in ['d', 'u', 'h']:
                                adjusted_value = numeric_value + 1
                                company_data["first_odds"][readable_key] = f"{adjusted_value:.2f}"
                            else:
                                # Line values stay as they are (no +1)
                                company_data["first_odds"][readable_key] = f"{numeric_value:.1f}"
                        except ValueError:
                            company_data["first_odds"][get_corner_odds_name(key)] = value

                # Parse pre-match odds (l)
                pre_match_odds = odds_data.get('l', {})
                for key, value in pre_match_odds.items():
                    if value and value.strip():
                        try:
                            numeric_value = float(value)
                            readable_key = get_corner_odds_name(key)
                            # Only add +1 for away and home, not for line
                            if key in ['d', 'u', 'h']:
                                adjusted_value = numeric_value + 1
                                company_data["pre_match_odds"][readable_key] = f"{adjusted_value:.2f}"
                            else:
                                # Line values stay as they are (no +1)
                                company_data["pre_match_odds"][readable_key] = f"{numeric_value:.1f}"
                        except ValueError:
                            company_data["pre_match_odds"][get_corner_odds_name(key)] = value

                # Parse live odds (r)
                live_odds = odds_data.get('r', {})
                for key, value in live_odds.items():
                    if value and value.strip():
                        try:
                            numeric_value = float(value)
                            readable_key = get_corner_odds_name(key)
                            # Only add +1 for away and home, not for line
                            if key in ['d', 'u', 'h']:
                                adjusted_value = numeric_value + 1
                                company_data["live_odds"][readable_key] = f"{adjusted_value:.2f}"
                            else:
                                # Line values stay as they are (no +1)
                                company_data["live_odds"][readable_key] = f"{numeric_value:.1f}"
                        except ValueError:
                            company_data["live_odds"][get_corner_odds_name(key)] = value

                parsed_odds.append(company_data)
            except Exception as e:
                logger.warning(f"Error parsing corner odds entry: {e}")
                continue

        return {
            "error_code": error_code,
            "match_state": match_state,
            "betting_companies_count": len(parsed_odds),
            "corner_odds": parsed_odds
        }

    except Exception as e:
        logger.error(f"Error parsing corner odds: {e}")
        return {"error": f"Failed to parse corner odds: {str(e)}"}

def get_corner_odds_name(key):
    """Convert corner odds key to readable name"""
    mapping = {
        'd': 'away',      # Deplasman
        'g': 'line',      # Korner çizgisi (örn: 9.5)
        'u': 'home',      # Ev sahibi
        'h': 'home'       # Ev sahibi (alternatif)
    }
    return mapping.get(key, key)

def parse_h2h_details(soup):
    """Parses the h2h details from a soup object."""
    details = {}
    details['standings'] = parse_standings(soup)
    details['head_to_head'] = parse_match_list_table(soup, 'table_v3')
    details['home_team_previous_matches'] = parse_match_list_table(soup, 'table_v1')
    details['away_team_previous_matches'] = parse_match_list_table(soup, 'table_v2')
    details['injury_and_suspension'] = parse_injury_suspension(soup)
    details['last_match_lineups'] = parse_last_match_lineups(soup)
    return details
