"""
Parameter Tuner — automatic optimization engine for Eagle prediction algorithms.

Strategy:
    1. Identify algorithms performing below TARGET_ACCURACY (85%)
    2. Generate parameter variations (grid search with +/- 10% steps)
    3. Backtest each variation against the last 7 days of prediction_results
    4. Apply the best-performing parameter set if improvement >= 1%
    5. Record all changes in parameter_history and tuner_runs tables

Backtesting approach:
    For threshold-based params (FIRST_HALF_SHARE, HOME_CORNER_SHARE, etc.):
        Predictions near the decision boundary (confidence 40-60%) are
        sensitive to parameter shifts.  We estimate how many borderline
        predictions would flip from incorrect to correct (or vice versa)
        with the new parameter value.

    For weight-based params (DC_WEIGHT, BK_WEIGHT, SOURCE_WEIGHTS):
        A simplified re-scoring evaluates the weighted confidence shift
        and estimates the net accuracy change.

    The backtest is an *estimation*, not a full replay — it uses the
    already-stored prediction_results to avoid re-running the full
    analysis pipeline, which would require live data fetching.

Safety:
    - Minimum 1% improvement required to apply changes
    - Parameter bounds enforced via config_manager
    - Backup created before every file modification
    - All changes logged in PostgreSQL for audit trail

Usage::

    from accuracy.parameter_tuner import AutoTuner
    tuner = AutoTuner()
    summary = tuner.run_daily_tuning()
"""

import logging
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from accuracy.config_manager import (
    TUNABLE_PARAMS,
    get_all_tunable_params,
    read_algorithm_params,
    write_algorithm_params,
)
from accuracy.db import execute_query, execute_many

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TARGET_ACCURACY = 85.0  # Percent
MIN_IMPROVEMENT_PCT = 1.0  # Minimum accuracy improvement to apply changes
BACKTEST_DAYS = 7  # Days of historical data to evaluate
MIN_PREDICTIONS_FOR_TUNING = 20  # Skip algorithms with too few data points
GRID_STEPS = [-0.10, -0.05, 0.05, 0.10]  # Relative variation steps
MAX_VARIATIONS_PER_PARAM = 4  # Max grid points per parameter


# ---------------------------------------------------------------------------
# Schema — tuner_runs table (idempotent)
# ---------------------------------------------------------------------------

_TUNER_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tuner_runs (
    id               TEXT PRIMARY KEY,
    started_at       TIMESTAMPTZ NOT NULL,
    completed_at      TIMESTAMPTZ,
    status           TEXT NOT NULL DEFAULT 'running',
    algorithms_checked  INTEGER DEFAULT 0,
    algorithms_tuned    INTEGER DEFAULT 0,
    total_variations    INTEGER DEFAULT 0,
    summary          JSONB,
    error            TEXT
);

CREATE INDEX IF NOT EXISTS idx_tuner_runs_started
    ON tuner_runs (started_at DESC);
"""


def ensure_tuner_schema() -> None:
    """Create the tuner_runs table if it does not exist (idempotent)."""
    try:
        execute_query(_TUNER_SCHEMA_SQL, fetch=False)
        logger.info("[AutoTuner] Tuner schema ensured")
    except Exception as exc:
        logger.error("[AutoTuner] Schema creation failed: %s", exc)


# ---------------------------------------------------------------------------
# Backtest Engine
# ---------------------------------------------------------------------------

def _load_recent_predictions(algorithm: str, days: int) -> List[Dict]:
    """
    Load resolved prediction results for a given algorithm over the last N days.

    Only returns predictions that have been resolved (is_correct IS NOT NULL).
    """
    cutoff = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = execute_query(
        """
        SELECT date, match_id, algorithm, market, prediction,
               confidence, actual_result, is_correct,
               home_score, away_score, ht_home_score, ht_away_score,
               total_goals, total_corners, total_cards
        FROM prediction_results
        WHERE algorithm = %s
          AND date >= %s
          AND is_correct IS NOT NULL
        ORDER BY date DESC
        """,
        (algorithm, cutoff),
        fetch=True,
    )
    return rows or []


def _get_algorithm_accuracy(algorithm: str, days: int) -> Optional[Dict]:
    """
    Get the aggregate accuracy for an algorithm over the last N days.

    Returns dict with total, correct, accuracy_pct or None if no data.
    """
    cutoff = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = execute_query(
        """
        SELECT
            SUM(total_predictions) AS total,
            SUM(correct_predictions) AS correct
        FROM algorithm_accuracy
        WHERE algorithm = %s
          AND date >= %s
        """,
        (algorithm, cutoff),
        fetch=True,
    )
    if not rows or not rows[0] or not rows[0].get("total"):
        return None

    total = rows[0]["total"]
    correct = rows[0]["correct"]
    if total == 0:
        return None

    return {
        "algorithm": algorithm,
        "total": total,
        "correct": correct,
        "accuracy_pct": round((correct / total) * 100, 2),
    }


def _estimate_accuracy_with_params(
    predictions: List[Dict],
    algorithm: str,
    current_params: Dict[str, Any],
    new_params: Dict[str, Any],
) -> float:
    """
    Estimate accuracy that would result from applying *new_params* to the
    given set of historical predictions.

    This is a heuristic estimation — NOT a full replay.  The approach:

    1. For each prediction, compute a "sensitivity score" based on how close
       the confidence was to the decision boundary (50%).
    2. Estimate the probability that each parameter change would flip the
       prediction outcome for sensitive predictions.
    3. Sum up the net expected flips (correct -> incorrect and vice versa)
       to estimate the new accuracy.

    The sensitivity model is based on the observation that:
    - Predictions with confidence near 50% are highly sensitive to parameter
      changes (they could easily go either way).
    - Predictions with confidence > 80% or < 20% are unlikely to flip
      regardless of small parameter adjustments.

    For threshold parameters (like FIRST_HALF_SHARE), a 5% change in the
    share directly shifts the expected lambda, which shifts probabilities
    near the boundary.

    For the rho parameter (Dixon-Coles), we estimate the effect on low-score
    game probabilities.
    """
    if not predictions:
        return 0.0

    total_resolved = len(predictions)
    current_correct = sum(1 for p in predictions if p["is_correct"])

    # Calculate the *relative* parameter shift for each changed parameter
    param_shifts: Dict[str, float] = {}
    for param_name, new_val in new_params.items():
        old_val = current_params.get(param_name)
        if old_val is None or not isinstance(old_val, (int, float)):
            continue
        if not isinstance(new_val, (int, float)):
            continue
        if old_val == 0:
            param_shifts[param_name] = 0.0
        else:
            param_shifts[param_name] = (new_val - old_val) / abs(old_val)

    if not param_shifts:
        # Dict-type params: rough estimation based on value magnitude change
        for param_name, new_val in new_params.items():
            old_val = current_params.get(param_name)
            if isinstance(old_val, dict) and isinstance(new_val, dict):
                shifts = []
                for k in old_val:
                    if k in new_val and isinstance(old_val[k], (int, float)):
                        if old_val[k] != 0:
                            shifts.append(
                                (new_val[k] - old_val[k]) / abs(old_val[k])
                            )
                if shifts:
                    param_shifts[param_name] = sum(shifts) / len(shifts)

    if not param_shifts:
        return (current_correct / total_resolved) * 100 if total_resolved else 0.0

    # Overall relative shift magnitude (absolute, averaged across params)
    avg_shift = sum(abs(s) for s in param_shifts.values()) / len(param_shifts)

    # Count "borderline" predictions — confidence between 40% and 60%
    # These are most sensitive to parameter changes.
    borderline_correct = 0
    borderline_incorrect = 0
    high_confidence_correct = 0
    high_confidence_incorrect = 0

    for pred in predictions:
        conf = pred.get("confidence") or 50.0
        is_correct = pred["is_correct"]

        if 40 <= conf <= 60:
            if is_correct:
                borderline_correct += 1
            else:
                borderline_incorrect += 1
        else:
            if is_correct:
                high_confidence_correct += 1
            else:
                high_confidence_incorrect += 1

    # Estimate flip probability:
    # A 10% parameter shift has roughly 15-25% chance of flipping a borderline prediction.
    # We use a linear model: flip_prob = min(0.30, avg_shift * 2.0)
    flip_prob = min(0.30, avg_shift * 2.0)

    # Determine if the shift direction is likely positive or negative.
    # Heuristic: if the algorithm is under-performing, moderate shifts
    # (away from current values) are more likely to help than hurt.
    # We assume a 60% chance the shift helps for borderline cases.
    help_probability = 0.60

    # Expected net flip count
    expected_flips_to_correct = borderline_incorrect * flip_prob * help_probability
    expected_flips_to_incorrect = borderline_correct * flip_prob * (1 - help_probability)

    # Small effect on high-confidence predictions
    hc_flip_prob = min(0.05, avg_shift * 0.5)
    hc_flips_to_correct = high_confidence_incorrect * hc_flip_prob * help_probability
    hc_flips_to_incorrect = high_confidence_correct * hc_flip_prob * (1 - help_probability)

    net_change = (
        expected_flips_to_correct
        - expected_flips_to_incorrect
        + hc_flips_to_correct
        - hc_flips_to_incorrect
    )

    estimated_correct = current_correct + net_change
    estimated_correct = max(0, min(total_resolved, estimated_correct))

    estimated_accuracy = (estimated_correct / total_resolved) * 100 if total_resolved else 0.0
    return round(estimated_accuracy, 2)


# ---------------------------------------------------------------------------
# AutoTuner
# ---------------------------------------------------------------------------

class AutoTuner:
    """
    Automatic parameter optimization for Eagle prediction algorithms.

    Runs a daily grid-search-based optimization loop:
    1. Identifies under-performing algorithms (below TARGET_ACCURACY)
    2. Generates parameter variations
    3. Backtests each variation
    4. Applies the best-performing set if improvement is significant
    """

    TARGET_ACCURACY = TARGET_ACCURACY

    def __init__(self) -> None:
        self._run_id: Optional[str] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_daily_tuning(self) -> Dict[str, Any]:
        """
        Main entry point for daily parameter tuning.

        Returns:
            Summary dict with tuning results::

                {
                    "run_id": "...",
                    "status": "completed",
                    "algorithms_checked": 5,
                    "algorithms_tuned": 2,
                    "total_variations_tested": 16,
                    "details": {
                        "first_half": {...},
                        "corner": {...},
                    },
                    "elapsed_seconds": 12.3,
                }
        """
        import time
        start_time = time.time()

        self._run_id = str(uuid.uuid4())[:12]
        started_at = datetime.now(timezone.utc)

        logger.info(
            "[AutoTuner] Starting daily tuning run %s (target: %.1f%%)",
            self._run_id, self.TARGET_ACCURACY,
        )

        # Ensure schema exists
        ensure_tuner_schema()

        # Record run start
        self._record_run_start(started_at)

        try:
            # Step 1: Get under-performing algorithms
            underperformers = self._get_underperforming_algorithms()

            if not underperformers:
                logger.info("[AutoTuner] All algorithms at or above target — no tuning needed")
                summary = {
                    "run_id": self._run_id,
                    "status": "completed",
                    "message": "All algorithms at or above target accuracy",
                    "algorithms_checked": 0,
                    "algorithms_tuned": 0,
                    "total_variations_tested": 0,
                    "details": {},
                    "elapsed_seconds": round(time.time() - start_time, 2),
                }
                self._record_run_finish("completed", summary)
                return summary

            logger.info(
                "[AutoTuner] Found %d under-performing algorithms: %s",
                len(underperformers),
                [u["algorithm"] for u in underperformers],
            )

            # Step 2: Tune each algorithm
            details: Dict[str, Any] = {}
            total_variations = 0
            algorithms_tuned = 0

            for algo_info in underperformers:
                market_name = algo_info["market"]
                algo_result = self._tune_algorithm(algo_info)
                details[market_name] = algo_result
                total_variations += algo_result.get("variations_tested", 0)
                if algo_result.get("applied"):
                    algorithms_tuned += 1

            elapsed = round(time.time() - start_time, 2)

            summary = {
                "run_id": self._run_id,
                "status": "completed",
                "algorithms_checked": len(underperformers),
                "algorithms_tuned": algorithms_tuned,
                "total_variations_tested": total_variations,
                "details": details,
                "elapsed_seconds": elapsed,
            }

            logger.info(
                "[AutoTuner] Run %s completed: %d/%d algorithms tuned, "
                "%d variations tested in %.1fs",
                self._run_id,
                algorithms_tuned,
                len(underperformers),
                total_variations,
                elapsed,
            )

            self._record_run_finish("completed", summary)
            return summary

        except Exception as exc:
            logger.error(
                "[AutoTuner] Run %s failed: %s", self._run_id, exc, exc_info=True,
            )
            error_summary = {
                "run_id": self._run_id,
                "status": "error",
                "error": str(exc),
                "elapsed_seconds": round(time.time() - start_time, 2),
            }
            self._record_run_finish("error", error_summary, error=str(exc))
            return error_summary

    def get_tuner_status(self) -> Dict[str, Any]:
        """
        Return current tuner status for the API.

        Includes last run info, next scheduled run, and overall stats.
        """
        try:
            # Last run
            last_run_rows = execute_query(
                """
                SELECT run_id, started_at, completed_at, status,
                       algorithms_tuned, parameters_changed, details, error_message
                FROM tuner_runs
                ORDER BY started_at DESC
                LIMIT 1
                """,
                fetch=True,
            ) or []

            # Stats: total runs, total tunings
            stats_rows = execute_query(
                """
                SELECT
                    COUNT(*) AS total_runs,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed,
                    SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) AS errors,
                    SUM(COALESCE(algorithms_tuned, 0)) AS total_tuned
                FROM tuner_runs
                """,
                fetch=True,
            ) or []

            # Recent parameter changes
            changes_rows = execute_query(
                """
                SELECT algorithm, parameter_name, old_value, new_value,
                       accuracy_before, accuracy_after, applied_at
                FROM parameter_history
                ORDER BY applied_at DESC
                LIMIT 10
                """,
                fetch=True,
            ) or []

            last_run = None
            if last_run_rows:
                r = last_run_rows[0]
                last_run = {
                    "run_id": r["run_id"],
                    "started_at": r["started_at"].isoformat() if r["started_at"] else None,
                    "completed_at": r["completed_at"].isoformat() if r["completed_at"] else None,
                    "status": r["status"],
                    "algorithms_tuned": r["algorithms_tuned"],
                    "parameters_changed": r["parameters_changed"],
                    "error": r["error_message"],
                }

            stats = {}
            if stats_rows and stats_rows[0]:
                s = stats_rows[0]
                stats = {
                    "total_runs": s["total_runs"] or 0,
                    "completed_runs": s["completed"] or 0,
                    "error_runs": s["errors"] or 0,
                    "total_algorithms_tuned": s["total_tuned"] or 0,
                }

            recent_changes = []
            for c in changes_rows:
                recent_changes.append({
                    "algorithm": c["algorithm"],
                    "parameter": c["parameter_name"],
                    "old_value": c["old_value"],
                    "new_value": c["new_value"],
                    "accuracy_before": c["accuracy_before"],
                    "accuracy_after": c["accuracy_after"],
                    "applied_at": c["applied_at"].isoformat() if c["applied_at"] else None,
                })

            # Determine next run (approximately 04:00 UTC daily)
            tuner_hour = int(os.getenv("TUNER_CRON_HOUR", "4"))
            now = datetime.now(timezone.utc)
            next_run = now.replace(
                hour=tuner_hour, minute=0, second=0, microsecond=0
            )
            if now >= next_run:
                next_run += timedelta(days=1)

            return {
                "status": "active",
                "target_accuracy": self.TARGET_ACCURACY,
                "last_run": last_run,
                "next_run": next_run.isoformat(),
                "statistics": stats,
                "recent_changes": recent_changes,
            }

        except Exception as exc:
            logger.error("[AutoTuner] Status query failed: %s", exc)
            return {
                "status": "error",
                "target_accuracy": self.TARGET_ACCURACY,
                "error": str(exc),
            }

    def get_tuning_history(self, days: int = 30) -> List[Dict]:
        """
        Return recent tuning run history.

        Args:
            days: Number of days to look back.

        Returns:
            List of tuning run summaries.
        """
        cutoff = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")
        try:
            rows = execute_query(
                """
                SELECT run_id, started_at, completed_at, status,
                       algorithms_tuned, parameters_changed,
                       details, error_message
                FROM tuner_runs
                WHERE started_at >= %s
                ORDER BY started_at DESC
                """,
                (cutoff,),
                fetch=True,
            ) or []

            history = []
            for r in rows:
                history.append({
                    "run_id": r["run_id"],
                    "started_at": r["started_at"].isoformat() if r["started_at"] else None,
                    "completed_at": r["completed_at"].isoformat() if r["completed_at"] else None,
                    "status": r["status"],
                    "algorithms_tuned": r["algorithms_tuned"],
                    "parameters_changed": r["parameters_changed"],
                    "error": r["error_message"],
                })
            return history

        except Exception as exc:
            logger.error("[AutoTuner] History query failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Internal methods
    # ------------------------------------------------------------------

    def _get_underperforming_algorithms(self) -> List[Dict]:
        """
        Get algorithms whose accuracy over the last BACKTEST_DAYS
        is below TARGET_ACCURACY.

        Only considers algorithms that have tunable parameters defined
        in config_manager and enough prediction data to be meaningful.
        """
        underperformers = []

        # Get all algorithms that have tunable params
        tunable_algos = set()
        for algo, params in TUNABLE_PARAMS.items():
            if params:  # Has at least one tunable parameter
                tunable_algos.add(algo)

        # Map market names in prediction_results to algorithm names in TUNABLE_PARAMS.
        market_to_module = {
            # Dedicated algorithm files
            "first_half": "first_half_predictions",
            "second_half": "second_half_predictions",
            "corner": "corner_predictions",
            "card": "card_predictions",
            "correct_score": "correct_score_enhanced",
            "handicap": "handicap_predictions",
            # final_predictions.py markets (source weight tuning)
            "ms": "final_predictions",
            "over25": "final_predictions",
            "over35": "final_predictions",
            "btts": "final_predictions",
            "ht_result": "final_predictions",
            "ht_over05": "final_predictions",
            # Basketball (remote via Basket1 HTTP bridge)
            "basket_ml": "basket_ml",
            "basket_ou": "basket_ou",
            "basket_ah": "basket_ah",
        }

        # Get accuracy for all markets
        cutoff = (date.today() - timedelta(days=BACKTEST_DAYS)).strftime("%Y-%m-%d")
        rows = execute_query(
            """
            SELECT algorithm,
                   SUM(total_predictions) AS total,
                   SUM(correct_predictions) AS correct
            FROM algorithm_accuracy
            WHERE date >= %s
            GROUP BY algorithm
            """,
            (cutoff,),
            fetch=True,
        ) or []

        for row in rows:
            market_name = row["algorithm"]
            module_name = market_to_module.get(market_name)

            if not module_name or module_name not in tunable_algos:
                continue

            total = row["total"] or 0
            correct = row["correct"] or 0

            if total < MIN_PREDICTIONS_FOR_TUNING:
                logger.debug(
                    "[AutoTuner] Skipping %s: only %d predictions (min: %d)",
                    market_name, total, MIN_PREDICTIONS_FOR_TUNING,
                )
                continue

            accuracy_pct = round((correct / total) * 100, 2) if total > 0 else 0.0

            if accuracy_pct < self.TARGET_ACCURACY:
                underperformers.append({
                    "algorithm": module_name,
                    "market": market_name,
                    "total": total,
                    "correct": correct,
                    "accuracy_pct": accuracy_pct,
                    "gap": round(self.TARGET_ACCURACY - accuracy_pct, 2),
                })
                logger.info(
                    "[AutoTuner] Under-performing: %s (market=%s) %.1f%% "
                    "(target: %.1f%%, gap: %.1f%%)",
                    module_name, market_name, accuracy_pct,
                    self.TARGET_ACCURACY, self.TARGET_ACCURACY - accuracy_pct,
                )

        # Sort by largest gap first (most room for improvement)
        underperformers.sort(key=lambda x: x["gap"], reverse=True)
        return underperformers

    def _tune_algorithm(self, algo_info: Dict) -> Dict[str, Any]:
        """
        Attempt to tune a single algorithm.

        1. Read current parameters
        2. Generate variations
        3. Backtest each variation
        4. Apply the best if improvement >= MIN_IMPROVEMENT_PCT

        Returns result dict for this algorithm.
        """
        algo_name = algo_info["algorithm"]
        market_name = algo_info["market"]
        current_accuracy = algo_info["accuracy_pct"]

        logger.info(
            "[AutoTuner] Tuning %s (market=%s, current=%.1f%%)",
            algo_name, market_name, current_accuracy,
        )

        # Basketball remote tuning
        if algo_name.startswith("basket_"):
            return self._tune_basket1_algorithm(algo_info)

        # For final_predictions, select market-specific weight param
        market_param_map = {
            "ms": "MS_WEIGHTS",
            "over25": "GOAL_LINES_WEIGHTS",
            "over35": "GOAL_LINES_WEIGHTS",
            "btts": "BTTS_WEIGHTS",
            "ht_result": "HT_1X2_WEIGHTS",
            "ht_over05": "HT_GOALS_WEIGHTS",
        }

        # Read current parameters
        current_params = read_algorithm_params(algo_name)

        # For final_predictions, filter to the relevant weight dict
        if algo_name == "final_predictions" and market_name in market_param_map:
            target_param = market_param_map[market_name]
            if target_param in current_params:
                current_params = {target_param: current_params[target_param]}
            else:
                current_params = {}

        if not current_params:
            logger.info("[AutoTuner] No readable params for %s — skipping", algo_name)
            return {
                "algorithm": algo_name,
                "market": market_name,
                "status": "skipped",
                "reason": "no_readable_params",
                "variations_tested": 0,
                "applied": False,
            }

        # Load predictions for backtesting
        predictions = _load_recent_predictions(market_name, BACKTEST_DAYS)
        if len(predictions) < MIN_PREDICTIONS_FOR_TUNING:
            logger.info(
                "[AutoTuner] Insufficient predictions for %s (%d) — skipping",
                algo_name, len(predictions),
            )
            return {
                "algorithm": algo_name,
                "market": market_name,
                "status": "skipped",
                "reason": "insufficient_data",
                "predictions_count": len(predictions),
                "variations_tested": 0,
                "applied": False,
            }

        # Generate variations
        variations = self._generate_variations(current_params, algo_name)
        if not variations:
            logger.info("[AutoTuner] No valid variations for %s — skipping", algo_name)
            return {
                "algorithm": algo_name,
                "market": market_name,
                "status": "skipped",
                "reason": "no_valid_variations",
                "variations_tested": 0,
                "applied": False,
            }

        # Backtest each variation
        best_accuracy = current_accuracy
        best_params: Optional[Dict] = None
        tested = 0

        for variation in variations:
            estimated = _estimate_accuracy_with_params(
                predictions, algo_name, current_params, variation,
            )
            tested += 1

            if estimated > best_accuracy:
                best_accuracy = estimated
                best_params = variation

        improvement = best_accuracy - current_accuracy

        logger.info(
            "[AutoTuner] %s: tested %d variations, best=%.2f%% (improvement=%.2f%%)",
            algo_name, tested, best_accuracy, improvement,
        )

        # Apply if improvement is significant
        applied = False
        if best_params and improvement >= MIN_IMPROVEMENT_PCT:
            applied = self._apply_best_params(
                algo_name, current_params, best_params,
                current_accuracy, best_accuracy,
            )

        return {
            "algorithm": algo_name,
            "market": market_name,
            "status": "tuned" if applied else "no_improvement",
            "current_accuracy": current_accuracy,
            "best_estimated_accuracy": best_accuracy,
            "improvement": round(improvement, 2),
            "variations_tested": tested,
            "applied": applied,
            "new_params": best_params if applied else None,
        }

    def _generate_variations(
        self,
        current_params: Dict[str, Any],
        algorithm: str,
    ) -> List[Dict[str, Any]]:
        """
        Generate parameter variations for grid search.

        For each numeric parameter, produces variants at +/- 5% and +/- 10%
        of the current value.  For dict parameters, varies each numeric
        value in the dict independently.

        Returns a list of complete parameter dicts (each is a full set).
        """
        param_defs = TUNABLE_PARAMS.get(algorithm, {})
        variations: List[Dict[str, Any]] = []

        for param_name, current_value in current_params.items():
            meta = param_defs.get(param_name, {})
            ptype = meta.get("type", "float")

            if ptype == "float" and isinstance(current_value, (int, float)):
                param_min = meta.get("min", current_value * 0.5)
                param_max = meta.get("max", current_value * 2.0)

                for step in GRID_STEPS:
                    new_value = current_value * (1.0 + step)
                    # Clamp to bounds
                    new_value = max(param_min, min(param_max, new_value))
                    new_value = round(new_value, 4)

                    if abs(new_value - current_value) < 0.001:
                        continue  # Skip if effectively unchanged

                    variant = dict(current_params)
                    variant[param_name] = new_value
                    variations.append(variant)

            elif ptype == "dict" and isinstance(current_value, dict):
                # For dict params, vary each numeric key independently
                for dict_key, dict_val in current_value.items():
                    if not isinstance(dict_val, (int, float)):
                        continue

                    for step in [-0.10, 0.10]:
                        new_dict = dict(current_value)
                        new_dict[dict_key] = round(dict_val * (1.0 + step), 4)

                        variant = dict(current_params)
                        variant[param_name] = new_dict
                        variations.append(variant)

        return variations

    def _apply_best_params(
        self,
        algorithm: str,
        current_params: Dict[str, Any],
        best_params: Dict[str, Any],
        accuracy_before: float,
        estimated_accuracy: float,
    ) -> bool:
        """
        Apply the best parameter set to the algorithm file and record the change.

        Args:
            algorithm:          Algorithm module name.
            current_params:     Current parameter values.
            best_params:        Optimized parameter values.
            accuracy_before:    Accuracy before tuning.
            estimated_accuracy: Estimated accuracy with new params.

        Returns:
            True if parameters were successfully applied.
        """
        # Only write the parameters that actually changed
        changed_params: Dict[str, Any] = {}
        for key, new_val in best_params.items():
            old_val = current_params.get(key)
            if old_val != new_val:
                changed_params[key] = new_val

        if not changed_params:
            logger.info("[AutoTuner] No actual changes for %s", algorithm)
            return False

        logger.info(
            "[AutoTuner] Applying to %s: %s (%.1f%% -> est. %.1f%%)",
            algorithm, changed_params, accuracy_before, estimated_accuracy,
        )

        # Write to file (config_manager creates backup automatically)
        success = write_algorithm_params(algorithm, changed_params)

        if not success:
            logger.error("[AutoTuner] Failed to write params for %s", algorithm)
            return False

        # Record each parameter change in parameter_history
        for param_name, new_val in changed_params.items():
            old_val = current_params.get(param_name)

            # For numeric values, store directly; for dicts, store a summary
            old_numeric = old_val if isinstance(old_val, (int, float)) else None
            new_numeric = new_val if isinstance(new_val, (int, float)) else None

            try:
                execute_query(
                    """
                    INSERT INTO parameter_history
                        (sport, algorithm, parameter_name, old_value, new_value,
                         reason, accuracy_before, accuracy_after)
                    VALUES
                        (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        "football",
                        algorithm,
                        param_name,
                        old_numeric,
                        new_numeric,
                        f"AutoTuner run {self._run_id}: grid search optimization",
                        accuracy_before,
                        estimated_accuracy,
                    ),
                    fetch=False,
                )
            except Exception as exc:
                logger.error(
                    "[AutoTuner] Failed to record parameter change: %s", exc,
                )

        logger.info(
            "[AutoTuner] Applied %d parameter changes to %s",
            len(changed_params), algorithm,
        )
        return True

    # ------------------------------------------------------------------
    # Basketball (Basket1) remote tuning
    # ------------------------------------------------------------------

    def _tune_basket1_algorithm(self, algo_info: Dict) -> Dict[str, Any]:
        """
        Attempt to tune a Basket1 algorithm via HTTP bridge.

        Currently a placeholder that logs the accuracy but does not
        modify remote parameters — remote parameter tuning requires
        the Basket1 API to expose a config endpoint.
        """
        algo_name = algo_info["algorithm"]
        market_name = algo_info["market"]
        current_accuracy = algo_info["accuracy_pct"]

        logger.info(
            "[AutoTuner] Basketball algorithm %s (market=%s, accuracy=%.1f%%) — "
            "remote tuning not yet available, logging only",
            algo_name, market_name, current_accuracy,
        )

        return {
            "algorithm": algo_name,
            "market": market_name,
            "status": "remote_logged",
            "current_accuracy": current_accuracy,
            "best_estimated_accuracy": current_accuracy,
            "improvement": 0.0,
            "variations_tested": 0,
            "applied": False,
            "note": "Basketball remote tuning — accuracy tracked, parameter tuning pending Basket1 config API",
        }

    # ------------------------------------------------------------------
    # Run tracking
    # ------------------------------------------------------------------

    def _record_run_start(self, started_at: datetime) -> None:
        """Record the start of a tuning run in the database."""
        try:
            execute_query(
                """
                INSERT INTO tuner_runs (run_id, started_at, status)
                VALUES (%s, %s, 'running')
                ON CONFLICT (run_id) DO NOTHING
                """,
                (self._run_id, started_at),
                fetch=False,
            )
        except Exception as exc:
            logger.error("[AutoTuner] Failed to record run start: %s", exc)

    def _record_run_finish(
        self,
        status: str,
        summary: Dict,
        error: Optional[str] = None,
    ) -> None:
        """Record the completion of a tuning run."""
        import json

        try:
            execute_query(
                """
                UPDATE tuner_runs
                SET completed_at = %s,
                    status = %s,
                    algorithms_tuned = %s,
                    parameters_changed = %s,
                    details = %s,
                    error_message = %s
                WHERE run_id = %s
                """,
                (
                    datetime.now(timezone.utc),
                    status,
                    summary.get("algorithms_tuned", 0),
                    summary.get("total_params_changed", 0),
                    json.dumps(summary, default=str),
                    error,
                    self._run_id,
                ),
                fetch=False,
            )
        except Exception as exc:
            logger.error("[AutoTuner] Failed to record run finish: %s", exc)
