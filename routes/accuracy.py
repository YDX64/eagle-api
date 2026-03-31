"""
Accuracy API Blueprint — exposes accuracy reports and management endpoints.

Provides two sets of routes:

1. **Accuracy-specific** (``/accuracy/...``) — full CRUD for accuracy data.
2. **ML Monitor compat** (``/reports``, ``/report/<date>``, ``/latest``) — thin
   aliases that return the same report payloads the frontend ML Monitor
   page expects at ``/api/v1/reports``, ``/api/v1/report/<date>``, etc.

All endpoints return JSON with a top-level ``success`` boolean.
"""

import hmac
import logging
import os
from datetime import date, datetime, timedelta

from flask import Blueprint, jsonify, request

from accuracy.db import execute_query
from accuracy.report_generator import (
    generate_daily_report,
    generate_period_report,
    list_available_reports,
)

logger = logging.getLogger(__name__)

accuracy_bp = Blueprint("accuracy", __name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

API_SECRET_KEY = os.getenv("API_SECRET_KEY", "default-key")


def _require_api_key():
    """
    Validate the ``X-API-KEY`` header against ``API_SECRET_KEY``.

    Returns ``None`` on success, or a Flask ``(response, status)`` tuple
    on failure.
    """
    provided = request.headers.get("X-API-KEY") or request.headers.get("X-Api-Key") or ""
    if not provided:
        return jsonify({"success": False, "error": "API key required"}), 401
    if not hmac.compare_digest(provided, API_SECRET_KEY):
        return jsonify({"success": False, "error": "Invalid API key"}), 403
    return None


def _safe_json(fn, *args, **kwargs):
    """
    Execute *fn* and wrap the result in a standard JSON envelope.

    On success: ``{"success": true, ...payload}``
    On error:   ``{"success": false, "error": "..."}`` with HTTP 500.
    """
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        logger.error("[AccuracyAPI] %s failed: %s", fn.__name__, exc, exc_info=True)
        return jsonify({"success": False, "error": str(exc)}), 500


# ============================================================================
# 1.  Accuracy-specific endpoints  (/accuracy/...)
# ============================================================================

@accuracy_bp.route("/accuracy/reports", methods=["GET"])
def accuracy_list_reports():
    """List dates that have accuracy data."""
    def _handler():
        limit = request.args.get("limit", 30, type=int)
        reports = list_available_reports(limit=limit)
        return jsonify({
            "success": True,
            "reports": reports,
            "total": len(reports),
        })
    return _safe_json(_handler)


@accuracy_bp.route("/accuracy/report/<string:target_date>", methods=["GET"])
def accuracy_get_report(target_date: str):
    """Get full accuracy report for a specific date."""
    def _handler():
        # Validate date format.
        try:
            datetime.strptime(target_date, "%Y-%m-%d")
        except ValueError:
            return jsonify({
                "success": False,
                "error": "Invalid date format. Use YYYY-MM-DD.",
            }), 400

        report = generate_daily_report(target_date)
        return jsonify({"success": True, "report": report})
    return _safe_json(_handler)


@accuracy_bp.route("/accuracy/latest", methods=["GET"])
def accuracy_latest_report():
    """Get the most recent accuracy report."""
    def _handler():
        dates = list_available_reports(limit=1)
        if not dates:
            return jsonify({
                "success": True,
                "report": None,
                "message": "No accuracy data available yet",
            })
        report = generate_daily_report(dates[0])
        return jsonify({"success": True, "report": report})
    return _safe_json(_handler)


@accuracy_bp.route("/accuracy/algorithms", methods=["GET"])
def accuracy_algorithms():
    """Get all algorithms with their latest accuracy and trend."""
    def _handler():
        # Latest accuracy per algorithm (most recent date per algo).
        rows = execute_query(
            """
            SELECT DISTINCT ON (algorithm)
                   algorithm, accuracy_pct, total_predictions, date
            FROM algorithm_accuracy
            ORDER BY algorithm, date DESC
            """,
            fetch=True,
        ) or []

        # For trend, get the previous date's accuracy for comparison.
        prev_map: dict = {}
        if rows:
            latest_date = max(str(r["date"]) for r in rows)
            try:
                prev_dt = datetime.strptime(latest_date, "%Y-%m-%d").date() - timedelta(days=1)
                prev_rows = execute_query(
                    """
                    SELECT algorithm, accuracy_pct
                    FROM algorithm_accuracy
                    WHERE date = %s
                    """,
                    (prev_dt.strftime("%Y-%m-%d"),),
                    fetch=True,
                ) or []
                prev_map = {r["algorithm"]: r["accuracy_pct"] for r in prev_rows}
            except Exception:
                pass

        algorithms = []
        for r in rows:
            algo = r["algorithm"]
            current_pct = r["accuracy_pct"] or 0
            prev_pct = prev_map.get(algo)

            if prev_pct is not None:
                diff = current_pct - prev_pct
                if diff > 1:
                    trend = "up"
                elif diff < -1:
                    trend = "down"
                else:
                    trend = "stable"
            else:
                trend = "new"

            algorithms.append({
                "name": algo,
                "accuracy_pct": round(current_pct, 2),
                "total": r["total_predictions"] or 0,
                "trend": trend,
                "date": str(r["date"]),
            })

        algorithms.sort(key=lambda a: a["accuracy_pct"], reverse=True)
        return jsonify({"success": True, "algorithms": algorithms})
    return _safe_json(_handler)


@accuracy_bp.route("/accuracy/algorithm/<string:name>/history", methods=["GET"])
def accuracy_algorithm_history(name: str):
    """Get accuracy history for a single algorithm."""
    def _handler():
        days = request.args.get("days", 30, type=int)
        days = min(days, 365)  # Cap at 1 year.

        cutoff = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")
        rows = execute_query(
            """
            SELECT date, accuracy_pct, total_predictions, avg_confidence
            FROM algorithm_accuracy
            WHERE algorithm = %s AND date >= %s
            ORDER BY date ASC
            """,
            (name, cutoff),
            fetch=True,
        ) or []

        history = []
        for r in rows:
            history.append({
                "date": str(r["date"]),
                "accuracy_pct": round(r["accuracy_pct"] or 0, 2),
                "total": r["total_predictions"] or 0,
                "avg_confidence": round(r["avg_confidence"] or 0, 2),
            })

        return jsonify({
            "success": True,
            "algorithm": name,
            "days": days,
            "history": history,
        })
    return _safe_json(_handler)


@accuracy_bp.route("/accuracy/calculate", methods=["POST"])
def accuracy_calculate():
    """
    Trigger manual accuracy calculation for a given date.

    Requires ``X-API-KEY`` header matching ``API_SECRET_KEY``.

    Body (JSON):
        ``{"date": "2026-03-28"}``
    """
    # Auth check.
    auth_err = _require_api_key()
    if auth_err is not None:
        return auth_err

    def _handler():
        data = request.get_json(silent=True) or {}
        target_date = data.get("date")

        if not target_date:
            return jsonify({
                "success": False,
                "error": "Missing 'date' in request body",
            }), 400

        try:
            datetime.strptime(target_date, "%Y-%m-%d")
        except ValueError:
            return jsonify({
                "success": False,
                "error": "Invalid date format. Use YYYY-MM-DD.",
            }), 400

        from accuracy.accuracy_calculator import calculate_accuracy
        result = calculate_accuracy(target_date)

        return jsonify({"success": True, "result": result})
    return _safe_json(_handler)


@accuracy_bp.route("/accuracy/period", methods=["GET"])
def accuracy_period_report():
    """
    Get aggregated accuracy report for a custom date range.

    Query params:
        start: Start date (YYYY-MM-DD)
        end:   End date (YYYY-MM-DD)
    """
    def _handler():
        start = request.args.get("start")
        end = request.args.get("end")

        if not start or not end:
            return jsonify({
                "success": False,
                "error": "Both 'start' and 'end' query params required",
            }), 400

        for d in (start, end):
            try:
                datetime.strptime(d, "%Y-%m-%d")
            except ValueError:
                return jsonify({
                    "success": False,
                    "error": f"Invalid date format: {d}. Use YYYY-MM-DD.",
                }), 400

        report = generate_period_report(start, end)
        return jsonify({"success": True, "report": report})
    return _safe_json(_handler)


@accuracy_bp.route("/accuracy/tuner/status", methods=["GET"])
def accuracy_tuner_status():
    """Get autotuner status including last run, next run, and recent changes."""
    def _handler():
        from accuracy.parameter_tuner import AutoTuner
        tuner = AutoTuner()
        status = tuner.get_tuner_status()
        return jsonify({"success": True, **status})
    return _safe_json(_handler)


@accuracy_bp.route("/accuracy/tuner/history", methods=["GET"])
def accuracy_tuner_history():
    """
    Get tuning run history.

    Query params:
        days: Number of days to look back (default 30, max 365).
    """
    def _handler():
        days = request.args.get("days", 30, type=int)
        days = min(days, 365)

        from accuracy.parameter_tuner import AutoTuner
        tuner = AutoTuner()
        history = tuner.get_tuning_history(days=days)
        return jsonify({
            "success": True,
            "history": history,
            "total": len(history),
            "days": days,
        })
    return _safe_json(_handler)


@accuracy_bp.route("/accuracy/tuner/run", methods=["POST"])
def accuracy_tuner_run():
    """
    Trigger a manual tuning run.

    Requires ``X-API-KEY`` header matching ``API_SECRET_KEY``.
    This runs the full AutoTuner optimization synchronously and returns
    the result.  Can take 10-30 seconds depending on data volume.
    """
    auth_err = _require_api_key()
    if auth_err is not None:
        return auth_err

    def _handler():
        from accuracy.parameter_tuner import AutoTuner
        tuner = AutoTuner()
        result = tuner.run_daily_tuning()
        return jsonify({"success": True, "result": result})
    return _safe_json(_handler)


@accuracy_bp.route("/accuracy/tuner/params", methods=["GET"])
def accuracy_tuner_params():
    """
    Get all current tunable parameters across all algorithms.

    Returns the current values read from the algorithm Python files.
    """
    def _handler():
        from accuracy.config_manager import get_all_tunable_params, TUNABLE_PARAMS
        current = get_all_tunable_params()

        # Enrich with metadata (bounds, descriptions)
        enriched = {}
        for algo, params in current.items():
            algo_meta = TUNABLE_PARAMS.get(algo, {})
            enriched[algo] = {}
            for param_name, value in params.items():
                meta = algo_meta.get(param_name, {})
                enriched[algo][param_name] = {
                    "value": value,
                    "type": meta.get("type", "unknown"),
                    "default": meta.get("default"),
                    "min": meta.get("min"),
                    "max": meta.get("max"),
                    "description": meta.get("description", ""),
                }

        return jsonify({
            "success": True,
            "algorithms": enriched,
            "total_algorithms": len(enriched),
        })
    return _safe_json(_handler)


@accuracy_bp.route("/accuracy/tuner/params/<string:algorithm>", methods=["POST"])
def accuracy_tuner_set_params(algorithm: str):
    """
    Manually set parameters for a specific algorithm.

    Requires ``X-API-KEY`` header.

    Body (JSON)::

        {"params": {"FIRST_HALF_SHARE": 0.44}}
    """
    auth_err = _require_api_key()
    if auth_err is not None:
        return auth_err

    def _handler():
        data = request.get_json(silent=True) or {}
        params = data.get("params")

        if not params or not isinstance(params, dict):
            return jsonify({
                "success": False,
                "error": "Missing or invalid 'params' dict in request body",
            }), 400

        from accuracy.config_manager import write_algorithm_params, read_algorithm_params

        # Read current values for comparison
        before = read_algorithm_params(algorithm)

        success = write_algorithm_params(algorithm, params)
        if not success:
            return jsonify({
                "success": False,
                "error": f"Failed to write params for {algorithm}",
            }), 500

        after = read_algorithm_params(algorithm)

        return jsonify({
            "success": True,
            "algorithm": algorithm,
            "before": before,
            "after": after,
        })
    return _safe_json(_handler)


@accuracy_bp.route("/accuracy/tuner/backups/<string:algorithm>", methods=["GET"])
def accuracy_tuner_backups(algorithm: str):
    """List available backup files for an algorithm."""
    def _handler():
        from accuracy.config_manager import list_backups
        backups = list_backups(algorithm, limit=20)
        return jsonify({
            "success": True,
            "algorithm": algorithm,
            "backups": backups,
            "total": len(backups),
        })
    return _safe_json(_handler)


@accuracy_bp.route("/accuracy/tuner/rollback/<string:algorithm>", methods=["POST"])
def accuracy_tuner_rollback(algorithm: str):
    """
    Rollback an algorithm to a previous backup.

    Requires ``X-API-KEY`` header.

    Body (JSON)::

        {"backup_path": "/app/analysis/corner_predictions.py.bak.20260329_040000"}
    """
    auth_err = _require_api_key()
    if auth_err is not None:
        return auth_err

    def _handler():
        data = request.get_json(silent=True) or {}
        backup_path = data.get("backup_path")

        if not backup_path:
            return jsonify({
                "success": False,
                "error": "Missing 'backup_path' in request body",
            }), 400

        from accuracy.config_manager import rollback_algorithm

        success = rollback_algorithm(algorithm, backup_path)
        if not success:
            return jsonify({
                "success": False,
                "error": f"Rollback failed for {algorithm}",
            }), 500

        return jsonify({
            "success": True,
            "algorithm": algorithm,
            "restored_from": backup_path,
        })
    return _safe_json(_handler)


# ============================================================================
# 2.  ML Monitor compatible endpoints  (/reports, /report/<date>, /latest)
#
#     The awastats2x frontend proxies to /api/v1/reports etc.
#     These aliases expose the same data under those shorter paths.
# ============================================================================

@accuracy_bp.route("/reports", methods=["GET"])
def ml_monitor_list_reports():
    """ML Monitor compat: list available report dates."""
    def _handler():
        limit = request.args.get("limit", 30, type=int)
        reports = list_available_reports(limit=limit)
        return jsonify({
            "success": True,
            "reports": reports,
            "total": len(reports),
        })
    return _safe_json(_handler)


@accuracy_bp.route("/report/<string:target_date>", methods=["GET"])
def ml_monitor_get_report(target_date: str):
    """ML Monitor compat: get report for a date."""
    def _handler():
        try:
            datetime.strptime(target_date, "%Y-%m-%d")
        except ValueError:
            return jsonify({
                "success": False,
                "error": "Invalid date format. Use YYYY-MM-DD.",
            }), 400
        report = generate_daily_report(target_date)
        return jsonify({"success": True, "report": report})
    return _safe_json(_handler)


@accuracy_bp.route("/latest", methods=["GET"])
def ml_monitor_latest_report():
    """ML Monitor compat: get the latest report."""
    def _handler():
        dates = list_available_reports(limit=1)
        if not dates:
            return jsonify({
                "success": True,
                "report": None,
                "message": "No accuracy data available yet",
            })
        report = generate_daily_report(dates[0])
        return jsonify({"success": True, "report": report})
    return _safe_json(_handler)
