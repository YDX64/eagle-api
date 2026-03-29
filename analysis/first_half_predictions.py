"""
First Half Goal Predictions - Detailed IY (Ilk Yari) Analysis
Uses half-time Poisson model combined with H2H first-half statistics.

Features:
1. IY 0.5 Ust/Alt
2. IY 1.5 Ust/Alt
3. IY Dogru Skor (0-0, 1-0, 0-1, 1-1, 2-0, 0-2, 2-1, 1-2)
4. IY 1X2 (MS)
5. IY Gol Beklentisi (xG)
6. Team-specific IY scoring tendencies

Data sources:
- h2h_details: HT scores from past matches (ht_score field)
- poisson_model: HT lambdas
- first_half_odds: Bookmaker IY odds
- team_performance: Team IY scoring/conceding

Research basis: First half accounts for ~40-45% of total goals.
IY lambda = total_lambda * first_half_share (empirical ~0.42)
"""
import math
import logging
from typing import Dict, Optional, Tuple, List

logger = logging.getLogger(__name__)

# First half goal share (empirical from research)
# Top 5 leagues average: ~42% of goals in first half
FIRST_HALF_SHARE = 0.42


def poisson_probability(lam, k):
    """P(X=k) for Poisson distribution."""
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    try:
        return (lam ** k) * math.exp(-lam) / math.factorial(k)
    except (OverflowError, ValueError):
        return 0.0


def extract_ht_lambdas(match_data: Dict) -> Optional[Tuple[float, float]]:
    """
    Extract first-half goal lambdas from multiple sources.

    Priority:
    1. H2H first-half goal averages (most reliable for IY)
    2. Poisson model HT lambdas
    3. Full-time lambdas * FIRST_HALF_SHARE
    """
    # Source 1: H2H analysis HT averages
    analysis = match_data.get('analysis', {})
    h2h_analysis = analysis.get('h2h_analysis', {})
    h2h_avg = h2h_analysis.get('avg_goals', {})

    ht_home_from_h2h = h2h_avg.get('ht_home_team_avg_goals')
    ht_away_from_h2h = h2h_avg.get('ht_away_team_avg_goals')

    # Source 2: Poisson model HT lambdas
    poisson = analysis.get('poisson_predictions', {})
    poisson_xg = poisson.get('expected_goals', {})

    # Source 3: Direct H2H match data
    h2h = match_data.get('h2h_details') or {}
    match_info = match_data.get('match_info') or {}
    home_team = match_info.get('home_team_name', '')
    away_team = match_info.get('away_team_name', '')

    ht_home_direct = None
    ht_away_direct = None

    if home_team and away_team:
        ht_home_goals, ht_away_goals, ht_count = _extract_ht_goals_from_matches(h2h, home_team, away_team)
        if ht_count >= 3:
            ht_home_direct = ht_home_goals / ht_count
            ht_away_direct = ht_away_goals / ht_count

    # Combine sources with priority weighting
    ht_home_lambda = None
    ht_away_lambda = None

    sources = []

    if ht_home_from_h2h and ht_away_from_h2h:
        sources.append(('h2h_analysis', float(ht_home_from_h2h), float(ht_away_from_h2h), 0.35))

    if ht_home_direct is not None and ht_away_direct is not None:
        sources.append(('h2h_direct', ht_home_direct, ht_away_direct, 0.30))

    if poisson_xg.get('home') and poisson_xg.get('away'):
        ht_from_poisson_h = float(poisson_xg['home']) * FIRST_HALF_SHARE
        ht_from_poisson_a = float(poisson_xg['away']) * FIRST_HALF_SHARE
        sources.append(('poisson', ht_from_poisson_h, ht_from_poisson_a, 0.35))

    if not sources:
        return None

    # Weighted average
    total_weight = sum(w for _, _, _, w in sources)
    ht_home_lambda = sum(h * w for _, h, _, w in sources) / total_weight
    ht_away_lambda = sum(a * w for _, _, a, w in sources) / total_weight

    # Clamp
    ht_home_lambda = max(0.15, min(2.0, ht_home_lambda))
    ht_away_lambda = max(0.15, min(2.0, ht_away_lambda))

    return ht_home_lambda, ht_away_lambda


def _extract_ht_goals_from_matches(h2h: Dict, home_team: str, away_team: str) -> Tuple[float, float, int]:
    """Extract HT goals from team's recent matches."""
    home_ht_goals = 0
    away_ht_goals = 0
    count = 0

    # From home team's recent matches
    for m in (h2h.get('home_team_previous_matches') or [])[:10]:
        ht_score = m.get('ht_score', '')
        if not ht_score or '-' not in ht_score:
            continue
        try:
            ht_h, ht_a = map(int, ht_score.split('-'))
            if m.get('home_team') == home_team:
                home_ht_goals += ht_h
            else:
                home_ht_goals += ht_a
            count += 1
        except (ValueError, IndexError):
            continue

    # From away team's recent matches
    away_count = 0
    for m in (h2h.get('away_team_previous_matches') or [])[:10]:
        ht_score = m.get('ht_score', '')
        if not ht_score or '-' not in ht_score:
            continue
        try:
            ht_h, ht_a = map(int, ht_score.split('-'))
            if m.get('home_team') == away_team:
                away_ht_goals += ht_h
            else:
                away_ht_goals += ht_a
            away_count += 1
        except (ValueError, IndexError):
            continue

    total_count = max(count, away_count, 1)
    return home_ht_goals, away_ht_goals, total_count


def calculate_ht_over_under(ht_home_lambda, ht_away_lambda) -> Dict:
    """Calculate first half over/under probabilities."""
    max_goals = 6

    home_probs = [poisson_probability(ht_home_lambda, k) for k in range(max_goals + 1)]
    away_probs = [poisson_probability(ht_away_lambda, k) for k in range(max_goals + 1)]

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


def calculate_ht_correct_score(ht_home_lambda, ht_away_lambda) -> List[Dict]:
    """
    Calculate most likely first-half scores.
    HT scores rarely exceed 2-1, so max 3 goals per side.
    """
    scores = []
    total_prob = 0.0

    for h in range(4):  # 0-3
        for a in range(4):  # 0-3
            prob = poisson_probability(ht_home_lambda, h) * poisson_probability(ht_away_lambda, a)
            scores.append({
                'score': f"{h}-{a}",
                'home_goals': h,
                'away_goals': a,
                'probability': prob,
            })
            total_prob += prob

    # Normalize
    for s in scores:
        s['probability'] = round((s['probability'] / total_prob) * 100, 2) if total_prob > 0 else 0

    # Sort by probability
    scores.sort(key=lambda x: x['probability'], reverse=True)
    return scores[:10]


def calculate_ht_1x2(ht_home_lambda, ht_away_lambda) -> Dict:
    """Calculate first half 1X2 probabilities."""
    max_goals = 6
    home_probs = [poisson_probability(ht_home_lambda, k) for k in range(max_goals + 1)]
    away_probs = [poisson_probability(ht_away_lambda, k) for k in range(max_goals + 1)]

    p_home = 0.0
    p_draw = 0.0
    p_away = 0.0

    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            joint = home_probs[h] * away_probs[a]
            if h > a:
                p_home += joint
            elif h == a:
                p_draw += joint
            else:
                p_away += joint

    return {
        'home': round(p_home * 100, 1),
        'draw': round(p_draw * 100, 1),
        'away': round(p_away * 100, 1),
    }


def calculate_ht_team_scoring(ht_home_lambda, ht_away_lambda) -> Dict:
    """Calculate probability each team scores in first half."""
    p_home_scores = 1.0 - poisson_probability(ht_home_lambda, 0)
    p_away_scores = 1.0 - poisson_probability(ht_away_lambda, 0)

    return {
        'home_scores_ht': round(p_home_scores * 100, 1),
        'home_clean_sheet_ht': round((1 - p_away_scores) * 100, 1),  # = P(away=0)
        'away_scores_ht': round(p_away_scores * 100, 1),
        'away_clean_sheet_ht': round((1 - p_home_scores) * 100, 1),  # = P(home=0)
    }


def get_ht_trends_from_h2h(match_data: Dict) -> Dict:
    """Extract first-half trends from H2H history."""
    h2h = match_data.get('h2h_details') or {}
    match_info = match_data.get('match_info') or {}
    home_team = match_info.get('home_team_name', '')

    trends = {
        'ht_goals_in_last_10_home': 0,
        'ht_goals_in_last_10_away': 0,
        'ht_0_0_rate': 0,
        'ht_both_scored_rate': 0,
        'matches_analyzed': 0,
    }

    home_matches = h2h.get('home_team_previous_matches') or []
    ht_goals_home = 0
    ht_0_0_count = 0
    ht_btts_count = 0
    ht_match_count = 0

    for m in home_matches[:10]:
        ht_score = m.get('ht_score', '')
        if not ht_score or '-' not in ht_score:
            continue
        try:
            ht_h, ht_a = map(int, ht_score.split('-'))
            is_home = m.get('home_team') == home_team
            team_ht_goals = ht_h if is_home else ht_a
            ht_goals_home += team_ht_goals
            if ht_h == 0 and ht_a == 0:
                ht_0_0_count += 1
            if ht_h > 0 and ht_a > 0:
                ht_btts_count += 1
            ht_match_count += 1
        except (ValueError, IndexError):
            continue

    if ht_match_count > 0:
        trends['ht_goals_in_last_10_home'] = ht_goals_home
        trends['ht_0_0_rate'] = round(ht_0_0_count / ht_match_count * 100, 1)
        trends['ht_both_scored_rate'] = round(ht_btts_count / ht_match_count * 100, 1)
        trends['matches_analyzed'] = ht_match_count

    return trends


def analyze_first_half_predictions(match_data: Dict) -> Dict:
    """
    Main first half prediction function.

    Returns:
        {
            "first_half_predictions": {
                "ht_over_under": {over_0_5, under_0_5, over_1_5, under_1_5, over_2_5, under_2_5},
                "ht_1x2": {home, draw, away},
                "ht_correct_score": [{score, probability}, ...],
                "ht_team_scoring": {home_scores_ht, away_scores_ht, ...},
                "ht_expected_goals": {home, away, total},
                "ht_trends": {...},
                "top_pick": str,
                "top_pick_probability": float,
                "confidence": float
            }
        }
    """
    try:
        ht_lambdas = extract_ht_lambdas(match_data)
        if not ht_lambdas:
            return {}

        ht_home_lambda, ht_away_lambda = ht_lambdas

        # Over/Under
        over_under = calculate_ht_over_under(ht_home_lambda, ht_away_lambda)

        # 1X2
        ht_1x2 = calculate_ht_1x2(ht_home_lambda, ht_away_lambda)

        # Correct score
        correct_scores = calculate_ht_correct_score(ht_home_lambda, ht_away_lambda)

        # Team scoring
        team_scoring = calculate_ht_team_scoring(ht_home_lambda, ht_away_lambda)

        # Trends
        trends = get_ht_trends_from_h2h(match_data)

        # Expected goals
        ht_xg = {
            'home': round(ht_home_lambda, 2),
            'away': round(ht_away_lambda, 2),
            'total': round(ht_home_lambda + ht_away_lambda, 2),
        }

        # Top pick selection
        picks = {
            'IY Ust 0.5': over_under['over_0_5'],
            'IY Alt 0.5': over_under['under_0_5'],
            'IY Ust 1.5': over_under['over_1_5'],
            'IY Alt 1.5': over_under['under_1_5'],
        }
        top_pick = max(picks, key=picks.get)
        top_prob = picks[top_pick]

        # Confidence
        h2h = match_data.get('h2h_details') or {}
        data_points = len(h2h.get('home_team_previous_matches', []))
        has_ht_data = trends['matches_analyzed'] >= 5

        if data_points >= 8 and has_ht_data:
            confidence = 72.0
        elif data_points >= 5:
            confidence = 62.0
        else:
            confidence = 50.0

        return {
            'first_half_predictions': {
                'ht_over_under': over_under,
                'ht_1x2': ht_1x2,
                'ht_correct_score': correct_scores,
                'ht_team_scoring': team_scoring,
                'ht_expected_goals': ht_xg,
                'ht_trends': trends,
                'top_pick': top_pick,
                'top_pick_probability': top_prob,
                'confidence': confidence,
            }
        }

    except Exception as e:
        logger.error(f"First half prediction error: {e}")
        return {}
