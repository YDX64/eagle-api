"""
Accuracy Cron — runs daily accuracy calculations in a background thread.

Calculates prediction accuracy for yesterday's matches at a configurable
hour (default 03:00 UTC).  On startup, backfills any of the last 3 days
that are missing from the database.

After football accuracy is calculated, syncs basketball (Basket1) picks
via the basket1_bridge module.

Usage from app startup::

    from accuracy.accuracy_cron import start_accuracy_cron, stop_accuracy_cron
    start_accuracy_cron()
    # ... on shutdown ...
    stop_accuracy_cron()
"""

import logging
import os
import threading
import time
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from accuracy.db import execute_query, init_db, ensure_schema
from accuracy.accuracy_calculator import calculate_accuracy

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Hour of day (UTC) to run the daily accuracy calculation.
ACCURACY_CRON_HOUR = int(os.getenv("ACCURACY_CRON_HOUR", "3"))

# How many past days to check for missing data on startup.
BACKFILL_DAYS = int(os.getenv("ACCURACY_BACKFILL_DAYS", "3"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _date_has_accuracy(target_date: str) -> bool:
    """Check whether we already have accuracy data for *target_date*."""
    try:
        rows = execute_query(
            "SELECT 1 FROM algorithm_accuracy WHERE date = %s LIMIT 1",
            (target_date,),
        )
        return bool(rows)
    except Exception as exc:
        logger.warning(
            "[AccuracyCron] DB check failed for %s: %s", target_date, exc
        )
        return False


def _calculate_safe(target_date: str) -> Optional[dict]:
    """
    Run ``calculate_accuracy`` with full error isolation.

    Returns the summary dict on success, ``None`` on failure.
    """
    try:
        logger.info("[AccuracyCron] Calculating accuracy for %s", target_date)
        result = calculate_accuracy(target_date)

        if result.get("error"):
            logger.warning(
                "[AccuracyCron] Accuracy calculation for %s returned error: %s",
                target_date,
                result["error"],
            )
            return result

        total = result.get("total_determined", 0)
        correct = result.get("total_correct", 0)
        pct = result.get("overall_accuracy_pct", 0)
        elapsed = result.get("elapsed_seconds", 0)
        logger.info(
            "[AccuracyCron] %s done: %d/%d (%.1f%%) in %.1fs",
            target_date, correct, total, pct, elapsed,
        )
        return result

    except Exception as exc:
        logger.error(
            "[AccuracyCron] Accuracy calculation failed for %s: %s",
            target_date, exc, exc_info=True,
        )
        return None


def _sync_basket1_safe(target_date: str) -> Optional[dict]:
    """
    Sync basketball picks from Basket1 API with full error isolation.

    This is a separate step from football accuracy because basketball data
    comes from an external API (Basket1) rather than NowGoal.

    Returns the summary dict on success, ``None`` on failure.
    """
    try:
        from accuracy.basket1_bridge import sync_basket1_accuracy

        logger.info(
            "[AccuracyCron] Syncing Basket1 basketball accuracy for %s",
            target_date,
        )
        result = sync_basket1_accuracy(target_date)

        if result.get("error"):
            logger.warning(
                "[AccuracyCron] Basket1 sync for %s returned error: %s",
                target_date,
                result["error"],
            )
            return result

        total = result.get("total_determined", 0)
        correct = result.get("total_correct", 0)
        pct = result.get("overall_accuracy_pct", 0)
        elapsed = result.get("elapsed_seconds", 0)
        logger.info(
            "[AccuracyCron] Basket1 %s done: %d/%d (%.1f%%) in %.1fs",
            target_date, correct, total, pct, elapsed,
        )
        return result

    except ImportError:
        logger.warning(
            "[AccuracyCron] basket1_bridge not available, skipping basketball sync"
        )
        return None
    except Exception as exc:
        logger.error(
            "[AccuracyCron] Basket1 sync failed for %s: %s",
            target_date, exc, exc_info=True,
        )
        return None


def _date_has_basketball_accuracy(target_date: str) -> bool:
    """Check whether we already have basketball accuracy data for *target_date*."""
    try:
        rows = execute_query(
            "SELECT 1 FROM algorithm_accuracy WHERE date = %s AND sport = 'basketball' LIMIT 1",
            (target_date,),
        )
        return bool(rows)
    except Exception as exc:
        logger.warning(
            "[AccuracyCron] Basketball DB check failed for %s: %s", target_date, exc
        )
        return False


def _backfill() -> None:
    """Check the last BACKFILL_DAYS days and calculate any missing ones."""
    logger.info(
        "[AccuracyCron] Backfill check: scanning last %d days", BACKFILL_DAYS
    )
    today = date.today()
    filled = 0
    skipped = 0
    basket_filled = 0
    basket_skipped = 0

    for days_ago in range(1, BACKFILL_DAYS + 1):
        target = today - timedelta(days=days_ago)
        target_str = target.strftime("%Y-%m-%d")

        # Football accuracy backfill
        if _date_has_accuracy(target_str):
            logger.debug("[AccuracyCron] Backfill skip %s (already exists)", target_str)
            skipped += 1
        else:
            logger.info("[AccuracyCron] Backfill: calculating %s", target_str)
            _calculate_safe(target_str)
            filled += 1

        # Basketball accuracy backfill (Basket1)
        if _date_has_basketball_accuracy(target_str):
            logger.debug(
                "[AccuracyCron] Backfill skip basketball %s (already exists)",
                target_str,
            )
            basket_skipped += 1
        else:
            logger.info("[AccuracyCron] Backfill: syncing basketball %s", target_str)
            _sync_basket1_safe(target_str)
            basket_filled += 1

    logger.info(
        "[AccuracyCron] Backfill complete: football %d calculated/%d skipped, "
        "basketball %d synced/%d skipped",
        filled, skipped, basket_filled, basket_skipped,
    )


def _seconds_until_next_run() -> float:
    """
    Return the number of seconds until the next scheduled run
    (``ACCURACY_CRON_HOUR:00 UTC``).

    If that time has already passed today, return seconds until tomorrow's
    run.
    """
    now = datetime.now(timezone.utc)
    target_today = now.replace(
        hour=ACCURACY_CRON_HOUR, minute=0, second=0, microsecond=0
    )

    if now >= target_today:
        # Already passed today -- target tomorrow.
        target = target_today + timedelta(days=1)
    else:
        target = target_today

    delta = (target - now).total_seconds()
    return max(delta, 0)


# ---------------------------------------------------------------------------
# Cron Thread
# ---------------------------------------------------------------------------

class AccuracyCronThread(threading.Thread):
    """Runs accuracy calculation daily at ``ACCURACY_CRON_HOUR:00`` UTC."""

    def __init__(self) -> None:
        super().__init__(daemon=True, name="AccuracyCronThread")
        self.running = True

    # ------------------------------------------------------------------
    def run(self) -> None:
        logger.info(
            "[AccuracyCron] Started (daily at %02d:00 UTC, backfill=%d days)",
            ACCURACY_CRON_HOUR,
            BACKFILL_DAYS,
        )

        # Brief initial delay to let the application finish starting up.
        self._sleep(15)

        if not self.running:
            return

        # Ensure the database schema is ready.
        try:
            init_db()
            ensure_schema()
            logger.info("[AccuracyCron] Database schema verified")
        except Exception as exc:
            logger.error(
                "[AccuracyCron] DB init failed -- cron will retry later: %s",
                exc,
            )

        # Run backfill on startup.
        if self.running:
            try:
                _backfill()
            except Exception as exc:
                logger.error(
                    "[AccuracyCron] Backfill failed: %s", exc, exc_info=True
                )

        # Main loop: sleep until next scheduled run, then calculate.
        while self.running:
            wait_seconds = _seconds_until_next_run()
            logger.info(
                "[AccuracyCron] Next run in %.0f seconds (%.1f hours)",
                wait_seconds,
                wait_seconds / 3600,
            )

            # Sleep in 1-second intervals so stop() takes effect quickly.
            self._sleep(wait_seconds)

            if not self.running:
                break

            # Calculate yesterday's accuracy.
            yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
            _calculate_safe(yesterday)

            # Sync basketball (Basket1) accuracy after football.
            _sync_basket1_safe(yesterday)

        logger.info("[AccuracyCron] Stopped")

    # ------------------------------------------------------------------
    def stop(self) -> None:
        """Signal the thread to stop.  Returns immediately."""
        self.running = False

    # ------------------------------------------------------------------
    def _sleep(self, seconds: float) -> None:
        """Sleep in 1-second chunks, checking ``self.running`` each tick."""
        remaining = seconds
        while remaining > 0 and self.running:
            chunk = min(remaining, 1.0)
            time.sleep(chunk)
            remaining -= chunk


# ---------------------------------------------------------------------------
# Module-level start / stop
# ---------------------------------------------------------------------------

_cron_thread: Optional[AccuracyCronThread] = None


def start_accuracy_cron() -> None:
    """Start the accuracy cron thread (idempotent)."""
    global _cron_thread
    if _cron_thread is not None and _cron_thread.is_alive():
        logger.info("[AccuracyCron] Already running -- skipping start")
        return
    _cron_thread = AccuracyCronThread()
    _cron_thread.start()
    logger.info("[AccuracyCron] Cron thread launched")


def stop_accuracy_cron() -> None:
    """Stop the accuracy cron thread (idempotent)."""
    global _cron_thread
    if _cron_thread is not None:
        _cron_thread.stop()
        logger.info("[AccuracyCron] Stop signal sent")
        _cron_thread = None
