"""
Parse yeni_taktikler.md and convert to tactics_data.py format
Updated to support all 18 tactic types
"""
import re

# Field name mappings from Turkish to API field names
FIELD_MAPPINGS = {
    # 1X2
    "1": "home",
    "2": "away",
    "X": "draw",

    # Odds changes
    "değişim 1": "odds_change_home",
    "değişim 2": "odds_change_away",
    "değişim x": "odds_change_draw",

    # Asian Handicap
    "Asya Açılış": "asian_open",
    "Asya Kapanış": "asian_close",
    "Asya Çıkış": "asian_up",
    "asya çıkış": "asian_up",
    "Asya iniş": "asian_down",
    "asya iniş": "asian_down",

    # Goal scoring
    "Dep Gol": "away_scores",
    "Ev Gol": "home_scores",

    # BTTS
    "Kg Var": "btts_yes",
    "Kg Var Güven": "btts_confidence",

    # Confidence
    "1x2 Güven": "1x2_confidence",
    "Gol Güven": "goals_confidence",
    "Üst Güven": "over_under_confidence",

    # Goal Lines - multiple case variations
    "goal line açılış": "goal_line_open",
    "Goal line açılış": "goal_line_open",
    "goal line kapanış": "goal_line_close",
    "Goal line kapanış": "goal_line_close",
    "goal line çıkış": "goal_line_up",
    "Goal line çıkış": "goal_line_up",
    "goal line iniş": "goal_line_down",
    "Goal line iniş": "goal_line_down",

    # Over/Under
    "2.5 Üst": "over_2_5",
    "3.5 Üst": "over_3_5",
    "1.5 Üst": "over_1_5",

    # Half-Time 1X2
    "Ht1": "ht_home",
    "Ht2": "ht_away",
    "HtX": "ht_draw",

    # Half-Time Confidence
    "Ht Güven": "ht_1x2_confidence",
    "Ht Gol Güven": "ht_goals_confidence",

    # Half-Time Asian - multiple case variations
    "ht asya açılış": "ht_asian_open",
    "ht asya kapanış": "ht_asian_close",
    "ht asya çıkış": "ht_asian_up",
    "ht asya iniş": "ht_asian_down",

    # Half-Time Odds Changes
    "ht2 değişim": "ht_odds_change_away",
    "ht1 değişim": "ht_odds_change_home",
    "htx değişim": "ht_odds_change_draw",

    # Half-Time Goal Lines (iy = ilk yarı)
    "iy goal line açılış": "ht_goal_line_open",
    "iy goal line kapanış": "ht_goal_line_close",
    "iy goal line çıkış": "ht_goal_line_up",
    "iy goal line iniş": "ht_goal_line_down",

    # Half-Time Over/Under
    "Ht 0.5 Üst": "ht_over_0_5",
    "Ht 1.5 Üst": "ht_over_1_5",
}

def parse_condition(condition_str):
    """Parse a single condition like '1 >= 59.60' or 'değişim x >= 13.10'"""
    # Clean up the condition
    condition_str = condition_str.strip()

    # Match pattern: field operator value
    match = re.match(r'(.+?)\s*(>=|<=|>|<|==)\s*(\d+\.?\d*)', condition_str)

    if not match:
        print(f"WARNING: Could not parse condition: {condition_str}")
        return None

    field_name = match.group(1).strip()
    operator = match.group(2)
    value = float(match.group(3))

    # Map Turkish field name to API field name
    api_field = FIELD_MAPPINGS.get(field_name)

    if not api_field:
        print(f"WARNING: Unknown field name: {field_name}")
        return None

    return (api_field, operator, value)

def parse_tactics_from_file(filepath):
    """Parse yeni_taktikler.md and extract tactics"""

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # All 18 tactic types
    tactics = {
        "MS1": {"2li": [], "3lu": []},
        "MS2": {"2li": [], "3lu": []},
        "MSX": {"2li": [], "3lu": []},
        "MS1_1_5_UST": {"2li": [], "3lu": []},
        "MS2_1_5_UST": {"2li": [], "3lu": []},
        "CIFT_1X": {"2li": [], "3lu": []},
        "CIFT_X2": {"2li": [], "3lu": []},
        "CIFT_12": {"2li": [], "3lu": []},
        "IY1": {"2li": [], "3lu": []},
        "IY2": {"2li": [], "3lu": []},
        "IYX": {"2li": [], "3lu": []},
        "2.5_UST": {"2li": [], "3lu": []},
        "2.5_ALT": {"2li": [], "3lu": []},
        "1.5_UST": {"2li": [], "3lu": []},
        "3.5_UST": {"2li": [], "3lu": []},
        "KG_VAR": {"2li": [], "3lu": []},
        "IY_0.5_UST": {"2li": [], "3lu": []},
        "IY_1.5_UST": {"2li": [], "3lu": []},
    }

    # Map section names - all 18 types
    section_mapping = {
        "## Ev Kazanır (MS1)": "MS1",
        "## Deplasman Kazanır (MS2)": "MS2",
        "## Beraberlik (MSX)": "MSX",
        "## Ev Sahibi 1.5 Üst (2+ Gol) (MS1_1_5_UST)": "MS1_1_5_UST",
        "## Deplasman 1.5 Üst (2+ Gol) (MS2_1_5_UST)": "MS2_1_5_UST",
        "## 1X Çifte Şans (Kapanış MS1≥1.80) (CIFT_1X)": "CIFT_1X",
        "## X2 Çifte Şans (Kapanış MS2≥1.80) (CIFT_X2)": "CIFT_X2",
        "## 12 Çifte Şans (Kapanış MSX≤3.50) (CIFT_12)": "CIFT_12",
        "## İlk Yarı Ev Kazanır (IY1)": "IY1",
        "## İlk Yarı Deplasman Kazanır (IY2)": "IY2",
        "## İlk Yarı Beraberlik (IYX)": "IYX",
        "## 2.5 Üst (2.5_UST)": "2.5_UST",
        "## 2.5 Alt (2.5_ALT)": "2.5_ALT",
        "## 1.5 Üst (1.5_UST)": "1.5_UST",
        "## 3.5 Üst (3.5_UST)": "3.5_UST",
        "## Karşılıklı Gol Var (KG_VAR)": "KG_VAR",
        "## İlk Yarı 0.5 Üst (IY_0.5_UST)": "IY_0.5_UST",
        "## İlk Yarı 1.5 Üst (IY_1.5_UST)": "IY_1.5_UST",
    }

    lines = content.split('\n')
    current_section = None
    current_subsection = None

    for line in lines:
        line = line.strip()

        # Check for section headers
        if line.startswith("## "):
            current_section = None
            for header, section_key in section_mapping.items():
                if line.startswith(header):
                    current_section = section_key
                    break

        # Check for subsection headers
        elif "### En iyi taktikler - 2li" in line:
            current_subsection = "2li"
        elif "### En iyi taktikler - 3lu" in line or "### En iyi taktikler - 3lü" in line:
            current_subsection = "3lu"

        # Parse tactic rows (starts with |)
        elif line.startswith("|") and current_section and current_subsection:
            # Skip header and separator rows
            if "Başarı %" in line or line.startswith("| - |") or "# |" in line:
                continue

            # Parse the row
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 7:
                continue

            try:
                # Extract fields: | # | Başarı % | Doğru/Toplam | Kapsama % | Skor | Kural |
                success_pct = float(parts[2])
                samples_str = parts[3].split("/")
                samples = int(samples_str[1])  # Total samples
                rule_str = parts[6]

                # Parse conditions from rule
                conditions_strs = rule_str.split(" VE ")
                conditions = []

                for cond_str in conditions_strs:
                    parsed = parse_condition(cond_str)
                    if parsed:
                        conditions.append(parsed)

                if conditions:  # Only add if we have valid conditions
                    tactic = {
                        "success": success_pct,
                        "samples": samples,
                        "strategy": "TOP",
                        "conditions": conditions
                    }
                    tactics[current_section][current_subsection].append(tactic)

            except (ValueError, IndexError) as e:
                # Skip rows that don't match expected format
                continue

    return tactics

def generate_tactics_file(tactics, output_file):
    """Generate new tactics_data.py file with all 18 tactic types"""

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('"""\n')
        f.write('Tactics Data - Gelişmiş Taktik Kuralları\n')
        f.write('Her taktik: başarı oranı, örnek sayısı ve koşullar içerir\n')
        f.write('Sadece yüksek kaliteli taktikler (en iyi 2\'li ve 3\'lü kombinasyonlar)\n')
        f.write('"""\n\n')

        # Helper function to write a tactic section
        def write_tactic_section(section_key, var_name, comment, max_2li=10, max_3lu=10):
            f.write(f'# {comment}\n')
            f.write(f'{var_name} = [\n')

            f.write('    # 2\'li - En İyiler\n')
            for tactic in tactics[section_key]["2li"][:max_2li]:
                strategy = "AGGRESSIVE" if tactic["success"] > 90 else "BALANCED" if tactic["success"] > 80 else "TOP"
                f.write(f'    {{"success": {tactic["success"]}, "samples": {tactic["samples"]}, ')
                f.write(f'"strategy": "{strategy}", "conditions": {tactic["conditions"]}}},\n')

            f.write('\n    # 3\'lü - En İyiler\n')
            for tactic in tactics[section_key]["3lu"][:max_3lu]:
                strategy = "AGGRESSIVE" if tactic["success"] > 90 else "BALANCED" if tactic["success"] > 80 else "TOP"
                f.write(f'    {{"success": {tactic["success"]}, "samples": {tactic["samples"]}, ')
                f.write(f'"strategy": "{strategy}", "conditions": {tactic["conditions"]}}},\n')

            f.write(']\n\n')

        # Write all 18 tactic types
        write_tactic_section("MS1", "MS1_TACTICS", "MS1 - EV KAZANIR")
        write_tactic_section("MS2", "MS2_TACTICS", "MS2 - DEPLASMAN KAZANIR")
        write_tactic_section("MSX", "MSX_TACTICS", "MSX - BERABERLİK")
        write_tactic_section("MS1_1_5_UST", "MS1_1_5_UST_TACTICS", "MS1 1.5 ÜST - EV SAHİBİ 2+ GOL")
        write_tactic_section("MS2_1_5_UST", "MS2_1_5_UST_TACTICS", "MS2 1.5 ÜST - DEPLASMAN 2+ GOL")
        write_tactic_section("CIFT_1X", "CIFT_1X_TACTICS", "ÇİFTE ŞANS 1X")
        write_tactic_section("CIFT_X2", "CIFT_X2_TACTICS", "ÇİFTE ŞANS X2")
        write_tactic_section("CIFT_12", "CIFT_12_TACTICS", "ÇİFTE ŞANS 12")
        write_tactic_section("IY1", "HT_1_TACTICS", "İY1 - İLK YARI EV KAZANIR")
        write_tactic_section("IY2", "HT_2_TACTICS", "İY2 - İLK YARI DEPLASMAN KAZANIR")
        write_tactic_section("IYX", "HT_X_TACTICS", "İYX - İLK YARI BERABERLİK")
        write_tactic_section("2.5_UST", "OVER_2_5_TACTICS", "2.5 ÜST")
        write_tactic_section("2.5_ALT", "UNDER_2_5_TACTICS", "2.5 ALT")
        write_tactic_section("1.5_UST", "OVER_1_5_TACTICS", "1.5 ÜST")
        write_tactic_section("3.5_UST", "OVER_3_5_TACTICS", "3.5 ÜST")
        write_tactic_section("KG_VAR", "KG_VAR_TACTICS", "KG VAR - KARŞILIKLI GOL VAR")
        write_tactic_section("IY_0.5_UST", "HT_OVER_0_5_TACTICS", "İY 0.5 ÜST - İLK YARI EN AZ 1 GOL")
        write_tactic_section("IY_1.5_UST", "HT_OVER_1_5_TACTICS", "İY 1.5 ÜST - İLK YARI EN AZ 2 GOL")

        # Add FIELD_MAPPINGS at the end
        f.write('# Alan eşleştirmeleri (tactics field → API yolları)\n')
        f.write('FIELD_MAPPINGS = {\n')
        f.write('    # Goal Lines\n')
        f.write('    "over_3_5": ["final_predictions", "goal_lines", "over_3_5"],\n')
        f.write('    "over_2_5": ["final_predictions", "goal_lines", "over_2_5"],\n')
        f.write('    "over_1_5": ["final_predictions", "goal_lines", "over_1_5"],\n')
        f.write('    "under_2_5": ["final_predictions", "goal_lines", "under_2_5"],\n')
        f.write('    "under_1_5": ["final_predictions", "goal_lines", "under_1_5"],\n')
        f.write('    \n')
        f.write('    # BTTS\n')
        f.write('    "btts_yes": ["final_predictions", "btts", "yes"],\n')
        f.write('    "btts_no": ["final_predictions", "btts", "no"],\n')
        f.write('    "btts_confidence": ["final_predictions", "btts", "confidence"],\n')
        f.write('    \n')
        f.write('    # Team Scoring\n')
        f.write('    "home_scores": ["final_predictions", "team_scoring", "home_team_scores"],\n')
        f.write('    "away_scores": ["final_predictions", "team_scoring", "away_team_scores"],\n')
        f.write('    \n')
        f.write('    # 1X2\n')
        f.write('    "home": ["final_predictions", "1x2", "home"],\n')
        f.write('    "draw": ["final_predictions", "1x2", "draw"],\n')
        f.write('    "away": ["final_predictions", "1x2", "away"],\n')
        f.write('    "1x2_confidence": ["final_predictions", "1x2", "confidence"],\n')
        f.write('    \n')
        f.write('    # Half-Time Goals\n')
        f.write('    "ht_over_0_5": ["final_predictions", "ht_goals", "over_0_5"],\n')
        f.write('    "ht_over_1_5": ["final_predictions", "ht_goals", "over_1_5"],\n')
        f.write('    "ht_under_0_5": ["final_predictions", "ht_goals", "under_0_5"],\n')
        f.write('    "ht_under_1_5": ["final_predictions", "ht_goals", "under_1_5"],\n')
        f.write('    "ht_goals_confidence": ["final_predictions", "ht_goals", "confidence"],\n')
        f.write('    \n')
        f.write('    # Half-Time 1X2\n')
        f.write('    "ht_home": ["final_predictions", "ht_1x2", "home"],\n')
        f.write('    "ht_draw": ["final_predictions", "ht_1x2", "draw"],\n')
        f.write('    "ht_away": ["final_predictions", "ht_1x2", "away"],\n')
        f.write('    "ht_1x2_confidence": ["final_predictions", "ht_1x2", "confidence"],\n')
        f.write('    \n')
        f.write('    # Confidence Scores\n')
        f.write('    "goals_confidence": ["final_predictions", "goal_lines", "confidence"],\n')
        f.write('    "over_under_confidence": ["final_predictions", "goal_lines", "confidence"],\n')
        f.write('    \n')
        f.write('    # Odds Movement\n')
        f.write('    "odds_change_home": ["odds_trend_analysis", "european_odds_movement", "changes", "home"],\n')
        f.write('    "odds_change_away": ["odds_trend_analysis", "european_odds_movement", "changes", "away"],\n')
        f.write('    "odds_change_draw": ["odds_trend_analysis", "european_odds_movement", "changes", "draw"],\n')
        f.write('\n')
        f.write('    # European Odds Closing Values\n')
        f.write('    "ms1_close_odds": ["odds_trend_analysis", "european_odds_movement", "pre_match_odds", "home"],\n')
        f.write('    "ms2_close_odds": ["odds_trend_analysis", "european_odds_movement", "pre_match_odds", "away"],\n')
        f.write('    "msx_close_odds": ["odds_trend_analysis", "european_odds_movement", "pre_match_odds", "draw"],\n')
        f.write('    \n')
        f.write('    # Half-Time Odds Changes\n')
        f.write('    "ht_odds_change_home": ["odds_trend_analysis", "ht_european_odds_movement", "changes", "home"],\n')
        f.write('    "ht_odds_change_away": ["odds_trend_analysis", "ht_european_odds_movement", "changes", "away"],\n')
        f.write('    "ht_odds_change_draw": ["odds_trend_analysis", "ht_european_odds_movement", "changes", "draw"],\n')
        f.write('    \n')
        f.write('    # Asian Handicap\n')
        f.write('    "asian_open": ["odds_trend_analysis", "asian_handicap_line_movement", "first_line"],\n')
        f.write('    "asian_close": ["odds_trend_analysis", "asian_handicap_line_movement", "pre_match_line"],\n')
        f.write('    "asian_up": ["odds_trend_analysis", "asian_handicap_line_movement", "line_increased"],\n')
        f.write('    "asian_down": ["odds_trend_analysis", "asian_handicap_line_movement", "line_decreased"],\n')
        f.write('    \n')
        f.write('    # Half-Time Asian\n')
        f.write('    "ht_asian_open": ["odds_trend_analysis", "ht_asian_handicap_line_movement", "first_line"],\n')
        f.write('    "ht_asian_close": ["odds_trend_analysis", "ht_asian_handicap_line_movement", "pre_match_line"],\n')
        f.write('    "ht_asian_up": ["odds_trend_analysis", "ht_asian_handicap_line_movement", "line_increased"],\n')
        f.write('    "ht_asian_down": ["odds_trend_analysis", "ht_asian_handicap_line_movement", "line_decreased"],\n')
        f.write('    \n')
        f.write('    # Goal Line Movement\n')
        f.write('    "goal_line_open": ["odds_trend_analysis", "over_under_line_movement", "first_line"],\n')
        f.write('    "goal_line_close": ["odds_trend_analysis", "over_under_line_movement", "pre_match_line"],\n')
        f.write('    "goal_line_up": ["odds_trend_analysis", "over_under_line_movement", "line_increased"],\n')
        f.write('    "goal_line_down": ["odds_trend_analysis", "over_under_line_movement", "line_decreased"],\n')
        f.write('    \n')
        f.write('    # Half-Time Goal Line\n')
        f.write('    "ht_goal_line_open": ["odds_trend_analysis", "ht_over_under_line_movement", "first_line"],\n')
        f.write('    "ht_goal_line_close": ["odds_trend_analysis", "ht_over_under_line_movement", "pre_match_line"],\n')
        f.write('    "ht_goal_line_up": ["odds_trend_analysis", "ht_over_under_line_movement", "line_increased"],\n')
        f.write('    "ht_goal_line_down": ["odds_trend_analysis", "ht_over_under_line_movement", "line_decreased"],\n')
        f.write('}\n')

if __name__ == "__main__":
    import os

    # Get current directory
    current_dir = os.path.dirname(os.path.abspath(__file__))

    # Parse tactics from yeni_taktikler.md
    input_file = os.path.join(current_dir, "yeni_taktikler.md")
    output_file = os.path.join(current_dir, "analysis", "tactics_data_new.py")

    print(f"Parsing tactics from {input_file}...")
    tactics = parse_tactics_from_file(input_file)

    # Print statistics
    print("\n=== Tactic Statistics ===")
    for section, data in tactics.items():
        if data['2li'] or data['3lu']:
            print(f"{section}: {len(data['2li'])} 2'li, {len(data['3lu'])} 3'lü tactics")

    # Generate new tactics_data.py
    print(f"\nGenerating new tactics_data.py at {output_file}...")
    generate_tactics_file(tactics, output_file)

    print("\nDone! New tactics saved to analysis/tactics_data_new.py")
    print("Review the file and rename it to tactics_data.py to replace the old one.")
