"""
Enhanced Correct Score Prediction - Dixon-Coles Model
Combines independent Poisson with Dixon-Coles rho correction
for low-scoring games (0-0, 1-0, 0-1, 1-1).

Also merges bookmaker correct score odds for a hybrid model.

Key improvements over basic correct_score.py:
1. Dixon-Coles rho correction for score correlation
2. Poisson-based score probabilities (not just from bookmaker odds)
3. Hybrid model: Poisson (40%) + Bookmaker (60%) weighted average
4. Top 10 most likely scores with probabilities
5. Score group analysis (home win scores, draw scores, away win scores)

Reference: Dixon & Coles (1997) "Modelling Association Football Scores
and Inefficiencies in the Football Betting Market"
"""
import math
import logging
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)

# Dixon-Coles rho parameter: typically between -0.15 and 0.05
# Negative rho → draws (0-0, 1-1) are MORE likely than independent Poisson
# Empirically fitted value from major European leagues
DEFAULT_RHO = -0.13


def poisson_probability(lam, k):
    """P(X=k) for Poisson distribution."""
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    try:
        return (lam ** k) * math.exp(-lam) / math.factorial(k)
    except (OverflowError, ValueError):
        return 0.0


def dixon_coles_tau(home_goals, away_goals, home_lambda, away_lambda, rho):
    """
    Dixon-Coles tau correction function.
    Only modifies probabilities for (0,0), (0,1), (1,0), (1,1) scorelines.

    tau(x,y,lambda,mu,rho):
        (0,0): 1 - lambda * mu * rho
        (0,1): 1 + lambda * rho
        (1,0): 1 + mu * rho
        (1,1): 1 - rho
        else:  1.0
    """
    if home_goals == 0 and away_goals == 0:
        return 1.0 - (home_lambda * away_lambda * rho)
    elif home_goals == 0 and away_goals == 1:
        return 1.0 + (home_lambda * rho)
    elif home_goals == 1 and away_goals == 0:
        return 1.0 + (away_lambda * rho)
    elif home_goals == 1 and away_goals == 1:
        return 1.0 - rho
    else:
        return 1.0


def calculate_dixon_coles_score_probs(home_lambda, away_lambda, rho=DEFAULT_RHO, max_goals=8):
    """
    Calculate score probabilities using Dixon-Coles model.

    P(X=x, Y=y) = tau(x,y) * Poisson(x|lambda) * Poisson(y|mu)

    Returns dict of "x:y" -> probability
    """
    score_probs = {}
    total = 0.0

    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            p_home = poisson_probability(home_lambda, h)
            p_away = poisson_probability(away_lambda, a)
            tau = dixon_coles_tau(h, a, home_lambda, away_lambda, rho)

            prob = tau * p_home * p_away
            prob = max(0, prob)  # tau can make it negative in edge cases

            score_key = f"{h}:{a}"
            score_probs[score_key] = prob
            total += prob

    # Normalize to sum to 1
    if total > 0:
        for key in score_probs:
            score_probs[key] /= total

    return score_probs


def extract_lambdas_from_data(match_data: Dict) -> Optional[Tuple[float, float]]:
    """
    Extract home/away goal expectation (lambda) from existing Poisson analysis
    or calculate from H2H data.
    """
    # Try existing poisson predictions first
    poisson = match_data.get('analysis', {}).get('poisson_predictions', {})
    if poisson:
        xg = poisson.get('expected_goals', {})
        if xg.get('home') and xg.get('away'):
            return xg['home'], xg['away']

    # Fallback: calculate from h2h data
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

    # Calculate scoring rates
    home_scored = []
    home_conceded = []
    away_scored = []
    away_conceded = []

    for m in home_matches[:15]:
        try:
            hs, aws = int(m.get('home_score', 0)), int(m.get('away_score', 0))
            if m.get('home_team') == home_team:
                home_scored.append(hs)
                home_conceded.append(aws)
            elif m.get('away_team') == home_team:
                home_scored.append(aws)
                home_conceded.append(hs)
        except (ValueError, TypeError):
            continue

    for m in away_matches[:15]:
        try:
            hs, aws = int(m.get('home_score', 0)), int(m.get('away_score', 0))
            if m.get('home_team') == away_team:
                away_scored.append(hs)
                away_conceded.append(aws)
            elif m.get('away_team') == away_team:
                away_scored.append(aws)
                away_conceded.append(hs)
        except (ValueError, TypeError):
            continue

    if len(home_scored) < 3 or len(away_scored) < 3:
        return None

    league_avg = 1.3
    h_attack = sum(home_scored) / len(home_scored)
    h_defense = sum(home_conceded) / len(home_conceded)
    a_attack = sum(away_scored) / len(away_scored)
    a_defense = sum(away_conceded) / len(away_conceded)

    home_lambda = (h_attack / league_avg) * (a_defense / league_avg) * league_avg
    away_lambda = (a_attack / league_avg) * (h_defense / league_avg) * league_avg

    home_lambda = max(0.3, min(4.0, home_lambda))
    away_lambda = max(0.3, min(4.0, away_lambda))

    return home_lambda, away_lambda


def get_bookmaker_score_probs(match_data: Dict) -> Optional[Dict]:
    """
    Extract correct score probabilities from bookmaker odds.
    Uses the existing correct_score_odds data.
    """
    cs_data = match_data.get('correct_score_odds', {})
    if not cs_data:
        return None

    companies = cs_data.get('correct_score_odds', [])
    if not companies:
        return None

    # Collect odds from all valid companies and average
    all_probs = {}
    company_count = 0

    for company in companies:
        odds = company.get('odds', {})
        if not odds:
            continue

        has_valid = False
        for score_key, odds_str in odds.items():
            if odds_str and odds_str.strip():
                try:
                    o = float(odds_str)
                    if o > 1.0:
                        has_valid = True
                        prob = 1.0 / o
                        if score_key not in all_probs:
                            all_probs[score_key] = []
                        all_probs[score_key].append(prob)
                except (ValueError, ZeroDivisionError):
                    continue

        if has_valid:
            company_count += 1

    if not all_probs:
        return None

    # Average probabilities across bookmakers
    avg_probs = {}
    total = 0.0
    for score_key, probs in all_probs.items():
        avg = sum(probs) / len(probs)
        avg_probs[score_key] = avg
        total += avg

    # Normalize (remove bookmaker margin)
    if total > 0:
        for key in avg_probs:
            avg_probs[key] = avg_probs[key] / total

    return avg_probs


def merge_score_probabilities(dc_probs: Dict, bk_probs: Optional[Dict],
                               dc_weight: float = 0.40, bk_weight: float = 0.60) -> Dict:
    """
    Merge Dixon-Coles model probabilities with bookmaker probabilities.
    Bookmakers have more information (insider knowledge, market efficiency),
    so they get higher weight by default.
    """
    if not bk_probs:
        return dc_probs

    # Get all score keys from both sources
    all_keys = set(dc_probs.keys()) | set(bk_probs.keys())
    merged = {}
    total = 0.0

    for key in all_keys:
        dc_p = dc_probs.get(key, 0.0)
        bk_p = bk_probs.get(key, 0.0)

        # If only one source has this score, adjust weights
        if dc_p > 0 and bk_p > 0:
            merged_p = dc_weight * dc_p + bk_weight * bk_p
        elif bk_p > 0:
            merged_p = bk_p  # Only bookmaker has it
        else:
            merged_p = dc_p  # Only model has it

        merged[key] = merged_p
        total += merged_p

    # Normalize
    if total > 0:
        for key in merged:
            merged[key] /= total

    return merged


def get_top_scores(score_probs: Dict, n: int = 10) -> List[Dict]:
    """Get top N most likely scores."""
    sorted_scores = sorted(score_probs.items(), key=lambda x: x[1], reverse=True)
    return [
        {
            'score': score,
            'probability': round(prob * 100, 2),
            'home_goals': int(score.split(':')[0]) if ':' in score else 0,
            'away_goals': int(score.split(':')[1]) if ':' in score else 0,
        }
        for score, prob in sorted_scores[:n]
        if prob > 0.001  # Only include scores with >0.1% probability
    ]


def categorize_scores(score_probs: Dict) -> Dict:
    """
    Categorize scores by result type:
    - home_win_scores: all X:Y where X > Y
    - draw_scores: all X:Y where X == Y
    - away_win_scores: all X:Y where X < Y
    """
    home_win = {}
    draw = {}
    away_win = {}

    for score, prob in score_probs.items():
        if score == 'Other' or ':' not in score:
            continue
        try:
            h, a = map(int, score.split(':'))
            if h > a:
                home_win[score] = prob
            elif h == a:
                draw[score] = prob
            else:
                away_win[score] = prob
        except (ValueError, IndexError):
            continue

    return {
        'home_win_total': round(sum(home_win.values()) * 100, 1),
        'draw_total': round(sum(draw.values()) * 100, 1),
        'away_win_total': round(sum(away_win.values()) * 100, 1),
        'top_home_win': sorted(home_win.items(), key=lambda x: x[1], reverse=True)[:3],
        'top_draw': sorted(draw.items(), key=lambda x: x[1], reverse=True)[:3],
        'top_away_win': sorted(away_win.items(), key=lambda x: x[1], reverse=True)[:3],
    }


def analyze_correct_score_enhanced(match_data: Dict) -> Dict:
    """
    Main enhanced correct score prediction function.

    Returns:
        {
            "correct_score_enhanced": {
                "top_scores": [{"score": "1:0", "probability": 12.5}, ...],
                "score_categories": {...},
                "model_info": {rho, home_lambda, away_lambda, model_type},
                "goal_expectation": {home, away, total},
                "confidence": float
            }
        }
    """
    try:
        # 1. Get lambdas
        lambdas = extract_lambdas_from_data(match_data)
        if not lambdas:
            return {}

        home_lambda, away_lambda = lambdas

        # 2. Dixon-Coles score probabilities
        rho = DEFAULT_RHO
        dc_probs = calculate_dixon_coles_score_probs(home_lambda, away_lambda, rho)

        # 3. Bookmaker score probabilities
        bk_probs = get_bookmaker_score_probs(match_data)

        # 4. Merge probabilities
        if bk_probs:
            merged_probs = merge_score_probabilities(dc_probs, bk_probs, 0.40, 0.60)
            model_type = 'hybrid_dixon_coles_bookmaker'
        else:
            merged_probs = dc_probs
            model_type = 'dixon_coles_only'

        # 5. Top scores
        top_scores = get_top_scores(merged_probs, 10)

        # 6. Score categories
        categories = categorize_scores(merged_probs)

        # 7. Derived predictions (for compatibility with final_predictions)
        home_win_prob = categories['home_win_total']
        draw_prob = categories['draw_total']
        away_win_prob = categories['away_win_total']

        # Goal line probabilities from score distribution
        over_15 = 0
        over_25 = 0
        over_35 = 0
        btts_yes = 0

        for score, prob in merged_probs.items():
            if ':' not in score or score == 'Other':
                continue
            try:
                h, a = map(int, score.split(':'))
                total_g = h + a
                if total_g >= 2:
                    over_15 += prob
                if total_g >= 3:
                    over_25 += prob
                if total_g >= 4:
                    over_35 += prob
                if h > 0 and a > 0:
                    btts_yes += prob
            except (ValueError, IndexError):
                continue

        # Confidence
        h2h = match_data.get('h2h_details') or {}
        data_points = len(h2h.get('home_team_previous_matches', []))
        has_bk = bk_probs is not None

        if data_points >= 8 and has_bk:
            confidence = 75.0
        elif data_points >= 5 and has_bk:
            confidence = 70.0
        elif has_bk:
            confidence = 65.0
        elif data_points >= 8:
            confidence = 60.0
        else:
            confidence = 50.0

        return {
            'correct_score_enhanced': {
                'top_scores': top_scores,
                'score_categories': {
                    'home_win_prob': categories['home_win_total'],
                    'draw_prob': categories['draw_total'],
                    'away_win_prob': categories['away_win_total'],
                },
                'derived_predictions': {
                    '1x2': {
                        'home': round(home_win_prob, 1),
                        'draw': round(draw_prob, 1),
                        'away': round(away_win_prob, 1),
                    },
                    'goal_lines': {
                        'over_1_5': round(over_15 * 100, 1),
                        'under_1_5': round((1 - over_15) * 100, 1),
                        'over_2_5': round(over_25 * 100, 1),
                        'under_2_5': round((1 - over_25) * 100, 1),
                        'over_3_5': round(over_35 * 100, 1),
                        'under_3_5': round((1 - over_35) * 100, 1),
                    },
                    'btts': {
                        'yes': round(btts_yes * 100, 1),
                        'no': round((1 - btts_yes) * 100, 1),
                    },
                },
                'model_info': {
                    'rho': rho,
                    'home_lambda': round(home_lambda, 3),
                    'away_lambda': round(away_lambda, 3),
                    'model_type': model_type,
                    'has_bookmaker_data': has_bk,
                },
                'goal_expectation': {
                    'home': round(home_lambda, 2),
                    'away': round(away_lambda, 2),
                    'total': round(home_lambda + away_lambda, 2),
                },
                'confidence': confidence,
            }
        }

    except Exception as e:
        logger.error(f"Enhanced correct score error: {e}")
        return {}
