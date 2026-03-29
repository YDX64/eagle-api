"""
Half-Based BTTS (Both Teams To Score) Prediction
Predicts BTTS for each half separately and combined.

This is a HIGH-VALUE market because bookmakers offer high odds
for half-specific BTTS, making it attractive for bettors.

Markets:
1. IY KG Var/Yok (First half BTTS yes/no)
2. 2Y KG Var/Yok (Second half BTTS yes/no)
3. Hangi yarida KG olur? (Which half has BTTS)
4. Her iki yarida da KG Var (Both halves BTTS - very high odds)
5. Sadece bir yarida KG Var (Exactly one half BTTS)
6. Hicbir yarida KG yok (No half BTTS)

Mathematical basis:
P(BTTS in half) = P(home scores in half) * P(away scores in half)
P(team scores in half) = 1 - P(Poisson=0) = 1 - e^(-lambda)

Data sources:
- h2h_details: HT scores, full-time scores → derive per-half scoring
- poisson_model: Lambdas
- first_half_odds: Bookmaker HT data
"""
import math
import logging
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


def poisson_probability(lam, k):
    """P(X=k) for Poisson distribution."""
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    try:
        return (lam ** k) * math.exp(-lam) / math.factorial(k)
    except (OverflowError, ValueError):
        return 0.0


def extract_half_lambdas(match_data: Dict) -> Optional[Dict]:
    """
    Extract per-half, per-team lambdas.

    Returns: {
        'fh_home': float, 'fh_away': float,
        'sh_home': float, 'sh_away': float,
        'total_home': float, 'total_away': float,
    }
    """
    analysis = match_data.get('analysis', {})
    h2h = match_data.get('h2h_details') or {}
    match_info = match_data.get('match_info') or {}
    home_team = match_info.get('home_team_name', '')
    away_team = match_info.get('away_team_name', '')

    # Total lambdas from Poisson
    poisson = analysis.get('poisson_predictions', {})
    xg = poisson.get('expected_goals', {})
    total_home = float(xg['home']) if xg.get('home') else None
    total_away = float(xg['away']) if xg.get('away') else None

    # HT lambdas from H2H
    h2h_analysis = analysis.get('h2h_analysis', {})
    h2h_avg = h2h_analysis.get('avg_goals', {})
    ht_home = float(h2h_avg['ht_home_team_avg_goals']) if h2h_avg.get('ht_home_team_avg_goals') else None
    ht_away = float(h2h_avg['ht_away_team_avg_goals']) if h2h_avg.get('ht_away_team_avg_goals') else None

    # Calculate from match history if needed
    if ht_home is None or ht_away is None:
        ht_home, ht_away = _calculate_ht_from_matches(h2h, home_team, away_team)

    if total_home is None or total_away is None:
        # Try to calculate total from match history
        total_home, total_away = _calculate_total_from_matches(h2h, home_team, away_team)

    if total_home is None or total_away is None:
        return None

    if ht_home is None or ht_away is None:
        # Fallback: use standard 42% share
        ht_home = total_home * 0.42
        ht_away = total_away * 0.42

    # Derive second half
    sh_home = max(0.10, total_home - ht_home)
    sh_away = max(0.10, total_away - ht_away)

    return {
        'fh_home': max(0.10, ht_home),
        'fh_away': max(0.10, ht_away),
        'sh_home': sh_home,
        'sh_away': sh_away,
        'total_home': total_home,
        'total_away': total_away,
    }


def _calculate_ht_from_matches(h2h: Dict, home_team: str, away_team: str) -> Tuple:
    """Calculate HT lambdas from match history."""
    home_ht_g, away_ht_g, h_count, a_count = 0, 0, 0, 0

    for m in (h2h.get('home_team_previous_matches') or [])[:10]:
        ht = m.get('ht_score', '')
        if not ht or '-' not in ht:
            continue
        try:
            ht_h, ht_a = map(int, ht.split('-'))
            if m.get('home_team') == home_team:
                home_ht_g += ht_h
            else:
                home_ht_g += ht_a
            h_count += 1
        except (ValueError, IndexError):
            continue

    for m in (h2h.get('away_team_previous_matches') or [])[:10]:
        ht = m.get('ht_score', '')
        if not ht or '-' not in ht:
            continue
        try:
            ht_h, ht_a = map(int, ht.split('-'))
            if m.get('home_team') == away_team:
                away_ht_g += ht_h
            else:
                away_ht_g += ht_a
            a_count += 1
        except (ValueError, IndexError):
            continue

    ht_home = (home_ht_g / h_count) if h_count >= 3 else None
    ht_away = (away_ht_g / a_count) if a_count >= 3 else None
    return ht_home, ht_away


def _calculate_total_from_matches(h2h: Dict, home_team: str, away_team: str) -> Tuple:
    """Calculate total lambdas from match history."""
    home_g, home_c, away_g, away_c = [], [], [], []

    for m in (h2h.get('home_team_previous_matches') or [])[:15]:
        try:
            hs, aws = int(m.get('home_score', 0)), int(m.get('away_score', 0))
            if m.get('home_team') == home_team:
                home_g.append(hs); home_c.append(aws)
            elif m.get('away_team') == home_team:
                home_g.append(aws); home_c.append(hs)
        except (ValueError, TypeError):
            continue

    for m in (h2h.get('away_team_previous_matches') or [])[:15]:
        try:
            hs, aws = int(m.get('home_score', 0)), int(m.get('away_score', 0))
            if m.get('home_team') == away_team:
                away_g.append(hs); away_c.append(aws)
            elif m.get('away_team') == away_team:
                away_g.append(aws); away_c.append(hs)
        except (ValueError, TypeError):
            continue

    if len(home_g) < 3 or len(away_g) < 3:
        return None, None

    avg = 1.3
    h_a = sum(home_g) / len(home_g)
    h_d = sum(home_c) / len(home_c)
    a_a = sum(away_g) / len(away_g)
    a_d = sum(away_c) / len(away_c)

    home_l = max(0.3, min(4.0, (h_a / avg) * (a_d / avg) * avg))
    away_l = max(0.3, min(4.0, (a_a / avg) * (h_d / avg) * avg))
    return home_l, away_l


def calculate_half_btts(lambdas: Dict) -> Dict:
    """
    Calculate BTTS probabilities for each half.

    P(BTTS in half) = P(home scores) * P(away scores)
    P(team scores) = 1 - P(Poisson=0) = 1 - e^(-lambda)
    """
    fh_home_scores = 1.0 - poisson_probability(lambdas['fh_home'], 0)
    fh_away_scores = 1.0 - poisson_probability(lambdas['fh_away'], 0)
    sh_home_scores = 1.0 - poisson_probability(lambdas['sh_home'], 0)
    sh_away_scores = 1.0 - poisson_probability(lambdas['sh_away'], 0)

    fh_btts = fh_home_scores * fh_away_scores
    sh_btts = sh_home_scores * sh_away_scores

    return {
        'fh_btts_yes': fh_btts,
        'fh_btts_no': 1.0 - fh_btts,
        'sh_btts_yes': sh_btts,
        'sh_btts_no': 1.0 - sh_btts,
        'fh_home_scores': fh_home_scores,
        'fh_away_scores': fh_away_scores,
        'sh_home_scores': sh_home_scores,
        'sh_away_scores': sh_away_scores,
    }


def calculate_btts_combinations(half_btts: Dict) -> Dict:
    """
    Calculate all BTTS combinations across halves.

    Assumes independence between halves (simplification).

    Combinations:
    1. Both halves BTTS = P(FH BTTS) * P(SH BTTS)
    2. Only FH BTTS = P(FH BTTS) * P(NOT SH BTTS)
    3. Only SH BTTS = P(NOT FH BTTS) * P(SH BTTS)
    4. No half BTTS = P(NOT FH BTTS) * P(NOT SH BTTS)
    5. At least one half BTTS = 1 - P(no half BTTS)
    6. Exactly one half BTTS = P(only FH) + P(only SH)
    """
    fh_yes = half_btts['fh_btts_yes']
    fh_no = half_btts['fh_btts_no']
    sh_yes = half_btts['sh_btts_yes']
    sh_no = half_btts['sh_btts_no']

    both_halves = fh_yes * sh_yes
    only_fh = fh_yes * sh_no
    only_sh = fh_no * sh_yes
    no_half = fh_no * sh_no
    at_least_one = 1.0 - no_half
    exactly_one = only_fh + only_sh

    return {
        'both_halves_btts': round(both_halves * 100, 1),
        'only_first_half_btts': round(only_fh * 100, 1),
        'only_second_half_btts': round(only_sh * 100, 1),
        'no_half_btts': round(no_half * 100, 1),
        'at_least_one_half_btts': round(at_least_one * 100, 1),
        'exactly_one_half_btts': round(exactly_one * 100, 1),
    }


def calculate_which_half_btts(half_btts: Dict) -> Dict:
    """Determine which half is more likely to have BTTS."""
    fh = half_btts['fh_btts_yes']
    sh = half_btts['sh_btts_yes']

    if sh > fh * 1.1:
        prediction = '2Y KG Var'
        reason = 'Ikinci yaridaki gol beklentisi daha yuksek'
    elif fh > sh * 1.1:
        prediction = 'IY KG Var'
        reason = 'Ilk yaridaki takim gol atma olasiliklarinin carpimi daha yuksek'
    else:
        prediction = 'Dengeli'
        reason = 'Her iki yarida da benzer KG olasiligi'

    return {
        'prediction': prediction,
        'reason': reason,
        'fh_btts_prob': round(fh * 100, 1),
        'sh_btts_prob': round(sh * 100, 1),
        'difference': round(abs(fh - sh) * 100, 1),
    }


def get_btts_trends_from_h2h(match_data: Dict) -> Dict:
    """Extract historical BTTS per half from H2H data."""
    h2h = match_data.get('h2h_details') or {}
    match_info = match_data.get('match_info') or {}
    home_team = match_info.get('home_team_name', '')

    fh_btts_count, sh_btts_count, both_btts_count, total = 0, 0, 0, 0

    # Check home team's recent matches
    for m in (h2h.get('home_team_previous_matches') or [])[:10]:
        try:
            score = m.get('score', '0-0')
            ht_score = m.get('ht_score', '')
            if not ht_score or '-' not in ht_score:
                continue

            ft_h, ft_a = map(int, score.split('-'))
            ht_h, ht_a = map(int, ht_score.split('-'))
            sh_h = ft_h - ht_h
            sh_a = ft_a - ht_a

            total += 1

            fh_btts = ht_h > 0 and ht_a > 0
            sh_btts = sh_h > 0 and sh_a > 0

            if fh_btts:
                fh_btts_count += 1
            if sh_btts:
                sh_btts_count += 1
            if fh_btts and sh_btts:
                both_btts_count += 1
        except (ValueError, IndexError):
            continue

    return {
        'fh_btts_rate': round(fh_btts_count / total * 100, 1) if total > 0 else 0,
        'sh_btts_rate': round(sh_btts_count / total * 100, 1) if total > 0 else 0,
        'both_halves_btts_rate': round(both_btts_count / total * 100, 1) if total > 0 else 0,
        'matches_analyzed': total,
    }


def analyze_half_btts_predictions(match_data: Dict) -> Dict:
    """
    Main half-based BTTS prediction function.

    Returns:
        {
            "half_btts_predictions": {
                "first_half_btts": {yes, no},
                "second_half_btts": {yes, no},
                "combinations": {both_halves, only_fh, only_sh, no_half, ...},
                "which_half_btts": {prediction, reason, ...},
                "team_scoring_by_half": {...},
                "historical_trends": {...},
                "top_pick": str,
                "top_pick_probability": float,
                "confidence": float
            }
        }
    """
    try:
        lambdas = extract_half_lambdas(match_data)
        if not lambdas:
            return {}

        # Half BTTS probabilities
        half_btts = calculate_half_btts(lambdas)

        # Combinations
        combinations = calculate_btts_combinations(half_btts)

        # Which half
        which_half = calculate_which_half_btts(half_btts)

        # Historical trends
        trends = get_btts_trends_from_h2h(match_data)

        # Team scoring by half
        team_scoring = {
            'fh_home_scores': round(half_btts['fh_home_scores'] * 100, 1),
            'fh_away_scores': round(half_btts['fh_away_scores'] * 100, 1),
            'sh_home_scores': round(half_btts['sh_home_scores'] * 100, 1),
            'sh_away_scores': round(half_btts['sh_away_scores'] * 100, 1),
        }

        # Top pick: find strongest prediction
        picks = {
            'IY KG Var': round(half_btts['fh_btts_yes'] * 100, 1),
            'IY KG Yok': round(half_btts['fh_btts_no'] * 100, 1),
            '2Y KG Var': round(half_btts['sh_btts_yes'] * 100, 1),
            '2Y KG Yok': round(half_btts['sh_btts_no'] * 100, 1),
            'Her Iki Yarida KG Var': combinations['both_halves_btts'],
            'Hicbir Yarida KG Yok': combinations['no_half_btts'],
        }
        top_pick = max(picks, key=picks.get)
        top_prob = picks[top_pick]

        # Confidence
        h2h = match_data.get('h2h_details') or {}
        data_points = len(h2h.get('home_team_previous_matches', []))
        has_ht = trends['matches_analyzed'] >= 5

        if data_points >= 8 and has_ht:
            confidence = 68.0
        elif data_points >= 5:
            confidence = 58.0
        else:
            confidence = 45.0

        return {
            'half_btts_predictions': {
                'first_half_btts': {
                    'yes': round(half_btts['fh_btts_yes'] * 100, 1),
                    'no': round(half_btts['fh_btts_no'] * 100, 1),
                },
                'second_half_btts': {
                    'yes': round(half_btts['sh_btts_yes'] * 100, 1),
                    'no': round(half_btts['sh_btts_no'] * 100, 1),
                },
                'combinations': combinations,
                'which_half_btts': which_half,
                'team_scoring_by_half': team_scoring,
                'historical_trends': trends,
                'top_pick': top_pick,
                'top_pick_probability': top_prob,
                'confidence': confidence,
            }
        }

    except Exception as e:
        logger.error(f"Half BTTS prediction error: {e}")
        return {}
