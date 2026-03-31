"""
Eagle Accuracy Tracking Module

Compares daily Eagle predictions with actual match results
to calculate per-algorithm and per-market accuracy rates.

Modules:
    db                  - PostgreSQL connection pool and query helpers
    result_resolver     - Fetches finished match scores from NowGoal
    accuracy_calculator - Compares predictions vs results, stores accuracy
    accuracy_cron       - Daily background thread for automatic calculation
    report_generator    - Builds comprehensive accuracy reports for the UI
    config_manager      - Reads/writes tunable algorithm parameters
    parameter_tuner     - Auto-tuning engine (grid search + backtest)
    tuner_cron          - Daily background thread for automatic tuning
    basket1_bridge      - Imports basketball picks from Basket1 API
"""

from accuracy.db import get_conn, execute_query, execute_many, init_db, close_pool
from accuracy.result_resolver import resolve_match_results
from accuracy.accuracy_calculator import calculate_accuracy
from accuracy.accuracy_cron import start_accuracy_cron, stop_accuracy_cron
from accuracy.report_generator import (
    generate_daily_report,
    generate_period_report,
    list_available_reports,
)
from accuracy.tuner_cron import start_tuner_cron, stop_tuner_cron
from accuracy.basket1_bridge import (
    sync_basket1_accuracy,
    get_basket1_accuracy_summary,
    fetch_basket1_picks,
)

__all__ = [
    "get_conn",
    "execute_query",
    "execute_many",
    "init_db",
    "close_pool",
    "resolve_match_results",
    "calculate_accuracy",
    "start_accuracy_cron",
    "stop_accuracy_cron",
    "generate_daily_report",
    "generate_period_report",
    "list_available_reports",
    "start_tuner_cron",
    "stop_tuner_cron",
    "sync_basket1_accuracy",
    "get_basket1_accuracy_summary",
    "fetch_basket1_picks",
]
