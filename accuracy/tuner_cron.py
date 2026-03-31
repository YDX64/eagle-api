"""
Tuner Cron — runs the AutoTuner daily in a background thread.

Schedules parameter optimization at ``TUNER_CRON_HOUR`` (default 04:00 UTC),
one hour after the accuracy calculation cron (03:00 UTC) so that fresh
accuracy data is available for the tuner to evaluate.

Usage from app startup::

    from accuracy.tuner_cron import start_tuner_cron, stop_tuner_cron
    start_tuner_cron()
    # ... on shutdown ...
    stop_tuner_cron()
"""

import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Hour of day (UTC) to run the daily tuning.
# Must be AFTER ACCURACY_CRON_HOUR (default 3) so accuracy data is fresh.
TUNER_CRON_HOUR = int(os.getenv("TUNER_CRON_HOUR", "4"))

# Initial delay after startup before the first check (seconds).
STARTUP_DELAY = int(os.getenv("TUNER_STARTUP_DELAY", "60"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seconds_until_next_run() -> float:
    """
    Return the number of seconds until the next scheduled tuner run
    (``TUNER_CRON_HOUR:00 UTC``).

    If that time has already passed today, returns seconds until tomorrow's run.
    """
    now = datetime.now(timezone.utc)
    target_today = now.replace(
        hour=TUNER_CRON_HOUR, minute=0, second=0, microsecond=0,
    )

    if now >= target_today:
        target = target_today + timedelta(days=1)
    else:
        target = target_today

    delta = (target - now).total_seconds()
    return max(delta, 0)


def _run_tuner_safe() -> Optional[dict]:
    """
    Execute the AutoTuner with full error isolation.

    Returns the summary dict on success, None on failure.
    """
    try:
        from accuracy.parameter_tuner import AutoTuner

        tuner = AutoTuner()
        result = tuner.run_daily_tuning()

        status = result.get("status", "unknown")
        checked = result.get("algorithms_checked", 0)
        tuned = result.get("algorithms_tuned", 0)
        elapsed = result.get("elapsed_seconds", 0)

        logger.info(
            "[TunerCron] Tuning completed: status=%s, checked=%d, "
            "tuned=%d, elapsed=%.1fs",
            status, checked, tuned, elapsed,
        )
        return result

    except Exception as exc:
        logger.error(
            "[TunerCron] Tuning failed: %s", exc, exc_info=True,
        )
        return None


# ---------------------------------------------------------------------------
# Cron Thread
# ---------------------------------------------------------------------------

class TunerCronThread(threading.Thread):
    """
    Runs the AutoTuner daily at ``TUNER_CRON_HOUR:00`` UTC.

    Daemon thread — dies automatically when the main process exits.
    """

    def __init__(self) -> None:
        super().__init__(daemon=True, name="TunerCronThread")
        self.running = True

    def run(self) -> None:
        logger.info(
            "[TunerCron] Started (daily at %02d:00 UTC, startup_delay=%ds)",
            TUNER_CRON_HOUR,
            STARTUP_DELAY,
        )

        # Initial delay to let the application finish starting up
        # and to let the accuracy cron potentially finish its work.
        self._sleep(STARTUP_DELAY)

        if not self.running:
            return

        # Ensure the tuner schema exists
        try:
            from accuracy.parameter_tuner import ensure_tuner_schema
            ensure_tuner_schema()
            logger.info("[TunerCron] Tuner schema verified")
        except Exception as exc:
            logger.error(
                "[TunerCron] Schema init failed — will retry later: %s", exc,
            )

        # Main loop: sleep until next scheduled run, then tune.
        while self.running:
            wait_seconds = _seconds_until_next_run()
            logger.info(
                "[TunerCron] Next tuning run in %.0f seconds (%.1f hours)",
                wait_seconds,
                wait_seconds / 3600,
            )

            # Sleep in 1-second intervals so stop() takes effect quickly.
            self._sleep(wait_seconds)

            if not self.running:
                break

            # Run the tuner
            logger.info("[TunerCron] Starting scheduled tuning run...")
            _run_tuner_safe()

        logger.info("[TunerCron] Stopped")

    def stop(self) -> None:
        """Signal the thread to stop. Returns immediately."""
        self.running = False

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

_cron_thread: Optional[TunerCronThread] = None


def start_tuner_cron() -> None:
    """Start the tuner cron thread (idempotent)."""
    global _cron_thread
    if _cron_thread is not None and _cron_thread.is_alive():
        logger.info("[TunerCron] Already running — skipping start")
        return
    _cron_thread = TunerCronThread()
    _cron_thread.start()
    logger.info("[TunerCron] Cron thread launched")


def stop_tuner_cron() -> None:
    """Stop the tuner cron thread (idempotent)."""
    global _cron_thread
    if _cron_thread is not None:
        _cron_thread.stop()
        logger.info("[TunerCron] Stop signal sent")
        _cron_thread = None
