"""
PostgreSQL connection pool and query helpers for the accuracy tracker.

Reads DATABASE_URL from environment (set in docker-compose.yml).
Provides a context-manager-based connection interface with auto-reconnect,
a simple execute_query() for single statements, and execute_many() for
batch inserts.
"""

import os
import time
import logging
import threading
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import psycopg2
import psycopg2.pool
import psycopg2.extras
from psycopg2 import OperationalError, InterfaceError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------
_pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None
_pool_lock = threading.Lock()

# Connection can come from DATABASE_URL or individual PG* env vars
DATABASE_URL = os.getenv("DATABASE_URL", "")
PGHOST = os.getenv("PGHOST", "")
PGPORT = os.getenv("PGPORT", "5432")
PGDATABASE = os.getenv("PGDATABASE", "awadb")
PGUSER = os.getenv("PGUSER", "")
PGPASSWORD = os.getenv("PGPASSWORD", "")

# Pool sizing
POOL_MIN_CONN = int(os.getenv("ACCURACY_POOL_MIN", "1"))
POOL_MAX_CONN = int(os.getenv("ACCURACY_POOL_MAX", "5"))

# Retry configuration
MAX_RECONNECT_ATTEMPTS = 3
RECONNECT_BACKOFF_BASE = 1.0  # seconds


# ---------------------------------------------------------------------------
# Pool lifecycle
# ---------------------------------------------------------------------------

def _get_connection_params() -> dict:
    """Build connection params from env vars.

    Prefers individual PG* env vars (avoids URL-encoding issues with
    special chars in passwords). Falls back to DATABASE_URL parsing.
    """
    # Prefer individual PG* env vars (set in docker-compose.yml)
    if PGHOST:
        return {
            "host": PGHOST,
            "port": int(PGPORT),
            "dbname": PGDATABASE,
            "user": PGUSER,
            "password": PGPASSWORD,
        }

    # Fallback: parse DATABASE_URL
    if DATABASE_URL:
        from urllib.parse import urlparse, unquote
        parsed = urlparse(DATABASE_URL)
        return {
            "host": parsed.hostname or "localhost",
            "port": parsed.port or 5432,
            "dbname": (parsed.path or "/awadb").lstrip("/"),
            "user": unquote(parsed.username or ""),
            "password": unquote(parsed.password or ""),
        }

    raise RuntimeError(
        "Neither PGHOST nor DATABASE_URL env var is set. "
        "Cannot connect to PostgreSQL for accuracy tracking."
    )


def _create_pool() -> psycopg2.pool.ThreadedConnectionPool:
    """Create a new ThreadedConnectionPool."""
    params = _get_connection_params()
    logger.info(
        "[AccuracyDB] Creating pool (min=%d, max=%d) → %s:%s/%s",
        POOL_MIN_CONN, POOL_MAX_CONN,
        params["host"], params["port"], params["dbname"],
    )
    return psycopg2.pool.ThreadedConnectionPool(
        minconn=POOL_MIN_CONN,
        maxconn=POOL_MAX_CONN,
        cursor_factory=psycopg2.extras.RealDictCursor,
        **params,
    )


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    """Return the module-level pool, creating it if needed (thread-safe)."""
    global _pool
    if _pool is not None and not _pool.closed:
        return _pool
    with _pool_lock:
        # Double-check after acquiring lock
        if _pool is not None and not _pool.closed:
            return _pool
        _pool = _create_pool()
        return _pool


def init_db() -> None:
    """
    Eagerly initialise the connection pool.

    Call once at application startup so that a misconfigured DATABASE_URL
    fails fast rather than on first query.
    """
    _get_pool()
    logger.info("[AccuracyDB] Pool initialised successfully")


def close_pool() -> None:
    """Shut down the pool cleanly (call on app teardown)."""
    global _pool
    with _pool_lock:
        if _pool is not None and not _pool.closed:
            _pool.closeall()
            logger.info("[AccuracyDB] Connection pool closed")
        _pool = None


# ---------------------------------------------------------------------------
# Connection context manager with auto-reconnect
# ---------------------------------------------------------------------------

@contextmanager
def get_conn():
    """
    Yield a psycopg2 connection from the pool.

    * Auto-commits on successful exit.
    * Rolls back on exception.
    * Returns the connection to the pool on exit.
    * If the connection is stale (server restarted, network blip), retries
      up to MAX_RECONNECT_ATTEMPTS times with exponential back-off.

    Usage::

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                rows = cur.fetchall()
    """
    pool = _get_pool()
    conn = None
    last_err: Optional[Exception] = None

    for attempt in range(1, MAX_RECONNECT_ATTEMPTS + 1):
        try:
            conn = pool.getconn()
            # Verify the connection is alive
            conn.isolation_level  # triggers InterfaceError if closed
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            break
        except (OperationalError, InterfaceError) as exc:
            last_err = exc
            logger.warning(
                "[AccuracyDB] Stale connection on attempt %d/%d: %s",
                attempt, MAX_RECONNECT_ATTEMPTS, exc,
            )
            # Return the bad connection and discard it
            if conn is not None:
                try:
                    pool.putconn(conn, close=True)
                except Exception:
                    pass
                conn = None
            if attempt < MAX_RECONNECT_ATTEMPTS:
                wait = RECONNECT_BACKOFF_BASE * (2 ** (attempt - 1))
                time.sleep(wait)
            else:
                # All retries exhausted - try recreating the entire pool
                logger.error(
                    "[AccuracyDB] All %d reconnect attempts failed, recreating pool",
                    MAX_RECONNECT_ATTEMPTS,
                )
                close_pool()
                pool = _get_pool()
                try:
                    conn = pool.getconn()
                except Exception as pool_err:
                    raise RuntimeError(
                        f"Cannot obtain DB connection after pool recreation: {pool_err}"
                    ) from last_err

    if conn is None:
        raise RuntimeError(
            f"Failed to acquire DB connection after {MAX_RECONNECT_ATTEMPTS} attempts"
        )

    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        try:
            pool.putconn(conn)
        except Exception:
            # Pool may have been closed between yield and finally
            pass


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def execute_query(
    sql: str,
    params: Union[Tuple, Dict, None] = None,
    *,
    fetch: bool = True,
) -> Optional[List[Dict[str, Any]]]:
    """
    Execute a single SQL statement and optionally return rows.

    Args:
        sql:    SQL string (may contain %s or %(name)s placeholders).
        params: Parameters for the query.
        fetch:  If True (default), call fetchall() and return a list of
                RealDictRow dicts.  If False (INSERT/UPDATE/DELETE), return
                None.

    Returns:
        List of dicts when fetch=True, None otherwise.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            if fetch:
                return cur.fetchall()
            return None


def execute_many(
    sql: str,
    params_list: Sequence[Union[Tuple, Dict]],
) -> int:
    """
    Execute a parameterised statement for each item in *params_list*.

    Uses psycopg2.extras.execute_batch for performance (sends multiple
    statements per round-trip).

    Args:
        sql:         SQL template with %s or %(name)s placeholders.
        params_list: Iterable of parameter tuples/dicts.

    Returns:
        Number of rows affected (sum of rowcounts).
    """
    if not params_list:
        return 0

    with get_conn() as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_batch(cur, sql, params_list, page_size=100)
            return cur.rowcount


# ---------------------------------------------------------------------------
# Schema bootstrap (idempotent - safe to call every startup)
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS prediction_results (
    id              SERIAL PRIMARY KEY,
    date            DATE NOT NULL,
    match_id        INTEGER NOT NULL,
    sport           TEXT DEFAULT 'football',
    algorithm       TEXT NOT NULL,
    market          TEXT NOT NULL,
    prediction      TEXT NOT NULL,
    confidence      REAL,
    actual_result   TEXT,
    is_correct      BOOLEAN,
    home_team       TEXT,
    away_team       TEXT,
    league          TEXT,
    home_score      INTEGER,
    away_score      INTEGER,
    ht_home_score   INTEGER,
    ht_away_score   INTEGER,
    total_goals     INTEGER,
    total_corners   INTEGER,
    total_cards     INTEGER,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pred_results_date
    ON prediction_results (date);
CREATE INDEX IF NOT EXISTS idx_pred_results_algorithm
    ON prediction_results (algorithm);
CREATE INDEX IF NOT EXISTS idx_pred_results_match
    ON prediction_results (match_id, date);
CREATE UNIQUE INDEX IF NOT EXISTS idx_pred_results_unique
    ON prediction_results (date, match_id, algorithm, market);

CREATE TABLE IF NOT EXISTS algorithm_accuracy (
    id                   SERIAL PRIMARY KEY,
    date                 DATE NOT NULL,
    sport                TEXT DEFAULT 'football',
    algorithm            TEXT NOT NULL,
    total_predictions    INTEGER,
    correct_predictions  INTEGER,
    accuracy_pct         REAL,
    avg_confidence       REAL,
    parameters           JSONB,
    created_at           TIMESTAMPTZ DEFAULT now(),
    UNIQUE(date, sport, algorithm)
);

CREATE INDEX IF NOT EXISTS idx_algo_accuracy_date
    ON algorithm_accuracy (date);
CREATE INDEX IF NOT EXISTS idx_algo_accuracy_algo
    ON algorithm_accuracy (algorithm);

CREATE TABLE IF NOT EXISTS parameter_history (
    id               SERIAL PRIMARY KEY,
    sport            TEXT DEFAULT 'football',
    algorithm        TEXT NOT NULL,
    parameter_name   TEXT NOT NULL,
    old_value        REAL,
    new_value        REAL,
    reason           TEXT,
    accuracy_before  REAL,
    accuracy_after   REAL,
    applied_at       TIMESTAMPTZ DEFAULT now()
);
"""


def ensure_schema() -> None:
    """Create accuracy tables if they do not exist yet (idempotent)."""
    logger.info("[AccuracyDB] Ensuring accuracy schema exists")
    execute_query(_SCHEMA_SQL, fetch=False)
    logger.info("[AccuracyDB] Schema check complete")
