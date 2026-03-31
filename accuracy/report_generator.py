"""
Report Generator — builds accuracy reports for the ML Monitor dashboard.

Queries ``prediction_results`` and ``algorithm_accuracy`` tables to produce
comprehensive reports including per-algorithm breakdowns, confidence
calibration analysis, league-level hot/cold spots, and trend tracking.

Main entry points::

    generate_daily_report(target_date)   -> dict
    generate_period_report(start, end)   -> dict
    list_available_reports(limit=30)      -> list[str]
"""

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from accuracy.db import execute_query

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SOURCE_NAME = "eagle"
DEFAULT_PERIOD_DAYS = 7
TARGET_ACCURACY_PCT = 85.0

# Confidence tier definitions (Turkish labels for the UI).
CONFIDENCE_TIERS = [
    {"label": "Cok Yuksek (90+)", "min": 90, "max": 100},
    {"label": "Yuksek (75-89)", "min": 75, "max": 89},
    {"label": "Orta (60-74)", "min": 60, "max": 74},
    {"label": "Dusuk (<60)", "min": 0, "max": 59},
]

# Win-rate thresholds for strong / weak classification.
STRONG_THRESHOLD = 65.0
WEAK_THRESHOLD = 40.0
MIN_SAMPLE_SIZE = 5  # Minimum predictions to include in league analysis.
OVERCONFIDENCE_ALERT_GAP = 15.0  # pp gap between expected & actual.


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def _safe_query(sql: str, params=None) -> List[Dict[str, Any]]:
    """Execute a query and return rows, returning [] on error."""
    try:
        rows = execute_query(sql, params, fetch=True)
        return rows if rows else []
    except Exception as exc:
        logger.error("[ReportGen] Query failed: %s — %s", exc, sql[:120])
        return []


def _pct(numerator: int, denominator: int) -> float:
    """Safe percentage calculation."""
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100, 2)


# ---------------------------------------------------------------------------
# Data loaders (period-based)
# ---------------------------------------------------------------------------

def _load_prediction_results(start_date: str, end_date: str) -> List[Dict]:
    """Load all resolved prediction results for a date range."""
    return _safe_query(
        """
        SELECT date, match_id, sport, algorithm, market, prediction,
               confidence, actual_result, is_correct,
               home_team, away_team, league,
               home_score, away_score, total_goals,
               total_corners, total_cards
        FROM prediction_results
        WHERE date >= %s AND date <= %s
          AND is_correct IS NOT NULL
        ORDER BY date, match_id
        """,
        (start_date, end_date),
    )


def _load_algorithm_accuracy(start_date: str, end_date: str) -> List[Dict]:
    """Load aggregated algorithm accuracy rows for a date range."""
    return _safe_query(
        """
        SELECT date, sport, algorithm,
               total_predictions, correct_predictions,
               accuracy_pct, avg_confidence
        FROM algorithm_accuracy
        WHERE date >= %s AND date <= %s
        ORDER BY date, algorithm
        """,
        (start_date, end_date),
    )


# ---------------------------------------------------------------------------
# Report section builders
# ---------------------------------------------------------------------------

def _build_summary(
    rows: List[Dict],
    prev_rows: List[Dict],
) -> Dict[str, Any]:
    """
    Build the top-level summary block.

    ``rows`` = current period, ``prev_rows`` = previous period (for trend).
    """
    total = len(rows)
    wins = sum(1 for r in rows if r["is_correct"] is True)
    losses = total - wins
    win_rate = _pct(wins, total)

    # Previous period stats for trend calculation.
    prev_total = len(prev_rows)
    prev_wins = sum(1 for r in prev_rows if r["is_correct"] is True)
    prev_rate = _pct(prev_wins, prev_total)

    if total < 10 or prev_total < 10:
        trend = "yetersiz_veri"
        trend_change = 0.0
    else:
        trend_change = round(win_rate - prev_rate, 2)
        if trend_change > 1.0:
            trend = "yukseliyor"
        elif trend_change < -1.0:
            trend = "dusuyor"
        else:
            trend = "stabil"

    return {
        "total_predictions": total,
        "overall_win_rate": win_rate,
        "total_wins": wins,
        "total_losses": losses,
        "trend": trend,
        "trend_change": trend_change,
        "sources": {
            SOURCE_NAME: {
                "total": total,
                "wins": wins,
                "win_rate": win_rate,
            }
        },
    }


def _build_market_performance(rows: List[Dict]) -> List[Dict]:
    """Per-market (algorithm) win/loss breakdown."""
    stats: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {"total": 0, "wins": 0, "losses": 0}
    )
    for r in rows:
        key = r["algorithm"]
        stats[key]["total"] += 1
        if r["is_correct"]:
            stats[key]["wins"] += 1
        else:
            stats[key]["losses"] += 1

    result = []
    for market, s in sorted(stats.items(), key=lambda x: x[0]):
        result.append({
            "source": SOURCE_NAME,
            "sport": "football",
            "market": market,
            "total": s["total"],
            "wins": s["wins"],
            "losses": s["losses"],
            "win_rate": _pct(s["wins"], s["total"]),
        })
    return result


def _build_algorithm_comparison(rows: List[Dict]) -> List[Dict]:
    """
    Per-algorithm rows plus a TOPLAM (total) row per algorithm.

    Since algorithm == market in Eagle, we emit one row per algorithm
    and one aggregate TOPLAM row per algorithm for the UI table.
    """
    stats: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {"total": 0, "wins": 0}
    )
    for r in rows:
        algo = r["algorithm"]
        stats[algo]["total"] += 1
        if r["is_correct"]:
            stats[algo]["wins"] += 1

    result = []
    for algo, s in sorted(stats.items(), key=lambda x: x[0]):
        wr = _pct(s["wins"], s["total"])
        # Per-market row.
        result.append({
            "source": SOURCE_NAME,
            "algorithm": algo,
            "market": algo,
            "total": s["total"],
            "wins": s["wins"],
            "win_rate": wr,
        })
        # TOPLAM row (same values since algorithm == market).
        result.append({
            "source": SOURCE_NAME,
            "algorithm": algo,
            "market": "TOPLAM",
            "total": s["total"],
            "wins": s["wins"],
            "win_rate": wr,
        })

    return result


def _build_confidence_accuracy(rows: List[Dict]) -> List[Dict]:
    """
    Confidence calibration: bucket predictions by confidence tier and
    compare expected vs actual accuracy.
    """
    buckets: Dict[str, Dict[str, Any]] = {}
    for tier in CONFIDENCE_TIERS:
        buckets[tier["label"]] = {
            "total": 0,
            "wins": 0,
            "confidence_sum": 0.0,
            "min": tier["min"],
            "max": tier["max"],
        }

    for r in rows:
        conf = r.get("confidence") or 0
        for tier in CONFIDENCE_TIERS:
            if tier["min"] <= conf <= tier["max"]:
                b = buckets[tier["label"]]
                b["total"] += 1
                b["confidence_sum"] += conf
                if r["is_correct"]:
                    b["wins"] += 1
                break

    result = []
    for tier in CONFIDENCE_TIERS:
        b = buckets[tier["label"]]
        total = b["total"]
        if total == 0:
            continue
        actual_rate = _pct(b["wins"], total)
        expected_rate = round(b["confidence_sum"] / total, 1)
        gap = round(expected_rate - actual_rate, 1)
        result.append({
            "source": SOURCE_NAME,
            "tier": tier["label"],
            "total": total,
            "wins": b["wins"],
            "actual_rate": actual_rate,
            "expected_rate": expected_rate,
            "gap": gap,
            "overconfident": gap > 0,
        })

    return result


def _build_overconfidence_alerts(
    confidence_rows: List[Dict],
) -> List[Dict]:
    """Extract entries where the calibration gap exceeds the threshold."""
    return [
        r for r in confidence_rows
        if r.get("gap", 0) > OVERCONFIDENCE_ALERT_GAP
    ]


def _build_league_analysis(
    rows: List[Dict],
) -> tuple[List[Dict], List[Dict], List[Dict]]:
    """
    League-level analysis: identify weak spots, strong spots, and full
    league performance listing.

    Returns (weak_spots, strong_spots, league_performance).
    """
    # Aggregate by (league, market).
    league_stats: Dict[tuple, Dict[str, int]] = defaultdict(
        lambda: {"total": 0, "wins": 0, "losses": 0}
    )
    for r in rows:
        league = r.get("league") or "Bilinmeyen"
        market = r["algorithm"]
        key = (league, market)
        league_stats[key]["total"] += 1
        if r["is_correct"]:
            league_stats[key]["wins"] += 1
        else:
            league_stats[key]["losses"] += 1

    weak = []
    strong = []
    all_leagues = []

    for (league, market), s in league_stats.items():
        if s["total"] < MIN_SAMPLE_SIZE:
            continue
        wr = _pct(s["wins"], s["total"])
        entry = {
            "source": SOURCE_NAME,
            "league": league,
            "market": market,
            "total": s["total"],
            "wins": s["wins"],
            "losses": s["losses"],
            "win_rate": wr,
        }
        all_leagues.append(entry)

        if wr < WEAK_THRESHOLD:
            weak.append({**entry, "status": "weak"})
        elif wr >= STRONG_THRESHOLD:
            strong.append({**entry, "status": "strong"})

    # Sort: weak ascending, strong descending.
    weak.sort(key=lambda x: x["win_rate"])
    strong.sort(key=lambda x: x["win_rate"], reverse=True)
    all_leagues.sort(key=lambda x: (-x["total"], -x["win_rate"]))

    return weak, strong, all_leagues


def _build_banko_performance(rows: List[Dict]) -> List[Dict]:
    """
    Banko performance: predictions with confidence >= 80.
    """
    banko_rows = [r for r in rows if (r.get("confidence") or 0) >= 80]
    if not banko_rows:
        return []

    stats: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {"total": 0, "wins": 0}
    )
    for r in banko_rows:
        algo = r["algorithm"]
        stats[algo]["total"] += 1
        if r["is_correct"]:
            stats[algo]["wins"] += 1

    result = []
    for algo, s in sorted(stats.items()):
        result.append({
            "source": SOURCE_NAME,
            "algorithm": algo,
            "total": s["total"],
            "wins": s["wins"],
            "win_rate": _pct(s["wins"], s["total"]),
        })
    return result


def _build_recommendations(
    market_perf: List[Dict],
    confidence_acc: List[Dict],
) -> List[str]:
    """
    Generate actionable Turkish-language recommendations from the data.
    """
    recs: List[str] = []

    # Strong/weak markets.
    for mp in market_perf:
        wr = mp["win_rate"]
        market = mp["market"]
        total = mp["total"]
        if wr >= STRONG_THRESHOLD and total >= MIN_SAMPLE_SIZE:
            recs.append(
                f"GUCLU: {market} market'i 7 gunluk ortalama %{wr} - iyi performans"
            )
        elif wr < WEAK_THRESHOLD and total >= MIN_SAMPLE_SIZE:
            recs.append(
                f"ZAYIF: {market} market'i %{wr} isabet - iyilestirme gerekli"
            )

    # Overconfidence alerts.
    for ca in confidence_acc:
        if ca.get("gap", 0) > OVERCONFIDENCE_ALERT_GAP:
            tier = ca["tier"]
            gap = ca["gap"]
            recs.append(
                f"DIKKAT: {tier} seviyesi asiri guvenli (fark: {gap}pp) - kalibrasyon gerekli"
            )

    if not recs:
        recs.append("Genel performans stabil - devam edin")

    return recs


def _build_accuracy_dashboard(
    algo_rows: List[Dict],
    pred_rows: List[Dict],
    start_date: str,
    end_date: str,
) -> Dict[str, Any]:
    """
    Build the ``accuracy_dashboard`` sub-object used by the frontend
    dashboard charts.
    """
    # --- daily_accuracy: overall accuracy per day ---
    daily_stats: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {"total": 0, "wins": 0}
    )
    for r in pred_rows:
        d = str(r["date"])
        daily_stats[d]["total"] += 1
        if r["is_correct"]:
            daily_stats[d]["wins"] += 1

    daily_accuracy = []
    for d in sorted(daily_stats.keys()):
        s = daily_stats[d]
        daily_accuracy.append({
            "date": d,
            "accuracy_pct": _pct(s["wins"], s["total"]),
            "total": s["total"],
        })

    # --- algorithm_history: per-algorithm per-day accuracy ---
    algo_daily: Dict[str, Dict[str, Dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: {"total": 0, "wins": 0})
    )
    for r in pred_rows:
        d = str(r["date"])
        algo = r["algorithm"]
        algo_daily[algo][d]["total"] += 1
        if r["is_correct"]:
            algo_daily[algo][d]["wins"] += 1

    algorithm_history: Dict[str, List[Dict]] = {}
    for algo in sorted(algo_daily.keys()):
        history = []
        for d in sorted(algo_daily[algo].keys()):
            s = algo_daily[algo][d]
            history.append({
                "date": d,
                "accuracy_pct": _pct(s["wins"], s["total"]),
            })
        algorithm_history[algo] = history

    # --- best/worst algorithm (over entire period) ---
    algo_totals: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {"total": 0, "wins": 0}
    )
    for r in pred_rows:
        algo = r["algorithm"]
        algo_totals[algo]["total"] += 1
        if r["is_correct"]:
            algo_totals[algo]["wins"] += 1

    best_algo = {"name": "", "accuracy_pct": 0.0}
    worst_algo = {"name": "", "accuracy_pct": 100.0}

    for algo, s in algo_totals.items():
        if s["total"] < MIN_SAMPLE_SIZE:
            continue
        pct = _pct(s["wins"], s["total"])
        if pct > best_algo["accuracy_pct"]:
            best_algo = {"name": algo, "accuracy_pct": pct}
        if pct < worst_algo["accuracy_pct"]:
            worst_algo = {"name": algo, "accuracy_pct": pct}

    # Handle case where no algorithms met the sample threshold.
    if not best_algo["name"]:
        best_algo = {"name": "n/a", "accuracy_pct": 0.0}
    if not worst_algo["name"]:
        worst_algo = {"name": "n/a", "accuracy_pct": 0.0}

    # --- target progress ---
    overall_total = sum(s["total"] for s in algo_totals.values())
    overall_wins = sum(s["wins"] for s in algo_totals.values())
    current_pct = _pct(overall_wins, overall_total)

    # Determine if trend is improving (compare first half vs second half).
    sorted_days = sorted(daily_accuracy, key=lambda x: x["date"])
    improving = False
    if len(sorted_days) >= 4:
        mid = len(sorted_days) // 2
        first_half_pcts = [d["accuracy_pct"] for d in sorted_days[:mid]]
        second_half_pcts = [d["accuracy_pct"] for d in sorted_days[mid:]]
        first_avg = sum(first_half_pcts) / len(first_half_pcts) if first_half_pcts else 0
        second_avg = sum(second_half_pcts) / len(second_half_pcts) if second_half_pcts else 0
        improving = second_avg > first_avg

    return {
        "daily_accuracy": daily_accuracy,
        "algorithm_history": algorithm_history,
        "best_algorithm": best_algo,
        "worst_algorithm": worst_algo,
        "target_progress": {
            "target_pct": TARGET_ACCURACY_PCT,
            "current_pct": current_pct,
            "gap": round(TARGET_ACCURACY_PCT - current_pct, 2),
            "improving": improving,
        },
    }


def _build_trends(
    summary: Dict,
    prev_rows: List[Dict],
) -> Dict[str, Any]:
    """Build the trends sub-object."""
    prev_total = len(prev_rows)
    prev_wins = sum(1 for r in prev_rows if r["is_correct"] is True)
    prev_rate = _pct(prev_wins, prev_total)

    return {
        "trend": summary.get("trend", "yetersiz_veri"),
        "recent": {
            "total": summary["total_predictions"],
            "wins": summary["total_wins"],
            "win_rate": summary["overall_win_rate"],
        },
        "previous": {
            "total": prev_total,
            "wins": prev_wins,
            "win_rate": prev_rate,
        },
        "change": summary.get("trend_change", 0.0),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_daily_report(target_date: str) -> Dict[str, Any]:
    """
    Generate a comprehensive accuracy report for a single date.

    The report contains a 7-day rolling window centred on the target date
    for trend analysis, plus the target date's individual results.

    Args:
        target_date: Date string in YYYY-MM-DD format.

    Returns:
        Complete report dictionary matching the ML Monitor UI schema.
    """
    try:
        dt = datetime.strptime(target_date, "%Y-%m-%d").date()
    except ValueError:
        return {"error": f"Invalid date format: {target_date}"}

    # Define the period: target_date minus 6 days .. target_date (7 days).
    period_start = (dt - timedelta(days=DEFAULT_PERIOD_DAYS - 1)).strftime("%Y-%m-%d")
    period_end = target_date

    # Previous period for trend comparison (same length, immediately prior).
    prev_end = (dt - timedelta(days=DEFAULT_PERIOD_DAYS)).strftime("%Y-%m-%d")
    prev_start = (dt - timedelta(days=2 * DEFAULT_PERIOD_DAYS - 1)).strftime("%Y-%m-%d")

    # Load data.
    pred_rows = _load_prediction_results(period_start, period_end)
    algo_rows = _load_algorithm_accuracy(period_start, period_end)
    prev_pred_rows = _load_prediction_results(prev_start, prev_end)

    if not pred_rows:
        return {
            "report_date": target_date,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "error": "Bu tarih icin veri bulunamadi",
            "period": {"start": period_start, "end": period_end},
            "summary": {
                "total_predictions": 0,
                "overall_win_rate": 0.0,
                "total_wins": 0,
                "total_losses": 0,
                "trend": "yetersiz_veri",
                "trend_change": 0.0,
                "sources": {SOURCE_NAME: {"total": 0, "wins": 0, "win_rate": 0.0}},
            },
            "market_performance": [],
            "algorithm_comparison": [],
            "confidence_accuracy": [],
            "overconfidence_alerts": [],
            "weak_spots": [],
            "strong_spots": [],
            "league_performance": [],
            "time_slots": [],
            "banko_performance": [],
            "trends": {
                "trend": "yetersiz_veri",
                "recent": {"total": 0, "wins": 0, "win_rate": 0.0},
                "previous": {"total": 0, "wins": 0, "win_rate": 0.0},
                "change": 0.0,
            },
            "recommendations": [],
            "accuracy_dashboard": {
                "daily_accuracy": [],
                "algorithm_history": {},
                "best_algorithm": {"name": "n/a", "accuracy_pct": 0.0},
                "worst_algorithm": {"name": "n/a", "accuracy_pct": 0.0},
                "target_progress": {
                    "target_pct": TARGET_ACCURACY_PCT,
                    "current_pct": 0.0,
                    "gap": TARGET_ACCURACY_PCT,
                    "improving": False,
                },
            },
        }

    # Build sections.
    summary = _build_summary(pred_rows, prev_pred_rows)
    market_perf = _build_market_performance(pred_rows)
    algo_comp = _build_algorithm_comparison(pred_rows)
    conf_acc = _build_confidence_accuracy(pred_rows)
    overconf = _build_overconfidence_alerts(conf_acc)
    weak, strong, league_perf = _build_league_analysis(pred_rows)
    banko = _build_banko_performance(pred_rows)
    recs = _build_recommendations(market_perf, conf_acc)
    trends = _build_trends(summary, prev_pred_rows)
    dashboard = _build_accuracy_dashboard(
        algo_rows, pred_rows, period_start, period_end
    )

    report = {
        "report_date": target_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "period": {"start": period_start, "end": period_end},
        "summary": summary,
        "market_performance": market_perf,
        "algorithm_comparison": algo_comp,
        "confidence_accuracy": conf_acc,
        "overconfidence_alerts": overconf,
        "weak_spots": weak,
        "strong_spots": strong,
        "league_performance": league_perf,
        "time_slots": [],  # Not available without match_time in prediction_results.
        "banko_performance": banko,
        "trends": trends,
        "recommendations": recs,
        "accuracy_dashboard": dashboard,
    }

    logger.info(
        "[ReportGen] Daily report for %s: %d predictions, %.1f%% accuracy",
        target_date,
        summary["total_predictions"],
        summary["overall_win_rate"],
    )

    return report


def generate_period_report(start_date: str, end_date: str) -> Dict[str, Any]:
    """
    Generate an aggregated report for an arbitrary date range.

    Args:
        start_date: Start date (YYYY-MM-DD), inclusive.
        end_date:   End date (YYYY-MM-DD), inclusive.

    Returns:
        Report dictionary with the same structure as daily reports.
    """
    try:
        dt_start = datetime.strptime(start_date, "%Y-%m-%d").date()
        dt_end = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        return {"error": "Invalid date format. Use YYYY-MM-DD."}

    if dt_start > dt_end:
        return {"error": "start_date must be before end_date"}

    period_days = (dt_end - dt_start).days + 1

    # Previous period of equal length for trend.
    prev_end = (dt_start - timedelta(days=1)).strftime("%Y-%m-%d")
    prev_start = (dt_start - timedelta(days=period_days)).strftime("%Y-%m-%d")

    pred_rows = _load_prediction_results(start_date, end_date)
    algo_rows = _load_algorithm_accuracy(start_date, end_date)
    prev_pred_rows = _load_prediction_results(prev_start, prev_end)

    if not pred_rows:
        return {
            "report_date": end_date,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "period": {"start": start_date, "end": end_date},
            "error": "Belirtilen tarih araliginda veri bulunamadi",
            "summary": {
                "total_predictions": 0,
                "overall_win_rate": 0.0,
                "total_wins": 0,
                "total_losses": 0,
                "trend": "yetersiz_veri",
                "trend_change": 0.0,
                "sources": {SOURCE_NAME: {"total": 0, "wins": 0, "win_rate": 0.0}},
            },
        }

    summary = _build_summary(pred_rows, prev_pred_rows)
    market_perf = _build_market_performance(pred_rows)
    algo_comp = _build_algorithm_comparison(pred_rows)
    conf_acc = _build_confidence_accuracy(pred_rows)
    overconf = _build_overconfidence_alerts(conf_acc)
    weak, strong, league_perf = _build_league_analysis(pred_rows)
    banko = _build_banko_performance(pred_rows)
    recs = _build_recommendations(market_perf, conf_acc)
    trends = _build_trends(summary, prev_pred_rows)
    dashboard = _build_accuracy_dashboard(
        algo_rows, pred_rows, start_date, end_date
    )

    return {
        "report_date": end_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "period": {"start": start_date, "end": end_date},
        "summary": summary,
        "market_performance": market_perf,
        "algorithm_comparison": algo_comp,
        "confidence_accuracy": conf_acc,
        "overconfidence_alerts": overconf,
        "weak_spots": weak,
        "strong_spots": strong,
        "league_performance": league_perf,
        "time_slots": [],
        "banko_performance": banko,
        "trends": trends,
        "recommendations": recs,
        "accuracy_dashboard": dashboard,
    }


def list_available_reports(limit: int = 30) -> List[str]:
    """
    List dates that have accuracy data, most recent first.

    Args:
        limit: Maximum number of dates to return.

    Returns:
        List of date strings in YYYY-MM-DD format.
    """
    rows = _safe_query(
        """
        SELECT DISTINCT date
        FROM algorithm_accuracy
        ORDER BY date DESC
        LIMIT %s
        """,
        (limit,),
    )
    return [str(r["date"]) for r in rows]
