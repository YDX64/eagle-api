"""
Card Prediction Algorithm - Statistical card total prediction
Uses match characteristics, team aggression, and Poisson distribution
to predict yellow/red card totals for over/under markets.

Data sources used:
- h2h_details: Team recent match history
- odds_comp: Asian handicap closeness (match competitiveness proxy)
- match_info: League context
- team_performance: Team aggression indicators

Card prediction is inherently harder than goal prediction because
Eagle doesn't store historical card counts. We use proxy indicators:
- Match competitiveness (close AH = more fouls = more cards)
- League average goals as league intensity proxy
- Team win/loss ratio (losing teams commit more tactical fouls)
- H2H rivalry intensity (close H2H = more heated matches)
"""
import math
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


# League card averages (cards per match) - empirical data from major leagues
# Source: FootyStats, WhoScored aggregate data 2023-2025
LEAGUE_CARD_AVERAGES = {
    # Top 5 European leagues
    'la liga': {'avg_cards': 5.2, 'avg_yellow': 4.8, 'avg_red': 0.20},
    'serie a': {'avg_cards': 5.0, 'avg_yellow': 4.6, 'avg_red': 0.18},
    'ligue 1': {'avg_cards': 4.5, 'avg_yellow': 4.2, 'avg_red': 0.15},
    'bundesliga': {'avg_cards': 4.0, 'avg_yellow': 3.7, 'avg_red': 0.12},
    'premier league': {'avg_cards': 3.6, 'avg_yellow': 3.3, 'avg_red': 0.10},
    # Turkish leagues
    'super lig': {'avg_cards': 5.5, 'avg_yellow': 5.0, 'avg_red': 0.25},
    'tff 1. lig': {'avg_cards': 5.3, 'avg_yellow': 4.9, 'avg_red': 0.22},
    # South American
    'brasileirao': {'avg_cards': 5.8, 'avg_yellow': 5.3, 'avg_red': 0.25},
    'liga profesional': {'avg_cards': 5.5, 'avg_yellow': 5.0, 'avg_red': 0.22},
    # Other European
    'eredivisie': {'avg_cards': 4.2, 'avg_yellow': 3.9, 'avg_red': 0.12},
    'primeira liga': {'avg_cards': 5.3, 'avg_yellow': 4.9, 'avg_red': 0.20},
    'jupiler pro league': {'avg_cards': 4.5, 'avg_yellow': 4.2, 'avg_red': 0.15},
}

# Default for unknown leagues
DEFAULT_CARD_AVERAGE = {'avg_cards': 4.5, 'avg_yellow': 4.1, 'avg_red': 0.16}


def poisson_probability(lam, k):
    """P(X=k) for Poisson distribution."""
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    try:
        return (lam ** k) * math.exp(-lam) / math.factorial(k)
    except (OverflowError, ValueError):
        return 0.0


def get_league_card_data(match_data: Dict) -> Dict:
    """Get league-specific card averages."""
    match_info = match_data.get('match_info') or {}
    league_name = match_info.get('league_name', '').lower().strip()

    # Try exact match first, then partial match
    for key, data in LEAGUE_CARD_AVERAGES.items():
        if key in league_name or league_name in key:
            return data

    return DEFAULT_CARD_AVERAGE


def calculate_match_competitiveness(match_data: Dict) -> float:
    """
    Calculate match competitiveness score (0-1).
    Close matches = more fouls = more cards.

    Uses Asian handicap line as proxy:
    - AH 0 (level) = very competitive = 1.0
    - AH -2.5 (big favorite) = less competitive = 0.3
    """
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

    if not ah_lines:
        return 0.6  # Default moderate competitiveness

    avg_ah = sum(ah_lines) / len(ah_lines)

    # Convert AH to competitiveness: 0 AH = 1.0, 3 AH = 0.2
    competitiveness = max(0.2, 1.0 - (avg_ah / 3.5))
    return round(competitiveness, 3)


def calculate_team_aggression(matches: list, team_name: str) -> float:
    """
    Calculate team aggression score (0-1) from match history.
    Proxies: losing rate, goal conceded rate, competitive matches rate.

    Teams that lose more → more tactical fouls → more cards.
    Teams that concede more → more desperate defending → more cards.
    """
    if not matches or len(matches) < 3:
        return 0.5

    recent = matches[:10]
    losses = 0
    goals_conceded = 0
    close_matches = 0
    total = 0

    for m in recent:
        try:
            hs = int(m.get('home_score', 0))
            aws = int(m.get('away_score', 0))
            total += 1

            is_home = m.get('home_team') == team_name
            team_goals = hs if is_home else aws
            opp_goals = aws if is_home else hs

            if team_goals < opp_goals:
                losses += 1
            goals_conceded += opp_goals

            # Close match (1 goal difference or draw)
            if abs(hs - aws) <= 1:
                close_matches += 1
        except (ValueError, TypeError):
            continue

    if total == 0:
        return 0.5

    loss_rate = losses / total
    avg_conceded = goals_conceded / total
    close_rate = close_matches / total

    # Aggression = weighted combo of losing, conceding, and competitive matches
    aggression = (loss_rate * 0.3) + (min(avg_conceded / 3.0, 1.0) * 0.3) + (close_rate * 0.4)
    return round(max(0.1, min(1.0, aggression)), 3)


def calculate_h2h_rivalry_intensity(h2h_matches: list) -> float:
    """
    Calculate H2H rivalry intensity from head-to-head history.
    Close H2H records = more intense rivalry = more cards.
    """
    if not h2h_matches or len(h2h_matches) < 3:
        return 0.5

    recent = h2h_matches[:10]
    close_count = 0
    total = 0

    for m in recent:
        try:
            score = m.get('score', '0-0')
            hs, aws = map(int, score.split('-'))
            total += 1
            if abs(hs - aws) <= 1:
                close_count += 1
        except (ValueError, IndexError):
            continue

    if total == 0:
        return 0.5

    return round(close_count / total, 3)


def estimate_card_lambda(match_data: Dict) -> Dict:
    """
    Estimate expected total cards (lambda) for Poisson model.

    Combines:
    1. League base average (40% weight)
    2. Match competitiveness from AH (25% weight)
    3. Team aggression proxy (20% weight)
    4. H2H rivalry intensity (15% weight)
    """
    h2h = match_data.get('h2h_details') or {}
    match_info = match_data.get('match_info') or {}
    home_team = match_info.get('home_team_name', '')
    away_team = match_info.get('away_team_name', '')

    # 1. League base
    league_data = get_league_card_data(match_data)
    league_avg = league_data['avg_cards']

    # 2. Match competitiveness
    competitiveness = calculate_match_competitiveness(match_data)
    # Highly competitive matches get +20% cards, low competitiveness -20%
    comp_factor = 0.8 + (competitiveness * 0.4)  # range: 0.8 - 1.2

    # 3. Team aggression
    home_matches = h2h.get('home_team_previous_matches', [])
    away_matches = h2h.get('away_team_previous_matches', [])
    home_aggression = calculate_team_aggression(home_matches, home_team)
    away_aggression = calculate_team_aggression(away_matches, away_team)
    avg_aggression = (home_aggression + away_aggression) / 2
    aggression_factor = 0.7 + (avg_aggression * 0.6)  # range: 0.7 - 1.3

    # 4. H2H rivalry
    h2h_matches = h2h.get('head_to_head', [])
    rivalry = calculate_h2h_rivalry_intensity(h2h_matches)
    rivalry_factor = 0.85 + (rivalry * 0.3)  # range: 0.85 - 1.15

    # Weighted combination
    estimated_lambda = league_avg * (
        0.40 * 1.0 +            # League base (identity)
        0.25 * comp_factor +     # Competitiveness adjustment
        0.20 * aggression_factor + # Team aggression
        0.15 * rivalry_factor    # H2H rivalry
    )

    # Clamp to reasonable range (2.0 - 8.0 cards per match)
    estimated_lambda = max(2.0, min(8.0, estimated_lambda))

    return {
        'total_lambda': round(estimated_lambda, 2),
        'league_base': league_avg,
        'competitiveness': competitiveness,
        'home_aggression': home_aggression,
        'away_aggression': away_aggression,
        'rivalry_intensity': rivalry,
        'comp_factor': round(comp_factor, 3),
        'aggression_factor': round(aggression_factor, 3),
        'rivalry_factor': round(rivalry_factor, 3),
    }


def calculate_card_over_under(card_lambda: float) -> Dict:
    """
    Calculate over/under probabilities for card lines using Poisson.

    Lines: 2.5, 3.5, 4.5, 5.5
    """
    results = {}

    for line in [2.5, 3.5, 4.5, 5.5]:
        threshold = int(line) + 1  # 2.5 → need 3+
        prob_under = sum(poisson_probability(card_lambda, k) for k in range(threshold))
        prob_over = 1.0 - prob_under

        key = str(line).replace('.', '_')
        results[f'over_{key}'] = round(prob_over * 100, 1)
        results[f'under_{key}'] = round(prob_under * 100, 1)

    return results


def calculate_team_card_split(match_data: Dict, card_lambda: float) -> Dict:
    """
    Estimate home vs away team card distribution.
    Away teams typically receive ~55% of cards (more defensive play).
    Losing team bias: teams behind get more cards.
    """
    competitiveness = calculate_match_competitiveness(match_data)

    # Base split: away teams get slightly more cards
    home_share = 0.45
    away_share = 0.55

    # If very competitive (even match), split is closer to 50-50
    if competitiveness > 0.7:
        home_share = 0.48
        away_share = 0.52

    home_lambda = card_lambda * home_share
    away_lambda = card_lambda * away_share

    return {
        'home_expected_cards': round(home_lambda, 2),
        'away_expected_cards': round(away_lambda, 2),
        'home_share_pct': round(home_share * 100, 1),
        'away_share_pct': round(away_share * 100, 1),
    }


def analyze_card_predictions(match_data: Dict) -> Dict:
    """
    Main card prediction analysis function.

    Returns:
        {
            "card_predictions": {
                "expected_total_cards": float,
                "over_under": {over_2_5, under_2_5, over_3_5, ...},
                "team_split": {home_expected, away_expected},
                "factors": {league_base, competitiveness, aggression, rivalry},
                "confidence": float,
                "top_pick": str,
                "top_pick_probability": float
            }
        }
    """
    try:
        # Estimate card lambda
        lambda_info = estimate_card_lambda(match_data)
        card_lambda = lambda_info['total_lambda']

        # Calculate over/under
        over_under = calculate_card_over_under(card_lambda)

        # Team card split
        team_split = calculate_team_card_split(match_data, card_lambda)

        # Most likely card count
        most_likely_count = round(card_lambda)
        most_likely_prob = poisson_probability(card_lambda, most_likely_count)

        # Card count distribution (0-10)
        card_distribution = {}
        for k in range(11):
            card_distribution[str(k)] = round(poisson_probability(card_lambda, k) * 100, 2)

        # Top pick: find the line with strongest signal
        lines = {
            'Ust 3.5 Kart': over_under.get('over_3_5', 50),
            'Alt 3.5 Kart': over_under.get('under_3_5', 50),
            'Ust 4.5 Kart': over_under.get('over_4_5', 50),
            'Alt 4.5 Kart': over_under.get('under_4_5', 50),
            'Ust 5.5 Kart': over_under.get('over_5_5', 50),
            'Alt 5.5 Kart': over_under.get('under_5_5', 50),
        }
        top_pick_name = max(lines, key=lines.get)
        top_pick_prob = lines[top_pick_name]

        # Confidence based on data availability
        h2h = match_data.get('h2h_details') or {}
        data_points = len(h2h.get('home_team_previous_matches', []))
        has_odds = bool(match_data.get('odds_comp'))

        if data_points >= 8 and has_odds:
            confidence = 70.0
        elif data_points >= 5:
            confidence = 60.0
        elif has_odds:
            confidence = 55.0
        else:
            confidence = 45.0

        return {
            'card_predictions': {
                'expected_total_cards': card_lambda,
                'most_likely_count': most_likely_count,
                'most_likely_count_prob': round(most_likely_prob * 100, 1),
                'over_under': over_under,
                'team_split': team_split,
                'card_distribution': card_distribution,
                'factors': {
                    'league_base': lambda_info['league_base'],
                    'competitiveness': lambda_info['competitiveness'],
                    'home_aggression': lambda_info['home_aggression'],
                    'away_aggression': lambda_info['away_aggression'],
                    'rivalry_intensity': lambda_info['rivalry_intensity'],
                },
                'top_pick': top_pick_name,
                'top_pick_probability': top_pick_prob,
                'confidence': confidence,
            }
        }

    except Exception as e:
        logger.error(f"Card prediction error: {e}")
        return {}
