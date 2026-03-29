"""
Analysis Package
Contains football match analysis modules (14 original + 6 new Eagle algorithms)
"""

from .correct_score import analyze_correct_score_predictions, calculate_derived_predictions
from .h2h import analyze_h2h_details
from .team_performance import analyze_team_performance
from .final_predictions import calculate_final_predictions
from .odds_trends import analyze_odds_trends
from .tips import generate_betting_tips
from .spotlight import compute_spotlight_stats

# New Eagle algorithms
from .card_predictions import analyze_card_predictions
from .correct_score_enhanced import analyze_correct_score_enhanced
from .handicap_predictions import analyze_handicap_predictions
from .first_half_predictions import analyze_first_half_predictions
from .second_half_predictions import analyze_second_half_predictions
from .half_btts_predictions import analyze_half_btts_predictions
from .corner_predictions import analyze_corner_predictions

__all__ = [
    'analyze_correct_score_predictions',
    'calculate_derived_predictions',
    'analyze_h2h_details',
    'analyze_team_performance',
    'calculate_final_predictions',
    'analyze_odds_trends',
    'generate_betting_tips',
    'compute_spotlight_stats',
    # New algorithms
    'analyze_card_predictions',
    'analyze_correct_score_enhanced',
    'analyze_handicap_predictions',
    'analyze_first_half_predictions',
    'analyze_second_half_predictions',
    'analyze_half_btts_predictions',
    'analyze_corner_predictions',
]
