"""
Poisson Goal Model - Falcon-style statistical goal prediction
Calculates goal probabilities using Poisson distribution based on
team scoring/conceding rates from recent matches.

This is an ADDITIONAL analysis source - it does NOT replace existing analyses.
"""
import math
import logging

logger = logging.getLogger(__name__)


def poisson_probability(lam, k):
    """Calculate P(X=k) for Poisson distribution with parameter lambda."""
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return (lam ** k) * math.exp(-lam) / math.factorial(k)


def poisson_cumulative(lam, max_k=10):
    """Calculate P(X=0), P(X=1), ..., P(X=max_k) for Poisson."""
    return [poisson_probability(lam, k) for k in range(max_k + 1)]


def calculate_over_probability(home_lambda, away_lambda, line):
    """
    Calculate P(total goals > line) using joint Poisson.
    E.g. line=2.5 means P(home+away >= 3)
    """
    threshold = int(line) + 1  # 2.5 -> need 3+, 3.5 -> need 4+
    max_goals = 12

    home_probs = poisson_cumulative(home_lambda, max_goals)
    away_probs = poisson_cumulative(away_lambda, max_goals)

    prob_under = 0.0
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            if h + a < threshold:
                prob_under += home_probs[h] * away_probs[a]

    return round((1.0 - prob_under) * 100, 1)


def calculate_btts_probability(home_lambda, away_lambda):
    """
    Calculate P(both teams score) = 1 - P(home=0) - P(away=0) + P(both=0)
    """
    p_home_zero = poisson_probability(home_lambda, 0)
    p_away_zero = poisson_probability(away_lambda, 0)
    p_both_zero = p_home_zero * p_away_zero

    # P(BTTS) = 1 - P(home=0 OR away=0) = 1 - P(h=0) - P(a=0) + P(h=0 AND a=0)
    p_btts = 1.0 - p_home_zero - p_away_zero + p_both_zero
    return round(p_btts * 100, 1)


def calculate_1x2_probability(home_lambda, away_lambda):
    """
    Calculate match result probabilities from Poisson.
    Returns {home, draw, away} percentages.
    """
    max_goals = 10
    home_probs = poisson_cumulative(home_lambda, max_goals)
    away_probs = poisson_cumulative(away_lambda, max_goals)

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
        "home": round(p_home * 100, 1),
        "draw": round(p_draw * 100, 1),
        "away": round(p_away * 100, 1),
    }


def extract_scoring_rates(match_data):
    """
    Extract average goals scored/conceded from h2h_details.
    Returns (home_attack, home_defense, away_attack, away_defense) rates per match.
    """
    h2h = match_data.get("h2h_details") or {}
    match_info = match_data.get("match_info") or {}
    home_team = match_info.get("home_team_name", "")
    away_team = match_info.get("away_team_name", "")

    if not home_team or not away_team:
        return None

    # Home team's recent matches
    home_matches = h2h.get("home_team_previous_matches") or []
    away_matches = h2h.get("away_team_previous_matches") or []

    home_scored = []
    home_conceded = []
    away_scored = []
    away_conceded = []

    for m in home_matches[:15]:
        try:
            hs = int(m.get("home_score", 0))
            aws = int(m.get("away_score", 0))
            if m.get("home_team") == home_team:
                home_scored.append(hs)
                home_conceded.append(aws)
            elif m.get("away_team") == home_team:
                home_scored.append(aws)
                home_conceded.append(hs)
        except (ValueError, TypeError):
            continue

    for m in away_matches[:15]:
        try:
            hs = int(m.get("home_score", 0))
            aws = int(m.get("away_score", 0))
            if m.get("home_team") == away_team:
                away_scored.append(hs)
                away_conceded.append(aws)
            elif m.get("away_team") == away_team:
                away_scored.append(aws)
                away_conceded.append(hs)
        except (ValueError, TypeError):
            continue

    if len(home_scored) < 3 or len(away_scored) < 3:
        return None

    home_attack = sum(home_scored) / len(home_scored)
    home_defense = sum(home_conceded) / len(home_conceded)
    away_attack = sum(away_scored) / len(away_scored)
    away_defense = sum(away_conceded) / len(away_conceded)

    return home_attack, home_defense, away_attack, away_defense


def analyze_poisson(match_data):
    """
    Main Poisson analysis function.
    Calculates goal-based probabilities from team scoring rates.

    Returns dict compatible with final_predictions source format:
    {
        "poisson_predictions": {
            "1x2": {home, draw, away},
            "goal_lines": {over_2_5, under_2_5, over_3_5, under_3_5, ...},
            "btts": {yes, no},
            "ht_goals": {over_0_5, under_0_5, ...},
            "expected_goals": {home, away, total},
            "confidence": float
        }
    }
    """
    try:
        rates = extract_scoring_rates(match_data)
        if not rates:
            return {}

        home_attack, home_defense, away_attack, away_defense = rates

        # Expected goals: attack of team A * defense weakness of team B
        # Normalized by league average (~1.3 goals per team)
        league_avg = 1.3

        home_lambda = (home_attack / league_avg) * (away_defense / league_avg) * league_avg
        away_lambda = (away_attack / league_avg) * (home_defense / league_avg) * league_avg

        # Clamp to reasonable range
        home_lambda = max(0.3, min(4.0, home_lambda))
        away_lambda = max(0.3, min(4.0, away_lambda))

        # Half-time lambdas (roughly 40-45% of full time)
        ht_home_lambda = home_lambda * 0.42
        ht_away_lambda = away_lambda * 0.42

        # Calculate all probabilities
        ms_probs = calculate_1x2_probability(home_lambda, away_lambda)

        over_15 = calculate_over_probability(home_lambda, away_lambda, 1.5)
        over_25 = calculate_over_probability(home_lambda, away_lambda, 2.5)
        over_35 = calculate_over_probability(home_lambda, away_lambda, 3.5)

        btts_yes = calculate_btts_probability(home_lambda, away_lambda)

        ht_over_05 = calculate_over_probability(ht_home_lambda, ht_away_lambda, 0.5)
        ht_over_15 = calculate_over_probability(ht_home_lambda, ht_away_lambda, 1.5)

        # HT 1x2
        ht_ms = calculate_1x2_probability(ht_home_lambda, ht_away_lambda)

        # Confidence based on data quality (more matches = higher confidence)
        data_points = len((match_data.get("h2h_details") or {}).get("home_team_previous_matches") or [])
        if data_points >= 10:
            confidence = 75.0
        elif data_points >= 7:
            confidence = 65.0
        elif data_points >= 5:
            confidence = 55.0
        else:
            confidence = 45.0

        return {
            "poisson_predictions": {
                "1x2": ms_probs,
                "goal_lines": {
                    "over_1_5": over_15,
                    "under_1_5": round(100 - over_15, 1),
                    "over_2_5": over_25,
                    "under_2_5": round(100 - over_25, 1),
                    "over_3_5": over_35,
                    "under_3_5": round(100 - over_35, 1),
                },
                "btts": {
                    "yes": btts_yes,
                    "no": round(100 - btts_yes, 1),
                },
                "ht_1x2": ht_ms,
                "ht_goals": {
                    "over_0_5": ht_over_05,
                    "under_0_5": round(100 - ht_over_05, 1),
                    "over_1_5": ht_over_15,
                    "under_1_5": round(100 - ht_over_15, 1),
                },
                "expected_goals": {
                    "home": round(home_lambda, 2),
                    "away": round(away_lambda, 2),
                    "total": round(home_lambda + away_lambda, 2),
                },
                "confidence": confidence,
            }
        }

    except Exception as e:
        logger.error(f"Poisson analysis error: {e}")
        return {}
