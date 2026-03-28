"""
Analysis Package
Contains football match analysis modules
"""

from .correct_score import analyze_correct_score_predictions, calculate_derived_predictions
from .h2h import analyze_h2h_details
from .team_performance import analyze_team_performance
from .final_predictions import calculate_final_predictions
from .odds_trends import analyze_odds_trends
from .tips import generate_betting_tips
from .spotlight import compute_spotlight_stats

__all__ = [
    'analyze_correct_score_predictions',
    'calculate_derived_predictions',
    'analyze_h2h_details',
    'analyze_team_performance',
    'calculate_final_predictions',
    'analyze_odds_trends',
    'generate_betting_tips',
    'compute_spotlight_stats',
]
