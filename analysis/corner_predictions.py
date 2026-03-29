"""
Corner Prediction Algorithm - Statistical corner total prediction
Uses corner odds data from multiple bookmakers + match characteristics.

Features:
1. Total corners over/under (8.5, 9.5, 10.5, 11.5)
2. Home vs Away corner distribution
3. Corner handicap (which team gets more corners)
4. Odds movement direction analysis
5. Value detection vs bookmaker lines

Data sources:
- corner_odds: Multiple bookmakers with opening/closing lines and odds
- odds_comp: AH line as match intensity proxy
- h2h_details: Historical match data
- match_info: League context

Average corners per match in top leagues: ~10 (9.5-10.5 range)
Home teams average ~5.5 corners, away teams ~4.5 corners.
"""
import math
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# League corner averages (total corners per match)
LEAGUE_CORNER_AVERAGES = {
    'premier league': 10.8,
    'la liga': 10.2,
    'serie a': 10.5,
    'bundesliga': 10.4,
    'ligue 1': 9.8,
    'super lig': 10.0,
    'tff 1. lig': 9.5,
    'eredivisie': 10.6,
    'primeira liga': 10.3,
    'brasileirao': 9.8,
    'jupiler pro league': 10.1,
    'championship': 10.5,
}
DEFAULT_CORNER_AVG = 10.0

# Home teams typically take ~55% of corners
HOME_CORNER_SHARE = 0.55


def poisson_probability(lam, k):
    """P(X=k) for Poisson distribution."""
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    try:
        return (lam ** k) * math.exp(-lam) / math.factorial(k)
    except (OverflowError, ValueError):
        return 0.0


def get_league_corner_avg(match_data: Dict) -> float:
    """Get league-specific corner average."""
    match_info = match_data.get('match_info') or {}
    league = match_info.get('league_name', '').lower().strip()

    for key, avg in LEAGUE_CORNER_AVERAGES.items():
        if key in league or league in key:
            return avg
    return DEFAULT_CORNER_AVG


def extract_corner_odds_data(match_data: Dict) -> Dict:
    """
    Extract corner odds from all bookmakers.
    Returns average opening/closing lines and odds.
    """
    corner_data = match_data.get('corner_odds') or {}
    if isinstance(corner_data, dict) and 'corner_odds' in corner_data:
        odds_list = corner_data['corner_odds']
    elif isinstance(corner_data, dict) and 'Data' in corner_data:
        odds_list = corner_data.get('Data', {}).get('oddsList', [])
    elif isinstance(corner_data, list):
        odds_list = corner_data
    else:
        return {}

    if not odds_list:
        return {}

    opening_lines = []
    closing_lines = []
    opening_home_odds = []
    closing_home_odds = []
    opening_away_odds = []
    closing_away_odds = []
    line_raised = 0
    line_lowered = 0
    total_companies = 0

    for company in odds_list:
        first = company.get('first_odds') or company.get('odds', {}).get('f', {})
        pre = company.get('pre_match_odds') or company.get('odds', {}).get('l', {})

        # Extract lines
        f_line = first.get('line') or first.get('g')
        p_line = pre.get('line') or pre.get('g')

        if f_line is not None and p_line is not None:
            try:
                fl = float(f_line)
                pl = float(p_line)
                if fl > 0:
                    opening_lines.append(fl)
                    closing_lines.append(pl)
                    total_companies += 1

                    if pl > fl + 0.2:
                        line_raised += 1
                    elif pl < fl - 0.2:
                        line_lowered += 1

                    # Odds
                    f_home = first.get('home') or first.get('u')
                    p_home = pre.get('home') or pre.get('u')
                    f_away = first.get('away') or first.get('d')
                    p_away = pre.get('away') or pre.get('d')

                    if f_home:
                        opening_home_odds.append(float(f_home))
                    if p_home:
                        closing_home_odds.append(float(p_home))
                    if f_away:
                        opening_away_odds.append(float(f_away))
                    if p_away:
                        closing_away_odds.append(float(p_away))
            except (ValueError, TypeError):
                continue

    if not opening_lines:
        return {}

    avg_opening = sum(opening_lines) / len(opening_lines)
    avg_closing = sum(closing_lines) / len(closing_lines)

    return {
        'avg_opening_line': round(avg_opening, 2),
        'avg_closing_line': round(avg_closing, 2),
        'line_movement': round(avg_closing - avg_opening, 2),
        'line_raised': line_raised,
        'line_lowered': line_lowered,
        'total_companies': total_companies,
        'avg_opening_home_odds': round(sum(opening_home_odds) / len(opening_home_odds), 3) if opening_home_odds else 0,
        'avg_closing_home_odds': round(sum(closing_home_odds) / len(closing_home_odds), 3) if closing_home_odds else 0,
        'avg_opening_away_odds': round(sum(opening_away_odds) / len(opening_away_odds), 3) if opening_away_odds else 0,
        'avg_closing_away_odds': round(sum(closing_away_odds) / len(closing_away_odds), 3) if closing_away_odds else 0,
        'movement_signal': 'over' if line_raised > line_lowered else 'under' if line_lowered > line_raised else 'neutral',
    }


def estimate_corner_lambda(match_data: Dict, corner_odds_info: Dict) -> float:
    """
    Estimate expected total corners (lambda) for Poisson model.

    Primary: Bookmaker closing line (most informative)
    Secondary: League average + match factors
    """
    # Primary: bookmaker line
    closing_line = corner_odds_info.get('avg_closing_line', 0)
    if closing_line > 5:
        # Bookmaker line is the best estimate
        bookmaker_lambda = closing_line
    else:
        bookmaker_lambda = None

    # Secondary: league average with adjustments
    league_avg = get_league_corner_avg(match_data)

    # Match intensity adjustment from AH
    odds_comp = match_data.get('odds_comp') or {}
    odds_list = odds_comp.get('odds_comparison', [])
    ah_lines = []
    for company in odds_list:
        ah = company.get('asian_handicap', {})
        pre = ah.get('pre_match_odds', {})
        line = pre.get('line')
        if line is not None:
            try:
                ah_lines.append(abs(float(line)))
            except (ValueError, TypeError):
                continue

    if ah_lines:
        avg_ah = sum(ah_lines) / len(ah_lines)
        # Close matches (low AH) tend to have more corners
        # Big favorite matches tend to have more corners too (pressing)
        if avg_ah < 0.5:
            intensity_factor = 1.05  # Very competitive
        elif avg_ah > 1.5:
            intensity_factor = 1.08  # Dominant team → more pressing → more corners
        else:
            intensity_factor = 1.0
    else:
        intensity_factor = 1.0

    league_lambda = league_avg * intensity_factor

    # Combine sources
    if bookmaker_lambda:
        # Bookmaker 70%, league model 30%
        final_lambda = bookmaker_lambda * 0.70 + league_lambda * 0.30
    else:
        final_lambda = league_lambda

    # Odds movement adjustment
    movement = corner_odds_info.get('line_movement', 0)
    if movement > 0.3:
        final_lambda += 0.3  # Line went up → expect more corners
    elif movement < -0.3:
        final_lambda -= 0.3

    return max(6.0, min(15.0, round(final_lambda, 2)))


def calculate_corner_over_under(corner_lambda: float) -> Dict:
    """Calculate corner over/under probabilities using Poisson."""
    results = {}
    for line in [7.5, 8.5, 9.5, 10.5, 11.5, 12.5]:
        threshold = int(line) + 1
        prob_under = sum(poisson_probability(corner_lambda, k) for k in range(threshold))
        prob_over = 1.0 - prob_under

        key = str(line).replace('.', '_')
        results[f'over_{key}'] = round(prob_over * 100, 1)
        results[f'under_{key}'] = round(prob_under * 100, 1)

    return results


def calculate_corner_handicap(corner_lambda: float) -> Dict:
    """
    Calculate home vs away corner distribution and handicap.
    Home teams average ~55% of corners.
    """
    home_lambda = corner_lambda * HOME_CORNER_SHARE
    away_lambda = corner_lambda * (1 - HOME_CORNER_SHARE)

    # Corner handicap probabilities (home - away difference)
    max_c = 15
    home_probs = [poisson_probability(home_lambda, k) for k in range(max_c + 1)]
    away_probs = [poisson_probability(away_lambda, k) for k in range(max_c + 1)]

    home_more = 0
    equal = 0
    away_more = 0

    for h in range(max_c + 1):
        for a in range(max_c + 1):
            joint = home_probs[h] * away_probs[a]
            if h > a:
                home_more += joint
            elif h == a:
                equal += joint
            else:
                away_more += joint

    return {
        'home_expected': round(home_lambda, 1),
        'away_expected': round(away_lambda, 1),
        'home_more_corners': round(home_more * 100, 1),
        'equal_corners': round(equal * 100, 1),
        'away_more_corners': round(away_more * 100, 1),
    }


def analyze_corner_predictions(match_data: Dict) -> Dict:
    """
    Main corner prediction analysis function.

    Returns:
        {
            "corner_predictions": {
                "expected_total_corners": float,
                "over_under": {over_8_5, under_8_5, over_9_5, ...},
                "corner_handicap": {home_expected, away_expected, home_more, ...},
                "odds_movement": {avg_opening_line, avg_closing_line, movement_signal, ...},
                "top_pick": str,
                "top_pick_probability": float,
                "confidence": float
            }
        }
    """
    try:
        # Extract corner odds
        corner_odds_info = extract_corner_odds_data(match_data)

        # Estimate lambda
        corner_lambda = estimate_corner_lambda(match_data, corner_odds_info)

        # Over/Under
        over_under = calculate_corner_over_under(corner_lambda)

        # Corner handicap
        handicap = calculate_corner_handicap(corner_lambda)

        # Most likely corner count
        most_likely = round(corner_lambda)
        most_likely_prob = poisson_probability(corner_lambda, most_likely)

        # Corner distribution (5-16)
        distribution = {}
        for k in range(5, 17):
            distribution[str(k)] = round(poisson_probability(corner_lambda, k) * 100, 2)

        # Top pick
        lines = {
            f'Korner Ust 9.5': over_under.get('over_9_5', 50),
            f'Korner Alt 9.5': over_under.get('under_9_5', 50),
            f'Korner Ust 10.5': over_under.get('over_10_5', 50),
            f'Korner Alt 10.5': over_under.get('under_10_5', 50),
            f'Korner Ust 11.5': over_under.get('over_11_5', 50),
            f'Korner Alt 11.5': over_under.get('under_11_5', 50),
        }
        top_pick_name = max(lines, key=lines.get)
        top_pick_prob = lines[top_pick_name]

        # Confidence
        has_odds = bool(corner_odds_info)
        companies = corner_odds_info.get('total_companies', 0)

        if companies >= 5:
            confidence = 75.0
        elif companies >= 3:
            confidence = 65.0
        elif has_odds:
            confidence = 55.0
        else:
            confidence = 45.0

        return {
            'corner_predictions': {
                'expected_total_corners': corner_lambda,
                'most_likely_count': most_likely,
                'most_likely_count_prob': round(most_likely_prob * 100, 1),
                'over_under': over_under,
                'corner_handicap': handicap,
                'corner_distribution': distribution,
                'odds_movement': corner_odds_info if corner_odds_info else None,
                'top_pick': top_pick_name,
                'top_pick_probability': top_pick_prob,
                'confidence': confidence,
            }
        }

    except Exception as e:
        logger.error(f"Corner prediction error: {e}")
        return {}
