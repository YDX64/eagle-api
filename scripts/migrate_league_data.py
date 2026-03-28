#!/usr/bin/env python3
"""
Migration Script: Convert league_gercek.js to leagues_master.json

This script parses the JavaScript array format and converts it to a clean JSON structure
with proper indexing for cups and leagues.
"""

import json
import re
import os
from datetime import datetime
from typing import Dict, List, Set, Tuple

# League code to name mapping (common ones)
CODE_TO_NAME = {
    # England
    "ENG PR": "Premier League",
    "ENG LCH": "Championship",
    "ENG L1": "League One",
    "ENG L2": "League Two",
    "ENG FAC": "FA Cup",
    "ENG LC": "EFL Cup (League Cup)",
    "ENG NL": "National League",
    "EFL Trophy": "EFL Trophy",
    "ENG FAT": "FA Trophy",

    # Italy
    "ITA D1": "Serie A",
    "ITA D2": "Serie B",
    "ITA Cup": "Coppa Italia",
    "ITA SC": "Serie C",

    # Spain
    "SPA D1": "La Liga",
    "SPA D2": "La Liga 2",
    "SPA CUP": "Copa del Rey",

    # Germany
    "GER D1": "Bundesliga",
    "GER D2": "2. Bundesliga",
    "GER D3": "3. Liga",
    "GERC": "DFB Pokal",

    # France
    "FRA D1": "Ligue 1",
    "FRA D2": "Ligue 2",
    "FRAC": "Coupe de France",

    # Europe
    "UEFA CL": "UEFA Champions League",
    "UEFA EL": "UEFA Europa League",
    "UEFA ECL": "UEFA Conference League",
    "UEFA NL": "UEFA Nations League",
    "UEFA SC": "UEFA Super Cup",
    "EURO Cup": "UEFA European Championship",

    # International
    "World Cup": "FIFA World Cup",
    "FCWC": "FIFA Club World Cup",

    # Turkey
    "TUR D1": "Super Lig",
    "TUR D2": "1. Lig",
    "TUR Cup": "Turkiye Kupasi",

    # Netherlands
    "HOL D1": "Eredivisie",
    "HOL D2": "Eerste Divisie",
    "HOLC": "KNVB Beker",

    # Portugal
    "POR D1": "Primeira Liga",
    "POR D2": "Liga Portugal 2",
    "POR CUP": "Taca de Portugal",

    # Belgium
    "BEL D1": "Pro League",
    "BEL D2": "Challenger Pro League",
    "BEL Cup": "Belgian Cup",

    # Russia
    "RUS PR": "Premier Liga",
    "RUS Cup": "Russian Cup",

    # Scotland
    "SCO PR": "Scottish Premiership",
    "SCOFAC": "Scottish FA Cup",
    "SCO LC": "Scottish League Cup",
}


def parse_league_string(league_str: str) -> Dict:
    """
    Parse a league string like "36,ENG PR,1,0,2025-2026,2024-2025,..."

    Format: ID,CODE,TYPE,HAS_SUBLEAGUE,SEASON1,SEASON2,...
    TYPE: 1=league, 2=cup
    HAS_SUBLEAGUE: 1=yes, 0=no
    """
    parts = league_str.split(',')
    if len(parts) < 4:
        return None

    league_id = int(parts[0])
    code = parts[1]
    type_num = int(parts[2])
    has_subleague = parts[3] == '1'
    seasons = parts[4:] if len(parts) > 4 else []

    # Determine type
    comp_type = "cup" if type_num == 2 else "league"

    # Get name from code mapping or use code as fallback
    name = CODE_TO_NAME.get(code, code)

    return {
        "id": league_id,
        "code": code,
        "name": name,
        "type": comp_type,
        "has_subleague": has_subleague,
        "seasons": seasons
    }


def parse_js_file(file_path: str) -> List[Dict]:
    """Parse the league_gercek.js file and extract all country/league data."""

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    countries = []
    cups_set = set()
    leagues_set = set()

    # Find all arr[X] = [...] patterns
    pattern = r'arr\[(\d+)\]\s*=\s*\[(.*?)\];'
    matches = re.findall(pattern, content, re.DOTALL)

    for index, arr_content in matches:
        # Parse the array content
        # Format: ["InfoID_X", "Country", "images/XXX.png", "1", [...leagues...]]

        # Extract country info
        info_match = re.match(r'"([^"]+)",\s*"([^"]+)",\s*"([^"]+)",\s*"(\d+)",\s*\[(.*)\]', arr_content.strip())
        if not info_match:
            continue

        country_id = info_match.group(1)
        country_name = info_match.group(2)
        flag_image = info_match.group(3)
        flag = info_match.group(4)
        leagues_str = info_match.group(5)

        # Build full image URL
        if flag_image and not flag_image.startswith('http'):
            flag_image = f"https://football.nowgoal26.com/Image/info/{flag_image}"

        # Parse leagues array - each league is a quoted string
        league_strings = re.findall(r'"([^"]+)"', leagues_str)

        competitions = []
        for ls in league_strings:
            comp = parse_league_string(ls)
            if comp:
                competitions.append(comp)

                # Add to index sets
                if comp['type'] == 'cup':
                    cups_set.add(comp['id'])
                else:
                    leagues_set.add(comp['id'])

        countries.append({
            "id": country_id,
            "name": country_name,
            "flag_image": flag_image,
            "is_featured": flag == "1",
            "competitions": competitions
        })

    return countries, cups_set, leagues_set


def build_subleague_map(countries: List[Dict]) -> Dict[int, int]:
    """
    Build a map of league_id -> default sub_league_id

    For leagues with has_subleague=True, we'll need to fetch this from the website.
    For now, we'll just mark them as needing lookup.
    """
    subleague_map = {}

    for country in countries:
        for comp in country.get('competitions', []):
            comp_id = comp['id']
            if comp['has_subleague']:
                subleague_map[comp_id] = -1  # Needs lookup
            else:
                subleague_map[comp_id] = 0  # No subleague

    return subleague_map


def main():
    """Main migration function."""

    # Paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    input_file = os.path.join(project_root, 'data', 'league_gercek.js')
    output_file = os.path.join(project_root, 'data', 'leagues_master.json')
    backup_file = os.path.join(project_root, 'data', 'leagues.json.backup')
    old_file = os.path.join(project_root, 'data', 'leagues.json')

    print("=" * 60)
    print("League Data Migration Script")
    print("=" * 60)

    # Check input file exists
    if not os.path.exists(input_file):
        print(f"ERROR: Input file not found: {input_file}")
        return False

    print(f"\n1. Parsing {input_file}...")
    countries, cups_set, leagues_set = parse_js_file(input_file)

    print(f"   Found {len(countries)} countries")
    print(f"   Found {len(cups_set)} cups")
    print(f"   Found {len(leagues_set)} leagues")

    # Build subleague map
    print("\n2. Building subleague map...")
    subleague_map = build_subleague_map(countries)
    needs_lookup = sum(1 for v in subleague_map.values() if v == -1)
    print(f"   {needs_lookup} competitions need subleague lookup")

    # Count total competitions
    total_comps = sum(len(c['competitions']) for c in countries)

    # Build final structure
    print("\n3. Building output structure...")
    output = {
        "metadata": {
            "source": "nowgoal26.com",
            "source_file": "league_gercek.js",
            "generated_at": datetime.now().isoformat(),
            "total_countries": len(countries),
            "total_competitions": total_comps,
            "total_cups": len(cups_set),
            "total_leagues": len(leagues_set)
        },
        "countries": countries,
        "cups_index": sorted(list(cups_set)),
        "leagues_index": sorted(list(leagues_set)),
        "subleague_map": {str(k): v for k, v in subleague_map.items()}
    }

    # Backup old file if exists
    if os.path.exists(old_file):
        print(f"\n4. Backing up old leagues.json to {backup_file}...")
        import shutil
        shutil.copy2(old_file, backup_file)

    # Write output
    print(f"\n5. Writing {output_file}...")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    file_size = os.path.getsize(output_file) / 1024
    print(f"   File size: {file_size:.1f} KB")

    # Print some stats
    print("\n" + "=" * 60)
    print("MIGRATION COMPLETE!")
    print("=" * 60)

    print("\nTop 10 Cup IDs:")
    for cup_id in sorted(cups_set)[:10]:
        # Find the cup name
        for country in countries:
            for comp in country['competitions']:
                if comp['id'] == cup_id:
                    print(f"   {cup_id}: {comp['name']} ({country['name']})")
                    break

    print("\nKey European Competitions:")
    key_comps = [103, 113, 2187, 1864, 90, 84, 51, 54, 81, 83]
    for comp_id in key_comps:
        for country in countries:
            for comp in country['competitions']:
                if comp['id'] == comp_id:
                    print(f"   {comp_id}: {comp['name']} [{comp['type']}] ({country['name']})")
                    break

    return True


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
