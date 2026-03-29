"""
Second Half Goal Predictions - 2Y (Ikinci Yari) Analysis
Derives second-half expectations from total and first-half models.

Key insight from research:
- Second half has ~55-58% of total goals
- Scoring rate accelerates after 60th minute
- Trailing teams become more aggressive in 2nd half
- Substitutions increase attacking intent

Features:
1. 2Y 0.5 Ust/Alt
2. 2Y 1.5 Ust/Alt
3. Which half has more goals?
4. Team 2Y performance differential (IY vs 2Y)
5. 2Y expected goals

Data sources:
- h2h_details: Full-time and HT scores → derive 2H by subtraction
- poisson_model: Total and HT lambdas
- team_performance: Historical performance
"""
import math
import logging
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Second half goal share (empirical)
SECOND_HALF_SHARE = 0.58  # ~58% of goals in 2nd half


def poisson_probability(lam, k):
    """P(X=k) for Poisson distribution."""
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    try:
        return (lam ** k) * math.exp(-lam) / math.factorial(k)
    except (OverflowError, ValueError):
        return 0.0


def extract_second_half_lambdas(match_data: Dict) -> Optional[Tuple[float, float, float, float]]:
    """
    Extract 2nd half lambdas.
    2H lambda = Total lambda - 1H lambda

    Returns: (sh_home_lambda, sh_away_lambda, fh_home_lambda, fh_away_lambda)
    """
    analysis = match_data.get('analysis', {})
    h2h = match_data.get('h2h_details') or {}
    match_info = match_data.get('match_info') or {}
    home_team = match_info.get('home_team_name', '')
    away_team = match_info.get('away_team_name', '')

    # Get total lambdas from Poisson
    poisson = analysis.get('poisson_predictions', {})
    xg = poisson.get('expected_goals', {})
    total_home = float(xg['home']) if xg.get('home') else None
    total_away = float(xg['away']) if xg.get('away') else None

    # Get HT lambdas from H2H
    h2h_analysis = analysis.get('h2h_analysis', {})
    h2h_avg = h2h_analysis.get('avg_goals', {})
    ht_home = float(h2h_avg['ht_home_team_avg_goals']) if h2h_avg.get('ht_home_team_avg_goals') else None
    ht_away = float(h2h_avg['ht_away_team_avg_goals']) if h2h_avg.get('ht_away_team_avg_goals') else None

    # If we have both total and HT, derive 2H
    if total_home and total_away and ht_home is not None and ht_away is not None:
        sh_home = max(0.15, total_home - ht_home)
        sh_away = max(0.15, total_away - ht_away)
        return sh_home, sh_away, ht_home, ht_away

    # Fallback: calculate from match history
    if not home_team or not away_team:
        return None

    home_matches = h2h.get('home_team_previous_matches') or []
    away_matches = h2h.get('away_team_previous_matches') or []

    fh_home_goals, fh_away_goals = 0, 0
    sh_home_goals, sh_away_goals = 0, 0
    home_count, away_count = 0, 0

    for m in home_matches[:10]:
        try:
            score = m.get('score', '0-0')
            ht_score = m.get('ht_score', '')
            if not ht_score or '-' not in ht_score:
                continue

            ft_h, ft_a = map(int, score.split('-'))
            ht_h, ht_a = map(int, ht_score.split('-'))

            is_home = m.get('home_team') == home_team
            if is_home:
                fh_home_goals += ht_h
                sh_home_goals += (ft_h - ht_h)
            else:
                fh_home_goals += ht_a
                sh_home_goals += (ft_a - ht_a)
            home_count += 1
        except (ValueError, IndexError):
            continue

    for m in away_matches[:10]:
        try:
            score = m.get('score', '0-0')
            ht_score = m.get('ht_score', '')
            if not ht_score or '-' not in ht_score:
                continue

            ft_h, ft_a = map(int, score.split('-'))
            ht_h, ht_a = map(int, ht_score.split('-'))

            is_home = m.get('home_team') == away_team
            if is_home:
                fh_away_goals += ht_h
                sh_away_goals += (ft_h - ht_h)
            else:
                fh_away_goals += ht_a
                sh_away_goals += (ft_a - ht_a)
            away_count += 1
        except (ValueError, IndexError):
            continue

    if home_count < 3 or away_count < 3:
        # Final fallback: use SECOND_HALF_SHARE of total
        if total_home and total_away:
            fh_h = total_home * (1 - SECOND_HALF_SHARE)
            fh_a = total_away * (1 - SECOND_HALF_SHARE)
            sh_h = total_home * SECOND_HALF_SHARE
            sh_a = total_away * SECOND_HALF_SHARE
            return sh_h, sh_a, fh_h, fh_a
        return None

    fh_h_avg = fh_home_goals / home_count
    fh_a_avg = fh_away_goals / away_count
    sh_h_avg = max(0.15, sh_home_goals / home_count)
    sh_a_avg = max(0.15, sh_away_goals / away_count)

    return sh_h_avg, sh_a_avg, fh_h_avg, fh_a_avg


def calculate_sh_over_under(sh_home_lambda, sh_away_lambda) -> Dict:
    """Calculate second half over/under probabilities."""
    max_goals = 6
    home_probs = [poisson_probability(sh_home_lambda, k) for k in range(max_goals + 1)]
    away_probs = [poisson_probability(sh_away_lambda, k) for k in range(max_goals + 1)]

    # Over/Under 0.5
    prob_0_0 = home_probs[0] * away_probs[0]
    over_05 = 1.0 - prob_0_0

    # Over/Under 1.5
    prob_under_15 = 0.0
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            if h + a < 2:
                prob_under_15 += home_probs[h] * away_probs[a]
    over_15 = 1.0 - prob_under_15

    # Over/Under 2.5
    prob_under_25 = 0.0
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            if h + a < 3:
                prob_under_25 += home_probs[h] * away_probs[a]
    over_25 = 1.0 - prob_under_25

    return {
        'over_0_5': round(over_05 * 100, 1),
        'under_0_5': round((1 - over_05) * 100, 1),
        'over_1_5': round(over_15 * 100, 1),
        'under_1_5': round((1 - over_15) * 100, 1),
        'over_2_5': round(over_25 * 100, 1),
        'under_2_5': round((1 - over_25) * 100, 1),
    }


def calculate_which_half_more_goals(fh_home, fh_away, sh_home, sh_away) -> Dict:
    """
    Calculate probability of which half has more goals.
    Uses convolution of Poisson distributions.
    """
    max_goals = 6

    fh_total_lambda = fh_home + fh_away
    sh_total_lambda = sh_home + sh_away

    # Calculate P(FH total = k) and P(SH total = k)
    fh_probs = {}
    sh_probs = {}

    for total_g in range(max_goals * 2 + 1):
        fh_p = 0
        sh_p = 0
        for h in range(min(total_g, max_goals) + 1):
            a = total_g - h
            if a <= max_goals:
                fh_p += poisson_probability(fh_home, h) * poisson_probability(fh_away, a)
                sh_p += poisson_probability(sh_home, h) * poisson_probability(sh_away, a)
        fh_probs[total_g] = fh_p
        sh_probs[total_g] = sh_p

    # P(1st half more) vs P(2nd half more) vs P(equal)
    p_first_more = 0
    p_second_more = 0
    p_equal = 0

    for fh_g in range(max_goals * 2 + 1):
        for sh_g in range(max_goals * 2 + 1):
            joint = fh_probs.get(fh_g, 0) * sh_probs.get(sh_g, 0)
            if fh_g > sh_g:
                p_first_more += joint
            elif sh_g > fh_g:
                p_second_more += joint
            else:
                p_equal += joint

    total = p_first_more + p_second_more + p_equal
    if total > 0:
        p_first_more /= total
        p_second_more /= total
        p_equal /= total

    return {
        'first_half_more': round(p_first_more * 100, 1),
        'second_half_more': round(p_second_more * 100, 1),
        'equal_goals': round(p_equal * 100, 1),
    }


def calculate_team_half_performance(match_data: Dict) -> Dict:
    """
    Calculate each team's IY vs 2Y goal scoring differential.
    Identifies teams that are 'first half teams' vs 'second half teams'.
    """
    h2h = match_data.get('h2h_details') or {}
    match_info = match_data.get('match_info') or {}
    home_team = match_info.get('home_team_name', '')
    away_team = match_info.get('away_team_name', '')

    result = {
        'home_team': {'fh_goals': 0, 'sh_goals': 0, 'matches': 0, 'profile': 'balanced'},
        'away_team': {'fh_goals': 0, 'sh_goals': 0, 'matches': 0, 'profile': 'balanced'},
    }

    for team_key, matches_key, team_name in [
        ('home_team', 'home_team_previous_matches', home_team),
        ('away_team', 'away_team_previous_matches', away_team),
    ]:
        matches = h2h.get(matches_key, [])
        for m in matches[:10]:
            try:
                score = m.get('score', '0-0')
                ht_score = m.get('ht_score', '')
                if not ht_score or '-' not in ht_score:
                    continue

                ft_h, ft_a = map(int, score.split('-'))
                ht_h, ht_a = map(int, ht_score.split('-'))

                is_home = m.get('home_team') == team_name
                if is_home:
                    fh_g = ht_h
                    sh_g = ft_h - ht_h
                else:
                    fh_g = ht_a
                    sh_g = ft_a - ht_a

                result[team_key]['fh_goals'] += fh_g
                result[team_key]['sh_goals'] += max(0, sh_g)
                result[team_key]['matches'] += 1
            except (ValueError, IndexError):
                continue

        # Determine profile
        n = result[team_key]['matches']
        if n >= 3:
            fh_avg = result[team_key]['fh_goals'] / n
            sh_avg = result[team_key]['sh_goals'] / n
            result[team_key]['fh_avg'] = round(fh_avg, 2)
            result[team_key]['sh_avg'] = round(sh_avg, 2)

            if sh_avg > fh_avg * 1.3:
                result[team_key]['profile'] = 'second_half_team'
            elif fh_avg > sh_avg * 1.3:
                result[team_key]['profile'] = 'first_half_team'
            else:
                result[team_key]['profile'] = 'balanced'

    return result


def analyze_second_half_predictions(match_data: Dict) -> Dict:
    """
    Main second half prediction function.

    Returns:
        {
            "second_half_predictions": {
                "sh_over_under": {over_0_5, under_0_5, over_1_5, under_1_5, over_2_5, under_2_5},
                "which_half_more_goals": {first_half_more, second_half_more, equal_goals},
                "sh_expected_goals": {home, away, total},
                "team_half_performance": {...},
                "top_pick": str,
                "top_pick_probability": float,
                "confidence": float
            }
        }
    """
    try:
        lambdas = extract_second_half_lambdas(match_data)
        if not lambdas:
            return {}

        sh_home, sh_away, fh_home, fh_away = lambdas

        # Over/Under
        over_under = calculate_sh_over_under(sh_home, sh_away)

        # Which half more goals
        which_half = calculate_which_half_more_goals(fh_home, fh_away, sh_home, sh_away)

        # Team performance differential
        team_perf = calculate_team_half_performance(match_data)

        # Expected goals
        sh_xg = {
            'home': round(sh_home, 2),
            'away': round(sh_away, 2),
            'total': round(sh_home + sh_away, 2),
        }

        fh_xg = {
            'home': round(fh_home, 2),
            'away': round(fh_away, 2),
            'total': round(fh_home + fh_away, 2),
        }

        # Top pick
        picks = {
            '2Y Ust 0.5': over_under['over_0_5'],
            '2Y Alt 0.5': over_under['under_0_5'],
            '2Y Ust 1.5': over_under['over_1_5'],
            '2Y Alt 1.5': over_under['under_1_5'],
        }
        top_pick = max(picks, key=picks.get)
        top_prob = picks[top_pick]

        # Confidence
        h2h = match_data.get('h2h_details') or {}
        data_points = len(h2h.get('home_team_previous_matches', []))
        has_ht_data = team_perf['home_team']['matches'] >= 5

        if data_points >= 8 and has_ht_data:
            confidence = 70.0
        elif data_points >= 5:
            confidence = 60.0
        else:
            confidence = 48.0

        return {
            'second_half_predictions': {
                'sh_over_under': over_under,
                'which_half_more_goals': which_half,
                'sh_expected_goals': sh_xg,
                'fh_expected_goals': fh_xg,
                'team_half_performance': team_perf,
                'top_pick': top_pick,
                'top_pick_probability': top_prob,
                'confidence': confidence,
            }
        }

    except Exception as e:
        logger.error(f"Second half prediction error: {e}")
        return {}
