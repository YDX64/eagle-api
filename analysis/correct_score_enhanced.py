"""
Enhanced Correct Score Prediction - 5-Source Ensemble Model

Combines five independent prediction sources with adaptive weighting:
  1. Dixon-Coles Poisson (rho-corrected for low-scoring games)
  2. H2H Scoreline Frequency (exponential time decay)
  3. Recent Form Lambda (EMA-based attack/defense strengths)
  4. Bookmaker Correct Score Odds (vig-removed, multi-company average)
  5. Common Scorelines Prior (Bayesian prior from all recent matches)

Key improvements over v1:
  - All sources produce proper normalized probabilities (sum to 1)
  - Exponential time decay on historical data (xi=0.012)
  - EMA-based form analysis (alpha=0.3) for home/away specific matches
  - Dynamic league average from actual data (not fixed 1.3)
  - Adaptive weight redistribution when sources are unavailable
  - H2H scoreline flipping when home/away roles reversed
  - Confidence score based on data richness and source agreement

References:
  Dixon & Coles (1997) "Modelling Association Football Scores"
  Rue & Salvesen (2000) "Prediction and Retrospective Analysis of Soccer Matches"
"""

import math
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any
from collections import Counter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_RHO = -0.13          # Dixon-Coles correlation parameter
MAX_GOALS = 8                # Maximum goals per team in score matrix
DEFAULT_LEAGUE_AVG = 1.35    # Fallback league average goals per team
EMA_ALPHA = 0.3              # Exponential moving average decay for form
TIME_DECAY_XI = 0.012        # Exponential time decay rate (days)
MIN_PROBABILITY = 1e-8       # Floor to avoid log(0) in blending

# Ensemble weights (must sum to 1.0)
BASE_WEIGHTS = {
    'dixon_coles':    0.25,
    'h2h_frequency':  0.15,
    'form_poisson':   0.20,
    'bookmaker':      0.30,
    'common_scores':  0.10,
}


# ---------------------------------------------------------------------------
# Utility: Poisson & Dixon-Coles
# ---------------------------------------------------------------------------

def poisson_pmf(lam: float, k: int) -> float:
    """Poisson probability mass function P(X=k | lambda)."""
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    if k < 0:
        return 0.0
    try:
        return (lam ** k) * math.exp(-lam) / math.factorial(k)
    except (OverflowError, ValueError):
        return 0.0


def dixon_coles_tau(hg: int, ag: int, lam_h: float, lam_a: float, rho: float) -> float:
    """
    Dixon-Coles tau correction factor.
    Only adjusts (0,0), (0,1), (1,0), (1,1) scorelines.
    """
    if hg == 0 and ag == 0:
        return 1.0 - lam_h * lam_a * rho
    if hg == 0 and ag == 1:
        return 1.0 + lam_h * rho
    if hg == 1 and ag == 0:
        return 1.0 + lam_a * rho
    if hg == 1 and ag == 1:
        return 1.0 - rho
    return 1.0


def build_score_matrix(lam_h: float, lam_a: float, rho: float = DEFAULT_RHO,
                       max_goals: int = MAX_GOALS) -> Dict[str, float]:
    """
    Build a full score probability matrix using Dixon-Coles model.
    Returns normalized dict of "h:a" -> probability (0-1 range, sums to 1).
    """
    raw: Dict[str, float] = {}
    total = 0.0

    for h in range(max_goals + 1):
        p_h = poisson_pmf(lam_h, h)
        for a in range(max_goals + 1):
            p_a = poisson_pmf(lam_a, a)
            tau = dixon_coles_tau(h, a, lam_h, lam_a, rho)
            prob = max(0.0, tau * p_h * p_a)
            key = f"{h}:{a}"
            raw[key] = prob
            total += prob

    # Normalize
    if total > 0:
        return {k: v / total for k, v in raw.items()}
    return raw


# ---------------------------------------------------------------------------
# Utility: Time Decay
# ---------------------------------------------------------------------------

def time_decay_weight(days_ago: float, xi: float = TIME_DECAY_XI) -> float:
    """Exponential time decay: recent matches weighted more heavily."""
    return math.exp(-xi * max(0.0, days_ago))


def parse_match_date(date_str: str) -> Optional[datetime]:
    """Parse date string from H2H data. Handles multiple formats."""
    if not date_str:
        return None
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d', '%d/%m/%Y', '%d.%m.%Y'):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except (ValueError, TypeError):
            continue
    return None


def parse_score(score_str: str) -> Optional[Tuple[int, int]]:
    """Parse score string like '2-1' or '2:1' into (home_goals, away_goals)."""
    if not score_str or not isinstance(score_str, str):
        return None
    score_str = score_str.strip()
    for sep in ('-', ':'):
        if sep in score_str:
            parts = score_str.split(sep)
            if len(parts) == 2:
                try:
                    return int(parts[0].strip()), int(parts[1].strip())
                except (ValueError, TypeError):
                    continue
    return None


def days_since(date_str: str, reference: Optional[datetime] = None) -> float:
    """Calculate days between a date string and now (or reference)."""
    dt = parse_match_date(date_str)
    if not dt:
        return 180.0  # Default penalty for unparseable dates
    ref = reference or datetime.now()
    delta = (ref - dt).total_seconds() / 86400.0
    return max(0.0, delta)


# ---------------------------------------------------------------------------
# Source 1: Dixon-Coles Poisson
# ---------------------------------------------------------------------------

def source_dixon_coles(match_data: Dict) -> Optional[Dict[str, float]]:
    """
    Dixon-Coles model using Poisson xG as lambda source.
    Falls back to H2H-derived lambdas if Poisson xG unavailable.
    """
    lam_h, lam_a = _extract_poisson_lambdas(match_data)
    if lam_h is None or lam_a is None:
        return None

    probs = build_score_matrix(lam_h, lam_a, DEFAULT_RHO)
    return probs


def _extract_poisson_lambdas(match_data: Dict) -> Tuple[Optional[float], Optional[float]]:
    """Get lambda values from Poisson predictions."""
    poisson = match_data.get('analysis', {}).get('poisson_predictions', {})
    if poisson:
        xg = poisson.get('expected_goals', {})
        h = xg.get('home')
        a = xg.get('away')
        if h is not None and a is not None:
            try:
                h_val = float(h)
                a_val = float(a)
                if 0.1 <= h_val <= 5.0 and 0.1 <= a_val <= 5.0:
                    return h_val, a_val
            except (ValueError, TypeError):
                pass
    return None, None


# ---------------------------------------------------------------------------
# Source 2: H2H Scoreline Frequency
# ---------------------------------------------------------------------------

def source_h2h_frequency(match_data: Dict) -> Optional[Dict[str, float]]:
    """
    Analyze direct H2H matches for scoreline frequency.
    Applies exponential time decay and flips scores when home/away roles reversed.
    """
    h2h = match_data.get('h2h_details', {})
    match_info = match_data.get('match_info', {})
    home_team = match_info.get('home_team_name', '')
    away_team = match_info.get('away_team_name', '')

    if not home_team or not away_team:
        return None

    h2h_matches = h2h.get('h2h_matches', [])
    if not h2h_matches or len(h2h_matches) < 2:
        return None

    now = datetime.now()
    weighted_scores: Dict[str, float] = {}
    total_weight = 0.0

    for m in h2h_matches:
        score_str = m.get('score', '')
        parsed = parse_score(score_str)
        if parsed is None:
            continue

        h_goals, a_goals = parsed
        match_home = (m.get('home_team') or '').strip()
        date_str = m.get('date', '')
        d_ago = days_since(date_str, now)
        w = time_decay_weight(d_ago)

        # Flip score if current home team was the away team in this H2H match
        if match_home and match_home != home_team:
            h_goals, a_goals = a_goals, h_goals

        key = f"{h_goals}:{a_goals}"
        weighted_scores[key] = weighted_scores.get(key, 0.0) + w
        total_weight += w

    if total_weight <= 0 or len(weighted_scores) < 1:
        return None

    # Normalize to probabilities
    probs = {k: v / total_weight for k, v in weighted_scores.items()}

    # Smooth with a uniform prior over common scores to avoid sparsity
    smoothed = _smooth_sparse_distribution(probs, alpha=0.3)
    return smoothed


def _smooth_sparse_distribution(probs: Dict[str, float], alpha: float = 0.3) -> Dict[str, float]:
    """
    Smooth a sparse scoreline distribution by mixing with a uniform prior
    over all scores 0:0 through MAX_GOALS:MAX_GOALS.

    alpha controls the smoothing: 0 = no smoothing, 1 = uniform.
    """
    n_scores = (MAX_GOALS + 1) ** 2
    uniform_p = 1.0 / n_scores
    smoothed: Dict[str, float] = {}
    total = 0.0

    for h in range(MAX_GOALS + 1):
        for a in range(MAX_GOALS + 1):
            key = f"{h}:{a}"
            empirical = probs.get(key, 0.0)
            p = (1.0 - alpha) * empirical + alpha * uniform_p
            smoothed[key] = p
            total += p

    # Normalize
    if total > 0:
        return {k: v / total for k, v in smoothed.items()}
    return smoothed


# ---------------------------------------------------------------------------
# Source 3: Recent Form Lambda (EMA-based)
# ---------------------------------------------------------------------------

def source_form_poisson(match_data: Dict) -> Optional[Dict[str, float]]:
    """
    Derive lambdas from recent form using Exponential Moving Average.
    Home team: only HOME matches. Away team: only AWAY matches.
    Then produce a Dixon-Coles score matrix from form-derived lambdas.
    """
    h2h = match_data.get('h2h_details', {})
    match_info = match_data.get('match_info', {})
    home_team = match_info.get('home_team_name', '')
    away_team = match_info.get('away_team_name', '')

    if not home_team or not away_team:
        return None

    home_matches = h2h.get('home_team_previous_matches', [])
    away_matches = h2h.get('away_team_previous_matches', [])

    if len(home_matches) < 3 or len(away_matches) < 3:
        return None

    now = datetime.now()

    # Home team stats from HOME matches only
    home_scored_ema, home_conceded_ema, home_count, league_goals_h = _compute_form_ema(
        home_matches, home_team, venue='home', reference=now
    )
    # Away team stats from AWAY matches only
    away_scored_ema, away_conceded_ema, away_count, league_goals_a = _compute_form_ema(
        away_matches, away_team, venue='away', reference=now
    )

    if home_count < 2 or away_count < 2:
        # Fall back to all matches if venue-specific data is insufficient
        home_scored_ema, home_conceded_ema, home_count, league_goals_h = _compute_form_ema(
            home_matches, home_team, venue='all', reference=now
        )
        away_scored_ema, away_conceded_ema, away_count, league_goals_a = _compute_form_ema(
            away_matches, away_team, venue='all', reference=now
        )

    if home_count < 2 or away_count < 2:
        return None

    # Dynamic league average from observed data
    all_league_goals = league_goals_h + league_goals_a
    if all_league_goals:
        league_avg = sum(all_league_goals) / len(all_league_goals)
        league_avg = max(0.8, min(2.0, league_avg))  # Clamp to reasonable range
    else:
        league_avg = DEFAULT_LEAGUE_AVG

    # Attack & defense strengths
    h_attack = home_scored_ema / league_avg if league_avg > 0 else 1.0
    h_defense = home_conceded_ema / league_avg if league_avg > 0 else 1.0
    a_attack = away_scored_ema / league_avg if league_avg > 0 else 1.0
    a_defense = away_conceded_ema / league_avg if league_avg > 0 else 1.0

    # Form-derived lambdas
    lam_h = h_attack * a_defense * league_avg
    lam_a = a_attack * h_defense * league_avg

    # Clamp
    lam_h = max(0.3, min(4.5, lam_h))
    lam_a = max(0.3, min(4.5, lam_a))

    probs = build_score_matrix(lam_h, lam_a, DEFAULT_RHO)
    return probs


def _compute_form_ema(
    matches: List[Dict],
    team_name: str,
    venue: str = 'all',
    reference: Optional[datetime] = None,
    max_matches: int = 10,
) -> Tuple[float, float, int, List[float]]:
    """
    Compute EMA of goals scored and conceded for a team from recent matches.

    Args:
        matches: List of match dicts
        team_name: Name of the team
        venue: 'home' (only matches where team was home), 'away', or 'all'
        reference: Reference datetime for time decay
        max_matches: Maximum number of matches to consider

    Returns:
        (ema_scored, ema_conceded, match_count, all_per_team_goals)
    """
    ref = reference or datetime.now()
    scored_list: List[Tuple[float, float]] = []  # (goals, time_weight)
    conceded_list: List[Tuple[float, float]] = []
    league_goals: List[float] = []

    for m in matches[:20]:  # Look at up to 20 for filtering, take max_matches
        score_str = m.get('score', '')
        parsed = parse_score(score_str)
        if parsed is None:
            continue

        h_goals, a_goals = parsed
        match_home = (m.get('home_team') or '').strip()
        match_away = (m.get('away_team') or '').strip()
        date_str = m.get('date', '')

        # Determine if team was home or away in this match
        is_home = (match_home == team_name)
        is_away = (match_away == team_name)

        if not is_home and not is_away:
            continue

        # Venue filter
        if venue == 'home' and not is_home:
            continue
        if venue == 'away' and not is_away:
            continue

        team_scored = h_goals if is_home else a_goals
        team_conceded = a_goals if is_home else h_goals

        d_ago = days_since(date_str, ref)
        tw = time_decay_weight(d_ago)

        scored_list.append((float(team_scored), tw))
        conceded_list.append((float(team_conceded), tw))

        # Per-team goals for league average
        league_goals.append(float(h_goals))
        league_goals.append(float(a_goals))

        if len(scored_list) >= max_matches:
            break

    count = len(scored_list)
    if count == 0:
        return 0.0, 0.0, 0, league_goals

    # EMA with time-weighted ordering (most recent first, they already are)
    ema_scored = _weighted_ema([s for s, _ in scored_list], [w for _, w in scored_list])
    ema_conceded = _weighted_ema([c for c, _ in conceded_list], [w for _, w in conceded_list])

    return ema_scored, ema_conceded, count, league_goals


def _weighted_ema(values: List[float], weights: List[float]) -> float:
    """
    Time-weighted EMA. The first value is the most recent.
    Combines EMA decay (alpha) with time-based weights.
    """
    if not values:
        return 0.0

    alpha = EMA_ALPHA
    ema = values[0]

    for i in range(1, len(values)):
        # Effective weight is EMA alpha combined with time decay weight ratio
        time_factor = weights[i] / weights[0] if weights[0] > 0 else 1.0
        effective_alpha = alpha * time_factor
        ema = effective_alpha * values[i] + (1.0 - effective_alpha) * ema

    return max(0.0, ema)


# ---------------------------------------------------------------------------
# Source 4: Bookmaker Odds
# ---------------------------------------------------------------------------

def source_bookmaker(match_data: Dict) -> Optional[Dict[str, float]]:
    """
    Convert bookmaker correct score odds to probabilities.
    Averages across all companies, removes vig by normalizing to sum=1.
    """
    cs_data = match_data.get('correct_score_odds', {})
    if not cs_data:
        return None

    companies = cs_data.get('correct_score_odds', [])
    if not companies:
        return None

    # Collect implied probabilities from all companies
    all_probs: Dict[str, List[float]] = {}
    valid_company_count = 0

    for company in companies:
        odds = company.get('odds', {})
        if not odds:
            continue

        company_has_valid = False
        for score_key, odds_str in odds.items():
            if not odds_str or not isinstance(odds_str, str):
                continue
            odds_str = odds_str.strip()
            if not odds_str:
                continue
            try:
                o = float(odds_str)
                if o > 1.0:
                    implied_prob = 1.0 / o
                    if score_key not in all_probs:
                        all_probs[score_key] = []
                    all_probs[score_key].append(implied_prob)
                    company_has_valid = True
            except (ValueError, ZeroDivisionError):
                continue

        if company_has_valid:
            valid_company_count += 1

    if not all_probs or valid_company_count == 0:
        return None

    # Average implied probabilities across bookmakers
    avg_probs: Dict[str, float] = {}
    total = 0.0
    for score_key, prob_list in all_probs.items():
        avg = sum(prob_list) / len(prob_list)
        avg_probs[score_key] = avg
        total += avg

    # Remove vig: normalize to sum = 1
    if total > 0:
        normalized = {k: v / total for k, v in avg_probs.items()}
    else:
        return None

    # Validate: probabilities should be reasonable
    max_prob = max(normalized.values()) if normalized else 0
    if max_prob > 0.5:
        # Something is wrong, a single score with >50% is suspicious
        logger.warning("Bookmaker source: max single score prob %.3f, may be unreliable", max_prob)

    return normalized


# ---------------------------------------------------------------------------
# Source 5: Common Scorelines Prior
# ---------------------------------------------------------------------------

def source_common_scores(match_data: Dict) -> Optional[Dict[str, float]]:
    """
    Build a Bayesian prior from the most common scorelines observed in
    all recent matches of both teams.
    """
    h2h = match_data.get('h2h_details', {})
    match_info = match_data.get('match_info', {})
    home_team = match_info.get('home_team_name', '')
    away_team = match_info.get('away_team_name', '')

    if not home_team or not away_team:
        return None

    home_matches = h2h.get('home_team_previous_matches', [])
    away_matches = h2h.get('away_team_previous_matches', [])

    if len(home_matches) < 3 and len(away_matches) < 3:
        return None

    now = datetime.now()
    score_counter: Dict[str, float] = {}
    total_weight = 0.0

    # Process home team matches (normalize scores from team's perspective as home)
    for m in home_matches[:15]:
        score_str = m.get('score', '')
        parsed = parse_score(score_str)
        if parsed is None:
            continue

        h_goals, a_goals = parsed
        match_home = (m.get('home_team') or '').strip()
        date_str = m.get('date', '')
        d_ago = days_since(date_str, now)
        w = time_decay_weight(d_ago)

        # If our home team was actually away, flip perspective to get
        # "home_team scored X, opponent scored Y" in the current match context
        if match_home != home_team:
            h_goals, a_goals = a_goals, h_goals

        # We map this to "home_scored:opponent_scored"
        key = f"{h_goals}:{a_goals}"
        score_counter[key] = score_counter.get(key, 0.0) + w
        total_weight += w

    # Process away team matches (from away perspective)
    for m in away_matches[:15]:
        score_str = m.get('score', '')
        parsed = parse_score(score_str)
        if parsed is None:
            continue

        h_goals, a_goals = parsed
        match_away = (m.get('away_team') or '').strip()
        date_str = m.get('date', '')
        d_ago = days_since(date_str, now)
        w = time_decay_weight(d_ago)

        # From the away team's perspective: they scored a_goals, conceded h_goals
        # In our output format: home_team vs away_team -> h:a
        # So away team's goals go to position 'a' (second), opponent to 'h' (first)
        if match_away == away_team:
            # away_team was away: they scored a_goals, conceded h_goals
            # map to current match: home=h_goals (opponent), away=a_goals
            key = f"{h_goals}:{a_goals}"
        else:
            # away_team was home: they scored h_goals, conceded a_goals
            # map to current match: home=a_goals (opponent), away=h_goals
            key = f"{a_goals}:{h_goals}"

        score_counter[key] = score_counter.get(key, 0.0) + w * 0.7  # Slightly lower weight for away source
        total_weight += w * 0.7

    if total_weight <= 0:
        return None

    # Normalize
    probs = {k: v / total_weight for k, v in score_counter.items()}

    # Smooth with uniform prior to cover unseen scorelines
    smoothed = _smooth_sparse_distribution(probs, alpha=0.4)
    return smoothed


# ---------------------------------------------------------------------------
# Ensemble Blending
# ---------------------------------------------------------------------------

def _compute_effective_weights(available_sources: Dict[str, Dict[str, float]]) -> Dict[str, float]:
    """
    Compute effective weights given which sources are available.
    Redistributes missing sources' weight proportionally.
    """
    available_total = sum(BASE_WEIGHTS[name] for name in available_sources)
    if available_total <= 0:
        # Uniform fallback
        n = len(available_sources)
        return {name: 1.0 / n for name in available_sources} if n > 0 else {}

    return {name: BASE_WEIGHTS[name] / available_total for name in available_sources}


def blend_distributions(sources: Dict[str, Dict[str, float]]) -> Dict[str, float]:
    """
    Blend multiple score probability distributions using weighted average.
    All input distributions must be normalized (sum to 1).
    Output is also normalized.
    """
    if not sources:
        return {}

    weights = _compute_effective_weights(sources)

    # Collect all score keys across all sources
    all_keys: set = set()
    for dist in sources.values():
        all_keys.update(dist.keys())

    blended: Dict[str, float] = {}
    total = 0.0

    for key in all_keys:
        p = 0.0
        for name, dist in sources.items():
            w = weights.get(name, 0.0)
            p += w * dist.get(key, 0.0)
        blended[key] = max(MIN_PROBABILITY, p)
        total += blended[key]

    # Normalize
    if total > 0:
        blended = {k: v / total for k, v in blended.items()}

    return blended


# ---------------------------------------------------------------------------
# Derived Predictions
# ---------------------------------------------------------------------------

def _derive_predictions(score_probs: Dict[str, float]) -> Dict:
    """Compute 1x2, goal lines, and BTTS from score probability distribution."""
    home_win = 0.0
    draw = 0.0
    away_win = 0.0
    over_15 = 0.0
    over_25 = 0.0
    over_35 = 0.0
    over_45 = 0.0
    btts_yes = 0.0

    for score_key, prob in score_probs.items():
        if ':' not in score_key:
            continue
        try:
            h, a = map(int, score_key.split(':'))
        except (ValueError, IndexError):
            continue

        total_g = h + a

        if h > a:
            home_win += prob
        elif h == a:
            draw += prob
        else:
            away_win += prob

        if total_g >= 2:
            over_15 += prob
        if total_g >= 3:
            over_25 += prob
        if total_g >= 4:
            over_35 += prob
        if total_g >= 5:
            over_45 += prob
        if h > 0 and a > 0:
            btts_yes += prob

    return {
        '1x2': {
            'home': round(home_win * 100, 1),
            'draw': round(draw * 100, 1),
            'away': round(away_win * 100, 1),
        },
        'goal_lines': {
            'over_1_5': round(over_15 * 100, 1),
            'under_1_5': round((1.0 - over_15) * 100, 1),
            'over_2_5': round(over_25 * 100, 1),
            'under_2_5': round((1.0 - over_25) * 100, 1),
            'over_3_5': round(over_35 * 100, 1),
            'under_3_5': round((1.0 - over_35) * 100, 1),
            'over_4_5': round(over_45 * 100, 1),
            'under_4_5': round((1.0 - over_45) * 100, 1),
        },
        'btts': {
            'yes': round(btts_yes * 100, 1),
            'no': round((1.0 - btts_yes) * 100, 1),
        },
    }


def _compute_goal_expectation(score_probs: Dict[str, float]) -> Tuple[float, float]:
    """Compute expected goals for home and away from the score distribution."""
    e_home = 0.0
    e_away = 0.0
    for score_key, prob in score_probs.items():
        if ':' not in score_key:
            continue
        try:
            h, a = map(int, score_key.split(':'))
            e_home += h * prob
            e_away += a * prob
        except (ValueError, IndexError):
            continue
    return e_home, e_away


# ---------------------------------------------------------------------------
# Confidence Score
# ---------------------------------------------------------------------------

def _compute_confidence(
    sources_used: List[str],
    score_probs: Dict[str, float],
    match_data: Dict,
) -> float:
    """
    Confidence score (0-100) based on:
      - Number of sources available (more = better)
      - Data richness (number of H2H matches, form matches)
      - Distribution entropy (lower entropy = more confident)
    """
    # Base score from source count
    n_sources = len(sources_used)
    base = 40.0 + n_sources * 6.0  # 5 sources => 70 base

    # Bonus for data richness
    h2h = match_data.get('h2h_details', {})
    h2h_count = len(h2h.get('h2h_matches', []))
    home_count = len(h2h.get('home_team_previous_matches', []))
    away_count = len(h2h.get('away_team_previous_matches', []))

    data_bonus = 0.0
    if h2h_count >= 5:
        data_bonus += 3.0
    if home_count >= 8:
        data_bonus += 2.0
    if away_count >= 8:
        data_bonus += 2.0
    if 'bookmaker' in sources_used:
        data_bonus += 3.0  # Market data is high quality

    # Entropy penalty: high entropy = less confident
    entropy = 0.0
    for p in score_probs.values():
        if p > 0:
            entropy -= p * math.log2(p)
    # Typical entropy for score distributions is 4-6 bits
    # Lower entropy -> more peaked -> more confident
    max_entropy = math.log2((MAX_GOALS + 1) ** 2)  # ~6.3 bits
    entropy_ratio = entropy / max_entropy if max_entropy > 0 else 0.5
    entropy_bonus = (1.0 - entropy_ratio) * 10.0  # Up to 10 points

    confidence = base + data_bonus + entropy_bonus
    return round(max(30.0, min(95.0, confidence)), 1)


# ---------------------------------------------------------------------------
# Top Scores Formatter
# ---------------------------------------------------------------------------

def _get_top_scores(score_probs: Dict[str, float], n: int = 10) -> List[Dict]:
    """Get top N most likely scores as formatted dicts (probability in %)."""
    sorted_scores = sorted(score_probs.items(), key=lambda x: x[1], reverse=True)
    result = []
    for score_key, prob in sorted_scores[:n]:
        if prob < 0.001:  # Skip negligible probabilities
            continue
        if ':' not in score_key:
            continue
        try:
            h, a = map(int, score_key.split(':'))
        except (ValueError, IndexError):
            continue
        result.append({
            'score': score_key,
            'probability': round(prob * 100, 2),
            'home_goals': h,
            'away_goals': a,
        })
    return result


# ---------------------------------------------------------------------------
# Score Categories
# ---------------------------------------------------------------------------

def _categorize_scores(score_probs: Dict[str, float]) -> Dict:
    """Categorize total probability by home win / draw / away win."""
    hw = 0.0
    dr = 0.0
    aw = 0.0
    for score_key, prob in score_probs.items():
        if ':' not in score_key:
            continue
        try:
            h, a = map(int, score_key.split(':'))
        except (ValueError, IndexError):
            continue
        if h > a:
            hw += prob
        elif h == a:
            dr += prob
        else:
            aw += prob

    return {
        'home_win_prob': round(hw * 100, 1),
        'draw_prob': round(dr * 100, 1),
        'away_win_prob': round(aw * 100, 1),
    }


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def analyze_correct_score_enhanced(match_data: Dict) -> Dict:
    """
    5-source ensemble correct score prediction.

    Sources:
      1. Dixon-Coles Poisson (from xG lambdas)
      2. H2H Scoreline Frequency (time-decayed)
      3. Recent Form Poisson (EMA-based lambdas)
      4. Bookmaker Correct Score Odds (vig-removed)
      5. Common Scorelines Prior (Bayesian prior)

    Returns:
        {
            'correct_score_enhanced': {
                'top_scores': [...],
                'score_categories': {...},
                'derived_predictions': {...},
                'model_info': {...},
                'goal_expectation': {...},
                'confidence': float,
            }
        }

    Returns empty dict on failure.
    """
    try:
        # ----- Gather all sources -----
        sources: Dict[str, Dict[str, float]] = {}
        lambdas_for_info: Tuple[Optional[float], Optional[float]] = (None, None)

        # Source 1: Dixon-Coles
        dc = source_dixon_coles(match_data)
        if dc:
            sources['dixon_coles'] = dc
            lam_h, lam_a = _extract_poisson_lambdas(match_data)
            lambdas_for_info = (lam_h, lam_a)
            logger.debug("Dixon-Coles source: OK (lambda_h=%.3f, lambda_a=%.3f)",
                         lam_h or 0, lam_a or 0)

        # Source 2: H2H Frequency
        h2h_freq = source_h2h_frequency(match_data)
        if h2h_freq:
            sources['h2h_frequency'] = h2h_freq
            logger.debug("H2H frequency source: OK (%d scores)", len(h2h_freq))

        # Source 3: Form Poisson
        form = source_form_poisson(match_data)
        if form:
            sources['form_poisson'] = form
            logger.debug("Form Poisson source: OK")

        # Source 4: Bookmaker
        bk = source_bookmaker(match_data)
        if bk:
            sources['bookmaker'] = bk
            logger.debug("Bookmaker source: OK (%d scores from odds)", len(bk))

        # Source 5: Common Scores
        cs = source_common_scores(match_data)
        if cs:
            sources['common_scores'] = cs
            logger.debug("Common scores source: OK")

        if not sources:
            logger.warning("No valid sources for correct score prediction")
            return {}

        # ----- Blend -----
        effective_weights = _compute_effective_weights(sources)
        blended = blend_distributions(sources)

        if not blended:
            logger.warning("Blending produced empty distribution")
            return {}

        # ----- Build output -----
        top_scores = _get_top_scores(blended, n=10)
        categories = _categorize_scores(blended)
        derived = _derive_predictions(blended)
        e_home, e_away = _compute_goal_expectation(blended)
        sources_used = list(sources.keys())
        confidence = _compute_confidence(sources_used, blended, match_data)

        # Use Poisson lambdas for model_info if available, otherwise use expectation from blend
        info_lam_h = lambdas_for_info[0] if lambdas_for_info[0] is not None else e_home
        info_lam_a = lambdas_for_info[1] if lambdas_for_info[1] is not None else e_away

        return {
            'correct_score_enhanced': {
                'top_scores': top_scores,
                'score_categories': categories,
                'derived_predictions': derived,
                'model_info': {
                    'rho': DEFAULT_RHO,
                    'home_lambda': round(info_lam_h, 3),
                    'away_lambda': round(info_lam_a, 3),
                    'model_type': 'ensemble_5source',
                    'sources_used': sources_used,
                    'weights': {k: round(v, 3) for k, v in effective_weights.items()},
                },
                'goal_expectation': {
                    'home': round(e_home, 2),
                    'away': round(e_away, 2),
                    'total': round(e_home + e_away, 2),
                },
                'confidence': confidence,
            }
        }

    except Exception as e:
        logger.error("Enhanced correct score ensemble error: %s", e, exc_info=True)
        return {}
