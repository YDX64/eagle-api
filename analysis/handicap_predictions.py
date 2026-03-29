"""
Handicap Prediction Algorithm - Asian & European Handicap Analysis
Uses Poisson goal distribution to calculate handicap cover probabilities
and detects value bets by comparing model vs bookmaker odds.

Features:
1. Asian handicap probabilities for all standard lines
2. European handicap probabilities
3. Value bet detection (model prob vs bookmaker implied prob)
4. Kelly criterion sizing for value bets
5. Handicap direction recommendation

Data sources:
- Poisson model lambdas (from existing analysis)
- odds_comp: Bookmaker AH odds for value detection
- h2h_details: Historical match data for lambda estimation
"""
import math
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def poisson_probability(lam, k):
    """P(X=k) for Poisson distribution."""
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    try:
        return (lam ** k) * math.exp(-lam) / math.factorial(k)
    except (OverflowError, ValueError):
        return 0.0


def extract_lambdas(match_data: Dict) -> Optional[Tuple[float, float]]:
    """Extract goal expectation lambdas from analysis data."""
    # Try existing poisson predictions
    analysis = match_data.get('analysis', {})
    poisson = analysis.get('poisson_predictions', {})
    if poisson:
        xg = poisson.get('expected_goals', {})
        if xg.get('home') and xg.get('away'):
            return xg['home'], xg['away']

    # Fallback: calculate from h2h
    h2h = match_data.get('h2h_details') or {}
    match_info = match_data.get('match_info') or {}
    home_team = match_info.get('home_team_name', '')
    away_team = match_info.get('away_team_name', '')

    if not home_team or not away_team:
        return None

    home_matches = h2h.get('home_team_previous_matches', [])
    away_matches = h2h.get('away_team_previous_matches', [])

    if len(home_matches) < 3 or len(away_matches) < 3:
        return None

    home_scored, home_conceded, away_scored, away_conceded = [], [], [], []

    for m in home_matches[:15]:
        try:
            hs, aws = int(m.get('home_score', 0)), int(m.get('away_score', 0))
            if m.get('home_team') == home_team:
                home_scored.append(hs); home_conceded.append(aws)
            elif m.get('away_team') == home_team:
                home_scored.append(aws); home_conceded.append(hs)
        except (ValueError, TypeError):
            continue

    for m in away_matches[:15]:
        try:
            hs, aws = int(m.get('home_score', 0)), int(m.get('away_score', 0))
            if m.get('home_team') == away_team:
                away_scored.append(hs); away_conceded.append(aws)
            elif m.get('away_team') == away_team:
                away_scored.append(aws); away_conceded.append(hs)
        except (ValueError, TypeError):
            continue

    if len(home_scored) < 3 or len(away_scored) < 3:
        return None

    league_avg = 1.3
    h_att = sum(home_scored) / len(home_scored)
    h_def = sum(home_conceded) / len(home_conceded)
    a_att = sum(away_scored) / len(away_scored)
    a_def = sum(away_conceded) / len(away_conceded)

    home_l = max(0.3, min(4.0, (h_att / league_avg) * (a_def / league_avg) * league_avg))
    away_l = max(0.3, min(4.0, (a_att / league_avg) * (h_def / league_avg) * league_avg))

    return home_l, away_l


def calculate_score_distribution(home_lambda, away_lambda, max_goals=8):
    """Calculate joint score probability distribution."""
    dist = {}
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            dist[(h, a)] = poisson_probability(home_lambda, h) * poisson_probability(away_lambda, a)
    return dist


def calculate_asian_handicap_probs(score_dist: Dict, line: float) -> Dict:
    """
    Calculate Asian handicap probabilities.

    AH works on goal difference (home - away):
    - AH -1.5: Home must win by 2+ goals
    - AH -0.5: Home must win (no draw push)
    - AH +0.5: Home doesn't lose (draw = win)
    - AH +1.5: Home doesn't lose by 2+ goals

    For whole number lines (e.g., -1):
    - Home wins by exactly 1: push (money returned)
    - Home wins by 2+: win
    - Draw or away win: lose

    For quarter lines (e.g., -0.25 = split between 0 and -0.5):
    - Half the bet on 0, half on -0.5
    """
    home_cover = 0.0
    push = 0.0
    away_cover = 0.0

    for (h, a), prob in score_dist.items():
        diff = h - a  # Goal difference from home perspective

        adjusted_diff = diff + line  # Add the handicap line

        if abs(adjusted_diff) < 0.001:  # Push (whole number lines)
            push += prob
        elif adjusted_diff > 0:
            home_cover += prob
        else:
            away_cover += prob

    return {
        'home_cover': round(home_cover * 100, 1),
        'push': round(push * 100, 1),
        'away_cover': round(away_cover * 100, 1),
    }


def calculate_european_handicap_probs(score_dist: Dict, line: int) -> Dict:
    """
    Calculate European (3-way) handicap probabilities.
    European handicap has three outcomes: home win, draw, away win.

    E.g., European -1:
    - Home wins by 2+: Home win
    - Home wins by exactly 1: Draw
    - Draw or away win: Away win
    """
    home_win = 0.0
    draw = 0.0
    away_win = 0.0

    for (h, a), prob in score_dist.items():
        adjusted_h = h + line  # Apply handicap to home score
        if adjusted_h > a:
            home_win += prob
        elif adjusted_h == a:
            draw += prob
        else:
            away_win += prob

    return {
        'home': round(home_win * 100, 1),
        'draw': round(draw * 100, 1),
        'away': round(away_win * 100, 1),
    }


def extract_bookmaker_ah_odds(match_data: Dict) -> Dict:
    """Extract average AH odds from bookmakers for value comparison."""
    odds_comp = match_data.get('odds_comp') or {}
    odds_list = odds_comp.get('odds_comparison', [])

    ah_data = {}

    for company in odds_list:
        ah = company.get('asian_handicap', {})
        pre = ah.get('pre_match_odds', {})

        line = pre.get('line')
        home_odds = pre.get('home')
        away_odds = pre.get('away')

        if line is not None and home_odds and away_odds:
            try:
                l = float(line)
                ho = float(home_odds)
                ao = float(away_odds)
                if ho > 1.0 and ao > 1.0:
                    if l not in ah_data:
                        ah_data[l] = {'home_odds': [], 'away_odds': []}
                    ah_data[l]['home_odds'].append(ho)
                    ah_data[l]['away_odds'].append(ao)
            except (ValueError, TypeError):
                continue

    # Average odds per line
    result = {}
    for line, odds in ah_data.items():
        result[line] = {
            'home_odds': round(sum(odds['home_odds']) / len(odds['home_odds']), 3),
            'away_odds': round(sum(odds['away_odds']) / len(odds['away_odds']), 3),
            'bookmaker_count': len(odds['home_odds']),
        }

    return result


def calculate_kelly_criterion(model_prob: float, odds: float, fraction: float = 0.25) -> Dict:
    """
    Calculate Kelly criterion bet size.

    f* = (bp - q) / b
    where b = odds - 1, p = model probability, q = 1 - p

    fraction: Use fractional Kelly (default 25%) for safety.
    """
    if model_prob <= 0 or model_prob >= 1 or odds <= 1:
        return {'kelly': 0, 'edge': 0, 'is_value': False}

    b = odds - 1
    p = model_prob
    q = 1 - p

    full_kelly = (b * p - q) / b
    edge = (model_prob * odds) - 1  # Expected value per unit

    fractional_kelly = max(0, full_kelly * fraction)

    return {
        'kelly': round(fractional_kelly * 100, 2),  # As percentage of bankroll
        'full_kelly': round(full_kelly * 100, 2),
        'edge': round(edge * 100, 2),  # Edge in percentage
        'is_value': edge > 0,
        'expected_value': round(edge * 100, 1),  # EV per 100 units
    }


def detect_value_bets(score_dist: Dict, bookmaker_ah: Dict) -> List[Dict]:
    """
    Compare model probabilities vs bookmaker odds to find value.
    """
    value_bets = []

    for line, bk_odds in bookmaker_ah.items():
        ah_probs = calculate_asian_handicap_probs(score_dist, line)

        # Model probability vs bookmaker implied probability
        home_model_prob = (ah_probs['home_cover'] + ah_probs['push'] * 0.5) / 100
        away_model_prob = (ah_probs['away_cover'] + ah_probs['push'] * 0.5) / 100

        home_implied = 1.0 / bk_odds['home_odds'] if bk_odds['home_odds'] > 1 else 0
        away_implied = 1.0 / bk_odds['away_odds'] if bk_odds['away_odds'] > 1 else 0

        # Check home value
        home_kelly = calculate_kelly_criterion(home_model_prob, bk_odds['home_odds'])
        if home_kelly['is_value'] and home_kelly['edge'] > 2:  # >2% edge minimum
            value_bets.append({
                'line': line,
                'side': 'home',
                'model_prob': round(home_model_prob * 100, 1),
                'implied_prob': round(home_implied * 100, 1),
                'odds': bk_odds['home_odds'],
                'edge_pct': home_kelly['edge'],
                'kelly_pct': home_kelly['kelly'],
                'bookmaker_count': bk_odds['bookmaker_count'],
            })

        # Check away value
        away_kelly = calculate_kelly_criterion(away_model_prob, bk_odds['away_odds'])
        if away_kelly['is_value'] and away_kelly['edge'] > 2:
            value_bets.append({
                'line': line,
                'side': 'away',
                'model_prob': round(away_model_prob * 100, 1),
                'implied_prob': round(away_implied * 100, 1),
                'odds': bk_odds['away_odds'],
                'edge_pct': away_kelly['edge'],
                'kelly_pct': away_kelly['kelly'],
                'bookmaker_count': bk_odds['bookmaker_count'],
            })

    # Sort by edge (highest first)
    value_bets.sort(key=lambda x: x['edge_pct'], reverse=True)
    return value_bets


def analyze_handicap_predictions(match_data: Dict) -> Dict:
    """
    Main handicap prediction function.

    Returns:
        {
            "handicap_predictions": {
                "asian_handicap": {line: {home_cover, push, away_cover}, ...},
                "european_handicap": {line: {home, draw, away}, ...},
                "recommended_line": float,
                "recommended_side": str,
                "value_bets": [...],
                "goal_difference_expected": float,
                "confidence": float
            }
        }
    """
    try:
        lambdas = extract_lambdas(match_data)
        if not lambdas:
            return {}

        home_lambda, away_lambda = lambdas

        # Score distribution
        score_dist = calculate_score_distribution(home_lambda, away_lambda)

        # Asian handicap for standard lines
        ah_lines = [-2.5, -1.5, -1.0, -0.5, 0, 0.5, 1.0, 1.5, 2.5]
        asian_handicap = {}
        for line in ah_lines:
            asian_handicap[str(line)] = calculate_asian_handicap_probs(score_dist, line)

        # European handicap for standard lines
        eh_lines = [-2, -1, 0, 1, 2]
        european_handicap = {}
        for line in eh_lines:
            european_handicap[str(line)] = calculate_european_handicap_probs(score_dist, line)

        # Expected goal difference
        expected_diff = home_lambda - away_lambda

        # Recommended AH line (closest to expected difference)
        recommended_line = round(expected_diff * 2) / 2  # Round to 0.5
        recommended_line = max(-2.5, min(2.5, recommended_line))

        # Get bookmaker AH odds and find value bets
        bookmaker_ah = extract_bookmaker_ah_odds(match_data)
        value_bets = detect_value_bets(score_dist, bookmaker_ah) if bookmaker_ah else []

        # Recommended side for the main bookmaker line
        rec_line_str = str(recommended_line)
        if rec_line_str in asian_handicap:
            rec_probs = asian_handicap[rec_line_str]
            if rec_probs['home_cover'] > rec_probs['away_cover']:
                recommended_side = 'home'
                recommended_prob = rec_probs['home_cover']
            else:
                recommended_side = 'away'
                recommended_prob = rec_probs['away_cover']
        else:
            recommended_side = 'home' if expected_diff > 0 else 'away'
            recommended_prob = 55.0

        # Best value bet as top pick
        top_pick = None
        if value_bets:
            vb = value_bets[0]
            top_pick = f"AH {vb['line']} {vb['side'].upper()} (Edge: {vb['edge_pct']}%)"

        # Confidence
        h2h = match_data.get('h2h_details') or {}
        data_points = len(h2h.get('home_team_previous_matches', []))
        has_odds = bool(bookmaker_ah)

        if data_points >= 8 and has_odds:
            confidence = 72.0
        elif data_points >= 5 and has_odds:
            confidence = 65.0
        elif data_points >= 5:
            confidence = 58.0
        else:
            confidence = 48.0

        return {
            'handicap_predictions': {
                'asian_handicap': asian_handicap,
                'european_handicap': european_handicap,
                'recommended_line': recommended_line,
                'recommended_side': recommended_side,
                'recommended_prob': recommended_prob,
                'goal_difference_expected': round(expected_diff, 2),
                'value_bets': value_bets[:5],  # Top 5 value bets
                'top_pick': top_pick,
                'model_info': {
                    'home_lambda': round(home_lambda, 3),
                    'away_lambda': round(away_lambda, 3),
                    'bookmaker_lines_available': len(bookmaker_ah),
                },
                'confidence': confidence,
            }
        }

    except Exception as e:
        logger.error(f"Handicap prediction error: {e}")
        return {}
