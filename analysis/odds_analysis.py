"""
Odds Analysis Module
Analyzes betting odds data to extract predictive metrics and market trends
"""

import logging
from typing import Dict, List


def analyze_odds_comprehensive(odds_comp_data: Dict) -> Dict:
    """
    Comprehensive odds analysis including 1x2 percentages, odds movements,
    goal line trends, and asian handicap analysis.

    Args:
        odds_comp_data (dict): Odds comparison data from API

    Returns:
        dict: Complete odds analysis results
    """
    try:
        odds_comparison = odds_comp_data.get('odds_comparison', [])
        # first_half_odds data içinde ayrı bir key olarak gelir
        first_half_odds_data = odds_comp_data.get('first_half_odds', {})
        if isinstance(first_half_odds_data, dict) and 'first_half_odds' in first_half_odds_data:
            first_half_odds = first_half_odds_data['first_half_odds']
        else:
            first_half_odds = []

        if not odds_comparison and not first_half_odds:
            return {"odds_analysis": {"available": False, "reason": "no_odds_data"}}

        analysis = {
            "odds_analysis": {
                "1x2_analysis": calculate_1x2_analysis(odds_comparison) if odds_comparison else {"available": False}
            }
        }

        return analysis

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in comprehensive odds analysis: {str(e)}")
        return {"odds_analysis": {"available": False, "error": str(e)}}


def calculate_1x2_analysis(odds_comparison: List[Dict]) -> Dict:
    """
    Calculate 1x2 odds analysis with percentages and normalization.

    Args:
        odds_comparison (list): List of company odds data

    Returns:
        dict: 1x2 analysis results
    """
    try:
        home_odds = []
        draw_odds = []
        away_odds = []

        for company in odds_comparison:
            european_odds = company.get('european_odds', {}).get('pre_match_odds', {})

            home_odd = european_odds.get('home')
            draw_odd = european_odds.get('draw')
            away_odd = european_odds.get('away')

            if home_odd and draw_odd and away_odd:
                try:
                    home_odds.append(float(home_odd))
                    draw_odds.append(float(draw_odd))
                    away_odds.append(float(away_odd))
                except (ValueError, TypeError):
                    continue

        if not home_odds:
            return {"available": False}

        # Raw averages
        avg_home = sum(home_odds) / len(home_odds)
        avg_draw = sum(draw_odds) / len(draw_odds)
        avg_away = sum(away_odds) / len(away_odds)

        # Convert odds to implied probabilities
        # Odds = 1/probability, so probability = 1/odds
        home_prob = (1 / avg_home) * 100
        draw_prob = (1 / avg_draw) * 100
        away_prob = (1 / avg_away) * 100

        # Total includes bookmaker margin
        total_prob = home_prob + draw_prob + away_prob

        # Normalize to 100% (remove bookmaker margin)
        home_percent = (home_prob / total_prob) * 100
        draw_percent = (draw_prob / total_prob) * 100
        away_percent = (away_prob / total_prob) * 100

        # Smart normalization for high odds
        normalized_percentages = smart_normalize_percentages(home_percent, draw_percent, away_percent)

        return {
            "available": True,
            "companies_analyzed": len(home_odds),
            "raw_averages": {
                "home": round(avg_home, 2),
                "draw": round(avg_draw, 2),
                "away": round(avg_away, 2)
            },
            "normalized_percentages": {
                "home": round(normalized_percentages['home'], 1),
                "draw": round(normalized_percentages['draw'], 1),
                "away": round(normalized_percentages['away'], 1)
            },
            "market_bias": determine_market_bias(normalized_percentages)
        }

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in 1x2 analysis: {str(e)}")
        return {"available": False, "error": str(e)}


def smart_normalize_percentages(home_pct: float, draw_pct: float, away_pct: float) -> Dict[str, float]:
    """
    Smart normalization for high odds to prevent extreme percentages.

    Args:
        home_pct, draw_pct, away_pct: Raw percentages

    Returns:
        dict: Normalized percentages
    """
    # Find the minimum percentage
    min_pct = min(home_pct, draw_pct, away_pct)

    # If any percentage is extremely high (>70%), apply smart normalization
    max_pct = max(home_pct, draw_pct, away_pct)

    if max_pct > 70:
        # Calculate adjustment factor
        target_max = 65.0  # Cap at 65%
        adjustment = (max_pct - target_max) * 0.3  # Reduce by 30% of excess

        # Apply adjustment proportionally
        if home_pct == max_pct:
            home_pct -= adjustment
            draw_pct += adjustment * 0.4
            away_pct += adjustment * 0.6
        elif draw_pct == max_pct:
            draw_pct -= adjustment
            home_pct += adjustment * 0.5
            away_pct += adjustment * 0.5
        else:  # away_pct == max_pct
            away_pct -= adjustment
            home_pct += adjustment * 0.6
            draw_pct += adjustment * 0.4

    # Ensure minimum percentages
    min_allowed = 5.0
    if home_pct < min_allowed:
        home_pct = min_allowed
    if draw_pct < min_allowed:
        draw_pct = min_allowed
    if away_pct < min_allowed:
        away_pct = min_allowed

    # Renormalize to ensure sum = 100
    total = home_pct + draw_pct + away_pct
    if total != 100:
        factor = 100 / total
        home_pct *= factor
        draw_pct *= factor
        away_pct *= factor

    return {
        'home': home_pct,
        'draw': draw_pct,
        'away': away_pct
    }


def determine_market_bias(percentages: Dict[str, float]) -> str:
    """Determine market bias based on percentages."""
    home = percentages['home']
    draw = percentages['draw']
    away = percentages['away']

    if home > 55:
        return "strong_home_favorite"
    elif away > 55:
        return "strong_away_favorite"
    elif home > 45:
        return "home_favorite"
    elif away > 45:
        return "away_favorite"
    elif draw > 35:
        return "balanced_draw"
    else:
        return "balanced"


def analyze_odds_changes(odds_comparison: List[Dict]) -> Dict:
    """
    Analyze odds changes between first_odds and pre_match_odds.

    Args:
        odds_comparison (list): List of company odds data

    Returns:
        dict: Odds change analysis
    """
    try:
        home_changes = []
        draw_changes = []
        away_changes = []
        companies_changed = 0

        significant_home_drops = 0
        significant_draw_drops = 0
        significant_away_drops = 0

        for company in odds_comparison:
            european_odds = company.get('european_odds', {})

            first_odds = european_odds.get('first_odds', {})
            pre_match_odds = european_odds.get('pre_match_odds', {})

            has_changed = european_odds.get('has_changed', False)

            if has_changed and first_odds and pre_match_odds:
                companies_changed += 1

                # Calculate percentage changes
                for outcome in ['home', 'draw', 'away']:
                    first_val = first_odds.get(outcome)
                    pre_val = pre_match_odds.get(outcome)

                    if first_val and pre_val:
                        try:
                            first_val = float(first_val)
                            pre_val = float(pre_val)

                            if first_val > 1.01:  # Avoid extreme odds
                                change_pct = ((pre_val - first_val) / first_val) * 100

                                if outcome == 'home':
                                    home_changes.append(change_pct)
                                    if change_pct < -10:  # Significant drop
                                        significant_home_drops += 1
                                elif outcome == 'draw':
                                    draw_changes.append(change_pct)
                                    if change_pct < -10:
                                        significant_draw_drops += 1
                                else:  # away
                                    away_changes.append(change_pct)
                                    if change_pct < -10:
                                        significant_away_drops += 1
                        except (ValueError, TypeError):
                            continue

        # Calculate averages
        avg_home_change = sum(home_changes) / len(home_changes) if home_changes else 0
        avg_draw_change = sum(draw_changes) / len(draw_changes) if draw_changes else 0
        avg_away_change = sum(away_changes) / len(away_changes) if away_changes else 0

        return {
            "available": True,
            "companies_changed": companies_changed,
            "change_percentage": round((companies_changed / len(odds_comparison)) * 100, 1),
            "significant_changes": {
                "home_drop_over_10_percent": significant_home_drops,
                "draw_drop_over_10_percent": significant_draw_drops,
                "away_drop_over_10_percent": significant_away_drops
            },
            "average_changes": {
                "home_change_percent": round(avg_home_change, 1),
                "draw_change_percent": round(avg_draw_change, 1),
                "away_change_percent": round(avg_away_change, 1)
            },
            "trend_analysis": analyze_change_trends(avg_home_change, avg_draw_change, avg_away_change)
        }

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in odds changes analysis: {str(e)}")
        return {"available": False, "error": str(e)}


def analyze_change_trends(home_change: float, draw_change: float, away_change: float) -> str:
    """Analyze overall trend from odds changes."""
    # If odds are dropping significantly, it indicates increased confidence
    significant_drop_threshold = -5.0

    if home_change < significant_drop_threshold and away_change > -significant_drop_threshold:
        return "increasing_home_confidence"
    elif away_change < significant_drop_threshold and home_change > -significant_drop_threshold:
        return "increasing_away_confidence"
    elif draw_change < significant_drop_threshold:
        return "increasing_draw_confidence"
    else:
        return "stable_market"


def analyze_goal_line_expectations(odds_comparison: List[Dict]) -> Dict:
    """
    Analyze goal line changes and market expectations for total goals.

    Args:
        odds_comparison (list): List of company odds data

    Returns:
        dict: Goal line analysis results
    """
    try:
        opening_lines = []
        current_lines = []
        changes = []
        increased_count = 0
        decreased_count = 0
        unchanged_count = 0

        for company in odds_comparison:
            over_under = company.get('over_under', {})

            first_line = over_under.get('first_odds', {}).get('line')
            pre_match_line = over_under.get('pre_match_odds', {}).get('line')
            has_changed = over_under.get('has_changed', False)

            if first_line and pre_match_line:
                try:
                    first_val = float(first_line)
                    pre_val = float(pre_match_line)

                    opening_lines.append(first_val)
                    current_lines.append(pre_val)

                    change = pre_val - first_val
                    changes.append(change)

                    if has_changed:
                        if change > 0.1:  # Increased by more than 0.1
                            increased_count += 1
                        elif change < -0.1:  # Decreased by more than 0.1
                            decreased_count += 1
                        else:
                            unchanged_count += 1

                except (ValueError, TypeError):
                    continue

        if not opening_lines:
            return {"available": False}

        avg_opening = sum(opening_lines) / len(opening_lines)
        avg_current = sum(current_lines) / len(current_lines)
        avg_change = sum(changes) / len(changes)

        # Determine trend
        if avg_change > 0.15:
            trend = "more_goals_expected"
            confidence = "high"
        elif avg_change < -0.15:
            trend = "fewer_goals_expected"
            confidence = "high"
        elif abs(avg_change) > 0.05:
            trend = "moderate_change"
            confidence = "medium"
        else:
            trend = "stable_expectations"
            confidence = "low"

        return {
            "available": True,
            "companies_analyzed": len(opening_lines),
            "market_expectations": {
                "opening_goal_expectation": round(avg_opening, 2),
                "current_goal_expectation": round(avg_current, 2),
                "expected_goals_change": round(avg_change, 2),
                "trend": trend,
                "confidence": confidence
            },
            "line_movements": {
                "increased_count": increased_count,
                "decreased_count": decreased_count,
                "unchanged_count": unchanged_count,
                "total_changed": increased_count + decreased_count,
                "change_percentage": round(((increased_count + decreased_count) / len(opening_lines)) * 100, 1)
            },
            "goal_probabilities": calculate_goal_probabilities(avg_current)
        }

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in goal line analysis: {str(e)}")
        return {"available": False, "error": str(e)}


def calculate_goal_probabilities(avg_goal_line: float) -> Dict:
    """Calculate goal probabilities based on goal line."""
    # Simple probability calculation based on goal line
    # Goal line represents the market's expectation

    if avg_goal_line <= 2.0:
        under_prob = 70.0
        over_prob = 30.0
    elif avg_goal_line <= 2.25:
        under_prob = 60.0
        over_prob = 40.0
    elif avg_goal_line <= 2.5:
        under_prob = 50.0
        over_prob = 50.0
    elif avg_goal_line <= 2.75:
        under_prob = 40.0
        over_prob = 60.0
    elif avg_goal_line <= 3.0:
        under_prob = 30.0
        over_prob = 70.0
    else:
        under_prob = 20.0
        over_prob = 80.0

    return {
        f"under_{avg_goal_line}": round(under_prob, 1),
        f"over_{avg_goal_line}": round(over_prob, 1),
        "expected_goals": round(avg_goal_line, 2)
    }


def analyze_asian_handicap_trends(odds_comparison: List[Dict]) -> Dict:
    """
    Analyze Asian handicap line movements and trends.

    Args:
        odds_comparison (list): List of company odds data

    Returns:
        dict: Asian handicap analysis results
    """
    try:
        line_changes = []
        increased_count = 0
        decreased_count = 0
        unchanged_count = 0

        for company in odds_comparison:
            asian_handicap = company.get('asian_handicap', {})

            first_line = asian_handicap.get('first_odds', {}).get('line')
            pre_match_line = asian_handicap.get('pre_match_odds', {}).get('line')
            has_changed = asian_handicap.get('has_changed', False)

            if first_line and pre_match_line:
                try:
                    first_val = float(first_line)
                    pre_val = float(pre_match_line)

                    change = pre_val - first_val
                    line_changes.append(change)

                    if has_changed:
                        if change > 0.1:
                            increased_count += 1
                        elif change < -0.1:
                            decreased_count += 1
                        else:
                            unchanged_count += 1

                except (ValueError, TypeError):
                    continue

        if not line_changes:
            return {"available": False}

        avg_change = sum(line_changes) / len(line_changes)

        # Determine trend
        if abs(avg_change) < 0.05:
            trend = "stable"
        elif avg_change > 0.1:
            trend = "increasing_home_advantage"
        elif avg_change < -0.1:
            trend = "increasing_away_advantage"
        else:
            trend = "minor_adjustments"

        return {
            "available": True,
            "companies_analyzed": len(line_changes),
            "line_movements": {
                "increased_count": increased_count,
                "decreased_count": decreased_count,
                "unchanged_count": unchanged_count,
                "total_changed": increased_count + decreased_count,
                "change_percentage": round(((increased_count + decreased_count) / len(line_changes)) * 100, 1)
            },
            "trend_analysis": {
                "average_change": round(avg_change, 2),
                "trend": trend,
                "volatility": "high" if abs(avg_change) > 0.25 else "medium" if abs(avg_change) > 0.1 else "low"
            }
        }

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in asian handicap analysis: {str(e)}")
        return {"available": False, "error": str(e)}


def calculate_company_statistics(odds_comparison: List[Dict]) -> Dict:
    """
    Calculate statistics about company behavior and changes.

    Args:
        odds_comparison (list): List of company odds data

    Returns:
        dict: Company statistics
    """
    try:
        total_companies = len(odds_comparison)
        companies_changed_european = 0
        companies_changed_goal_line = 0
        companies_changed_asian = 0

        for company in odds_comparison:
            # European odds changes
            if company.get('european_odds', {}).get('has_changed', False):
                companies_changed_european += 1

            # Goal line changes
            if company.get('over_under', {}).get('has_changed', False):
                companies_changed_goal_line += 1

            # Asian handicap changes
            if company.get('asian_handicap', {}).get('has_changed', False):
                companies_changed_asian += 1

        return {
            "total_companies": total_companies,
            "odds_type_changes": {
                "european_odds_changed": companies_changed_european,
                "goal_line_changed": companies_changed_goal_line,
                "asian_handicap_changed": companies_changed_asian
            },
            "change_rates": {
                "european_change_rate": round((companies_changed_european / total_companies) * 100, 1),
                "goal_line_change_rate": round((companies_changed_goal_line / total_companies) * 100, 1),
                "asian_change_rate": round((companies_changed_asian / total_companies) * 100, 1)
            },
            "market_activity": determine_market_activity(companies_changed_european, companies_changed_goal_line, companies_changed_asian, total_companies)
        }

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in company statistics: {str(e)}")
        return {"error": str(e)}


def determine_market_activity(european_changed: int, goal_changed: int, asian_changed: int, total: int) -> str:
    """Determine market activity level."""
    avg_change_rate = ((european_changed + goal_changed + asian_changed) / 3) / total

    if avg_change_rate > 0.8:
        return "highly_active"
    elif avg_change_rate > 0.6:
        return "active"
    elif avg_change_rate > 0.3:
        return "moderate"
    else:
        return "stable"


def analyze_first_half_odds_comprehensive(first_half_odds: List[Dict]) -> Dict:
    """
    Comprehensive first half odds analysis including 1x2 percentages, odds movements,
    goal line trends, and asian handicap analysis for first half.

    Args:
        first_half_odds (list): First half odds comparison data

    Returns:
        dict: Complete first half odds analysis results
    """
    try:
        if not first_half_odds:
            return {"available": False, "reason": "no_first_half_data"}

        analysis = {
            "available": True,
            "total_companies": len(first_half_odds),
            "ht_1x2_analysis": calculate_ht_1x2_analysis(first_half_odds),
            "ht_odds_changes": analyze_ht_odds_changes(first_half_odds),
            "ht_goal_line_analysis": analyze_ht_goal_line_expectations(first_half_odds),
            "ht_asian_handicap_analysis": analyze_ht_asian_handicap_trends(first_half_odds),
            "ht_company_statistics": calculate_ht_company_statistics(first_half_odds)
        }

        return analysis

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in first half odds analysis: {str(e)}")
        return {"available": False, "error": str(e)}


def calculate_ht_1x2_analysis(first_half_odds: List[Dict]) -> Dict:
    """
    Calculate first half 1x2 odds analysis with percentages and normalization.

    Args:
        first_half_odds (list): List of first half company odds data

    Returns:
        dict: HT 1x2 analysis results
    """
    try:
        home_odds = []
        draw_odds = []
        away_odds = []

        for company in first_half_odds:
            european_odds = company.get('european_odds', {}).get('pre_match_odds', {})

            home_odd = european_odds.get('home')
            draw_odd = european_odds.get('draw')
            away_odd = european_odds.get('away')

            if home_odd and draw_odd and away_odd:
                try:
                    home_odds.append(float(home_odd))
                    draw_odds.append(float(draw_odd))
                    away_odds.append(float(away_odd))
                except (ValueError, TypeError):
                    continue

        if not home_odds:
            return {"available": False}

        # Raw averages
        avg_home = sum(home_odds) / len(home_odds)
        avg_draw = sum(draw_odds) / len(draw_odds)
        avg_away = sum(away_odds) / len(away_odds)

        # Total for percentage calculation
        total_avg = avg_home + avg_draw + avg_away

        # Normalized percentages (HT için farklı normalizasyon - daha dengeli)
        home_percent = (avg_home / total_avg) * 100
        draw_percent = (avg_draw / total_avg) * 100
        away_percent = (avg_away / total_avg) * 100

        # HT için daha yumuşak normalizasyon (ilk yarı daha öngörülemez)
        normalized_percentages = smart_normalize_ht_percentages(home_percent, draw_percent, away_percent)

        return {
            "available": True,
            "companies_analyzed": len(home_odds),
            "raw_averages": {
                "home": round(avg_home, 2),
                "draw": round(avg_draw, 2),
                "away": round(avg_away, 2)
            },
            "normalized_percentages": {
                "home": round(normalized_percentages['home'], 1),
                "draw": round(normalized_percentages['draw'], 1),
                "away": round(normalized_percentages['away'], 1)
            },
            "market_bias": determine_ht_market_bias(normalized_percentages)
        }

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in HT 1x2 analysis: {str(e)}")
        return {"available": False, "error": str(e)}


def smart_normalize_ht_percentages(home_pct: float, draw_pct: float, away_pct: float) -> Dict[str, float]:
    """
    Smart normalization for HT odds (first half is more unpredictable).

    Args:
        home_pct, draw_pct, away_pct: Raw percentages

    Returns:
        dict: Normalized percentages for HT
    """
    # Find the maximum percentage
    max_pct = max(home_pct, draw_pct, away_pct)

    # For HT, allow higher maximums (HT is more balanced)
    if max_pct > 65:
        # Apply softer adjustment
        target_max = 60.0
        adjustment = (max_pct - target_max) * 0.4  # Reduce by 40% of excess

        if home_pct == max_pct:
            home_pct -= adjustment
            draw_pct += adjustment * 0.3
            away_pct += adjustment * 0.7
        elif draw_pct == max_pct:
            draw_pct -= adjustment
            home_pct += adjustment * 0.5
            away_pct += adjustment * 0.5
        else:  # away_pct == max_pct
            away_pct -= adjustment
            home_pct += adjustment * 0.7
            draw_pct += adjustment * 0.3

    # Ensure minimum percentages (HT için daha yüksek minimum)
    min_allowed = 8.0  # HT'de draw daha olası
    if home_pct < min_allowed:
        home_pct = min_allowed
    if draw_pct < min_allowed:
        draw_pct = min_allowed
    if away_pct < min_allowed:
        away_pct = min_allowed

    # Renormalize to ensure sum = 100
    total = home_pct + draw_pct + away_pct
    if total != 100:
        factor = 100 / total
        home_pct *= factor
        draw_pct *= factor
        away_pct *= factor

    return {
        'home': home_pct,
        'draw': draw_pct,
        'away': away_pct
    }


def determine_ht_market_bias(percentages: Dict[str, float]) -> str:
    """Determine market bias for HT odds."""
    home = percentages['home']
    draw = percentages['draw']
    away = percentages['away']

    if home > 50:
        return "strong_home_favorite_ht"
    elif away > 50:
        return "strong_away_favorite_ht"
    elif home > 40:
        return "home_favorite_ht"
    elif away > 40:
        return "away_favorite_ht"
    elif draw > 40:
        return "balanced_draw_ht"
    else:
        return "balanced_ht"


def analyze_ht_odds_changes(first_half_odds: List[Dict]) -> Dict:
    """
    Analyze HT odds changes between first_odds and pre_match_odds.

    Args:
        first_half_odds (list): List of HT company odds data

    Returns:
        dict: HT odds change analysis
    """
    try:
        home_changes = []
        draw_changes = []
        away_changes = []
        companies_changed = 0

        significant_home_drops = 0
        significant_draw_drops = 0
        significant_away_drops = 0

        for company in first_half_odds:
            european_odds = company.get('european_odds', {})

            first_odds = european_odds.get('first_odds', {})
            pre_match_odds = european_odds.get('pre_match_odds', {})

            has_changed = european_odds.get('has_changed', False)

            if has_changed and first_odds and pre_match_odds:
                companies_changed += 1

                # Calculate percentage changes
                for outcome in ['home', 'draw', 'away']:
                    first_val = first_odds.get(outcome)
                    pre_val = pre_match_odds.get(outcome)

                    if first_val and pre_val:
                        try:
                            first_val = float(first_val)
                            pre_val = float(pre_val)

                            if first_val > 1.01:  # Avoid extreme odds
                                change_pct = ((pre_val - first_val) / first_val) * 100

                                if outcome == 'home':
                                    home_changes.append(change_pct)
                                    if change_pct < -8:  # Significant drop (HT için daha düşük threshold)
                                        significant_home_drops += 1
                                elif outcome == 'draw':
                                    draw_changes.append(change_pct)
                                    if change_pct < -8:
                                        significant_draw_drops += 1
                                else:  # away
                                    away_changes.append(change_pct)
                                    if change_pct < -8:
                                        significant_away_drops += 1
                        except (ValueError, TypeError):
                            continue

        # Calculate averages
        avg_home_change = sum(home_changes) / len(home_changes) if home_changes else 0
        avg_draw_change = sum(draw_changes) / len(draw_changes) if draw_changes else 0
        avg_away_change = sum(away_changes) / len(away_changes) if away_changes else 0

        return {
            "available": True,
            "companies_changed": companies_changed,
            "change_percentage": round((companies_changed / len(first_half_odds)) * 100, 1),
            "significant_changes": {
                "home_drop_over_8_percent": significant_home_drops,
                "draw_drop_over_8_percent": significant_draw_drops,
                "away_drop_over_8_percent": significant_away_drops
            },
            "average_changes": {
                "home_change_percent": round(avg_home_change, 1),
                "draw_change_percent": round(avg_draw_change, 1),
                "away_change_percent": round(avg_away_change, 1)
            },
            "trend_analysis": analyze_ht_change_trends(avg_home_change, avg_draw_change, avg_away_change)
        }

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in HT odds changes analysis: {str(e)}")
        return {"available": False, "error": str(e)}


def analyze_ht_change_trends(home_change: float, draw_change: float, away_change: float) -> str:
    """Analyze overall HT trend from odds changes."""
    significant_drop_threshold = -6.0  # HT için daha düşük threshold

    if home_change < significant_drop_threshold and away_change > -significant_drop_threshold:
        return "increasing_home_confidence_ht"
    elif away_change < significant_drop_threshold and home_change > -significant_drop_threshold:
        return "increasing_away_confidence_ht"
    elif draw_change < significant_drop_threshold:
        return "increasing_draw_confidence_ht"
    else:
        return "stable_market_ht"


def analyze_ht_goal_line_expectations(first_half_odds: List[Dict]) -> Dict:
    """
    Analyze HT goal line changes and market expectations for half-time goals.

    Args:
        first_half_odds (list): List of HT company odds data

    Returns:
        dict: HT goal line analysis results
    """
    try:
        opening_lines = []
        current_lines = []
        changes = []
        increased_count = 0
        decreased_count = 0
        unchanged_count = 0

        for company in first_half_odds:
            over_under = company.get('over_under', {})

            first_line = over_under.get('first_odds', {}).get('line')
            pre_match_line = over_under.get('pre_match_odds', {}).get('line')
            has_changed = over_under.get('has_changed', False)

            if first_line and pre_match_line:
                try:
                    first_val = float(first_line)
                    pre_val = float(pre_match_line)

                    opening_lines.append(first_val)
                    current_lines.append(pre_val)

                    change = pre_val - first_val
                    changes.append(change)

                    if has_changed:
                        if change > 0.1:  # Increased by more than 0.1
                            increased_count += 1
                        elif change < -0.1:  # Decreased by more than 0.1
                            decreased_count += 1
                        else:
                            unchanged_count += 1

                except (ValueError, TypeError):
                    continue

        if not opening_lines:
            return {"available": False}

        avg_opening = sum(opening_lines) / len(opening_lines)
        avg_current = sum(current_lines) / len(current_lines)
        avg_change = sum(changes) / len(changes)

        # Determine HT trend (HT'de gol beklentileri daha düşüktür)
        if avg_change > 0.1:
            trend = "more_ht_goals_expected"
            confidence = "medium"
        elif avg_change < -0.1:
            trend = "fewer_ht_goals_expected"
            confidence = "medium"
        elif abs(avg_change) > 0.05:
            trend = "minor_ht_change"
            confidence = "low"
        else:
            trend = "stable_ht_goals"
            confidence = "low"

        return {
            "available": True,
            "companies_analyzed": len(opening_lines),
            "ht_market_expectations": {
                "opening_ht_goal_expectation": round(avg_opening, 2),
                "current_ht_goal_expectation": round(avg_current, 2),
                "expected_ht_goals_change": round(avg_change, 2),
                "trend": trend,
                "confidence": confidence
            },
            "ht_line_movements": {
                "increased_count": increased_count,
                "decreased_count": decreased_count,
                "unchanged_count": unchanged_count,
                "total_changed": increased_count + decreased_count,
                "change_percentage": round(((increased_count + decreased_count) / len(opening_lines)) * 100, 1)
            },
            "ht_goal_probabilities": calculate_ht_goal_probabilities(avg_current)
        }

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in HT goal line analysis: {str(e)}")
        return {"available": False, "error": str(e)}


def calculate_ht_goal_probabilities(avg_ht_goal_line: float) -> Dict:
    """Calculate HT goal probabilities based on HT goal line."""
    # HT için farklı probability hesaplaması (daha az gol)

    if avg_ht_goal_line <= 0.75:
        under_prob = 75.0
        over_prob = 25.0
    elif avg_ht_goal_line <= 1.0:
        under_prob = 65.0
        over_prob = 35.0
    elif avg_ht_goal_line <= 1.25:
        under_prob = 55.0
        over_prob = 45.0
    elif avg_ht_goal_line <= 1.5:
        under_prob = 45.0
        over_prob = 55.0
    else:
        under_prob = 35.0
        over_prob = 65.0

    return {
        f"ht_under_{avg_ht_goal_line}": round(under_prob, 1),
        f"ht_over_{avg_ht_goal_line}": round(over_prob, 1),
        "expected_ht_goals": round(avg_ht_goal_line, 2)
    }


def analyze_ht_asian_handicap_trends(first_half_odds: List[Dict]) -> Dict:
    """
    Analyze HT Asian handicap line movements and trends.

    Args:
        first_half_odds (list): List of HT company odds data

    Returns:
        dict: HT Asian handicap analysis results
    """
    try:
        line_changes = []
        increased_count = 0
        decreased_count = 0
        unchanged_count = 0

        for company in first_half_odds:
            asian_handicap = company.get('asian_handicap', {})

            first_line = asian_handicap.get('first_odds', {}).get('line')
            pre_match_line = asian_handicap.get('pre_match_odds', {}).get('line')
            has_changed = asian_handicap.get('has_changed', False)

            if first_line and pre_match_line:
                try:
                    first_val = float(first_line)
                    pre_val = float(pre_match_line)

                    change = pre_val - first_val
                    line_changes.append(change)

                    if has_changed:
                        if change > 0.1:
                            increased_count += 1
                        elif change < -0.1:
                            decreased_count += 1
                        else:
                            unchanged_count += 1

                except (ValueError, TypeError):
                    continue

        if not line_changes:
            return {"available": False}

        avg_change = sum(line_changes) / len(line_changes)

        # Determine HT trend
        if abs(avg_change) < 0.05:
            trend = "stable_ht"
        elif avg_change > 0.1:
            trend = "increasing_home_advantage_ht"
        elif avg_change < -0.1:
            trend = "increasing_away_advantage_ht"
        else:
            trend = "minor_ht_adjustments"

        return {
            "available": True,
            "companies_analyzed": len(line_changes),
            "ht_line_movements": {
                "increased_count": increased_count,
                "decreased_count": decreased_count,
                "unchanged_count": unchanged_count,
                "total_changed": increased_count + decreased_count,
                "change_percentage": round(((increased_count + decreased_count) / len(line_changes)) * 100, 1)
            },
            "ht_trend_analysis": {
                "average_change": round(avg_change, 2),
                "trend": trend,
                "volatility": "high" if abs(avg_change) > 0.2 else "medium" if abs(avg_change) > 0.1 else "low"
            }
        }

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in HT asian handicap analysis: {str(e)}")
        return {"available": False, "error": str(e)}


def calculate_ht_company_statistics(first_half_odds: List[Dict]) -> Dict:
    """
    Calculate statistics about HT company behavior and changes.

    Args:
        first_half_odds (list): List of HT company odds data

    Returns:
        dict: HT company statistics
    """
    try:
        total_companies = len(first_half_odds)
        companies_changed_european = 0
        companies_changed_goal_line = 0
        companies_changed_asian = 0

        for company in first_half_odds:
            # European odds changes
            if company.get('european_odds', {}).get('has_changed', False):
                companies_changed_european += 1

            # Goal line changes
            if company.get('over_under', {}).get('has_changed', False):
                companies_changed_goal_line += 1

            # Asian handicap changes
            if company.get('asian_handicap', {}).get('has_changed', False):
                companies_changed_asian += 1

        return {
            "total_companies": total_companies,
            "ht_odds_type_changes": {
                "european_odds_changed": companies_changed_european,
                "goal_line_changed": companies_changed_goal_line,
                "asian_handicap_changed": companies_changed_asian
            },
            "ht_change_rates": {
                "european_change_rate": round((companies_changed_european / total_companies) * 100, 1),
                "goal_line_change_rate": round((companies_changed_goal_line / total_companies) * 100, 1),
                "asian_change_rate": round((companies_changed_asian / total_companies) * 100, 1)
            },
            "ht_market_activity": determine_ht_market_activity(companies_changed_european, companies_changed_goal_line, companies_changed_asian, total_companies)
        }

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in HT company statistics: {str(e)}")
        return {"error": str(e)}


def determine_ht_market_activity(european_changed: int, goal_changed: int, asian_changed: int, total: int) -> str:
    """Determine HT market activity level."""
    avg_change_rate = ((european_changed + goal_changed + asian_changed) / 3) / total

    if avg_change_rate > 0.75:
        return "highly_active_ht"
    elif avg_change_rate > 0.5:
        return "active_ht"
    elif avg_change_rate > 0.25:
        return "moderate_ht"
    else:
        return "stable_ht"
