"""
db_pool.py  —  Shared PostgreSQL Connection Pool for HistoricalTrends
======================================================================
Provides a module-level ThreadedConnectionPool singleton used by
DBDataService (and any future services in this Flask app).

Design decisions
----------------
* ThreadedConnectionPool  — Flask runs with threads (not processes), so this
  is the correct pool class.  SimpleConnectionPool is NOT thread-safe.
* minconn=2, maxconn=10  — HistoricalTrends receives heavy analytical queries
  (wide date ranges, many tags).  2 always-warm connections handle baseline
  traffic; 10 caps DB load under burst.  Tune via HIST_POOL_MAX env var.
* Context manager `borrow_connection()` — guarantees connection is returned
  to pool even on exception; marks broken connections via `putconn(conn, close=True)`.
* Lazy init + auto-recreate — pool is created on first borrow; if pool is
  exhausted or all connections are dead, it is torn down and recreated once.
* keepalive probe — each borrowed connection gets a lightweight `SELECT 1`
  to detect stale TCP connections before handing to caller.

Usage
-----
    from db_pool import borrow_connection

    with borrow_connection() as conn:
        df = pd.read_sql(sql, conn, params=params)
    # connection automatically returned to pool here
"""

import os
import json
import logging
import threading
import contextlib
import psycopg2
import psycopg2.pool
import psycopg2.extras

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Load DB config from trends-config.json (single source of truth)
# Env vars HIST_DB_* override config file values — useful for containers/CI.
# NO credentials are hardcoded in this file.
# ──────────────────────────────────────────────────────────────────────────────

def _load_db_config() -> dict:
    """
    Load the Database section from trends-config.json.
    Env vars override file values:
      HIST_DB_HOST, HIST_DB_PORT, HIST_DB_NAME, HIST_DB_USER, HIST_DB_PASSWORD
      HIST_POOL_MIN, HIST_POOL_MAX, HIST_STMT_TIMEOUT_MS
    Raises RuntimeError if neither config file nor required env vars are present.
    """
    cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trends-config.json")
    file_db: dict = {}
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                full = json.load(f)
            file_db = full.get("Database", {})
        except Exception as exc:
            logger.warning("[DBPool] Could not read trends-config.json: %s", exc)
    else:
        logger.warning("[DBPool] trends-config.json not found at %s", cfg_path)

    def _get(env_key: str, cfg_key: str, required: bool = True):
        val = os.environ.get(env_key) or file_db.get(cfg_key)
        if val is None and required:
            raise RuntimeError(
                f"[DBPool] Missing DB config: set '{cfg_key}' in trends-config.json "
                f"or env var '{env_key}'."
            )
        return val

    return {
        "host":               _get("HIST_DB_HOST",         "Host"),
        "port":               int(_get("HIST_DB_PORT",     "Port")),
        "dbname":             _get("HIST_DB_NAME",         "Database"),
        "user":               _get("HIST_DB_USER",         "User"),
        "password":           _get("HIST_DB_PASSWORD",     "Password"),
        "pool_min":           int(_get("HIST_POOL_MIN",    "PoolMin",          required=False) or 2),
        "pool_max":           int(_get("HIST_POOL_MAX",    "PoolMax",          required=False) or 10),
        "stmt_timeout_ms":    int(_get("HIST_STMT_TIMEOUT_MS", "StatementTimeoutMs", required=False) or 120000),
    }


_DB_CFG: dict | None = None
_CFG_LOCK = threading.Lock()


def _get_db_cfg() -> dict:
    """Return the cached DB config dict, loading it once on first call."""
    global _DB_CFG
    if _DB_CFG is not None:
        return _DB_CFG
    with _CFG_LOCK:
        if _DB_CFG is None:
            _DB_CFG = _load_db_config()
            logger.info(
                "[DBPool] Config loaded: host=%s port=%s db=%s pool=%s-%s",
                _DB_CFG["host"], _DB_CFG["port"], _DB_CFG["dbname"],
                _DB_CFG["pool_min"], _DB_CFG["pool_max"],
            )
    return _DB_CFG

# ──────────────────────────────────────────────────────────────────────────────
# Internal state
# ──────────────────────────────────────────────────────────────────────────────
_pool: psycopg2.pool.ThreadedConnectionPool | None = None
_pool_lock = threading.Lock()


def _make_pool() -> psycopg2.pool.ThreadedConnectionPool:
    """Create a new ThreadedConnectionPool using config from trends-config.json."""
    cfg = _get_db_cfg()
    logger.info(
        "[DBPool] Creating ThreadedConnectionPool (min=%s, max=%s) → %s@%s:%s",
        cfg["pool_min"], cfg["pool_max"], cfg["dbname"], cfg["host"], cfg["port"],
    )
    pool = psycopg2.pool.ThreadedConnectionPool(
        minconn=cfg["pool_min"],
        maxconn=cfg["pool_max"],
        host=cfg["host"],
        port=cfg["port"],
        dbname=cfg["dbname"],
        user=cfg["user"],
        password=cfg["password"],
        # TCP keepalives prevent long analytical queries being killed by NAT/firewall
        keepalives=1,
        keepalives_idle=60,
        keepalives_interval=10,
        keepalives_count=5,
        connect_timeout=10,
        # application_name makes this pool visible in pg_stat_activity by name
        options=f"-c statement_timeout={cfg['stmt_timeout_ms']} -c application_name=historical_trends_pool",
    )
    logger.info(
        "[DBPool] ✅ Initialized historical_trends_pool (min=%s, max=%s) → %s@%s:%s",
        cfg["pool_min"], cfg["pool_max"], cfg["dbname"], cfg["host"], cfg["port"],
    )
    return pool


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    """Return the singleton pool, creating or re-creating if necessary."""
    global _pool
    if _pool is not None:
        return _pool
    with _pool_lock:
        if _pool is None:          # double-checked locking
            _pool = _make_pool()
    return _pool


def _probe_connection(conn) -> bool:
    """Return True if connection is alive, False if it is dead."""
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        return True
    except Exception:
        return False


@contextlib.contextmanager
def borrow_connection():
    """
    Context manager that borrows a connection from the pool and returns it
    safely on exit.  Broken connections are discarded (not returned to pool).

    Example
    -------
        with borrow_connection() as conn:
            df = pd.read_sql(sql, conn, params=[...])
    """
    global _pool
    conn = None
    broken = False

    try:
        pool = _get_pool()
        conn = pool.getconn()

        # Probe: discard and replace if stale
        if not _probe_connection(conn):
            logger.warning("[DBPool] Stale connection detected — discarding and fetching a fresh one.")
            try:
                pool.putconn(conn, close=True)
            except Exception:
                pass
            conn = pool.getconn()   # second attempt; if this fails it will raise

        yield conn

    except psycopg2.pool.PoolError as exc:
        # Pool is exhausted or closed — try to recreate once
        logger.error(f"[DBPool] PoolError: {exc} — attempting pool recreation.")
        broken = True
        with _pool_lock:
            if _pool is not None:
                try:
                    _pool.closeall()
                except Exception:
                    pass
            _pool = None
        raise RuntimeError(
            "DB connection pool exhausted or broken — retrying on next request."
        ) from exc

    except Exception:
        broken = True
        raise

    finally:
        if conn is not None and _pool is not None:
            try:
                _pool.putconn(conn, close=broken)
            except Exception:
                pass   # pool may already be gone; ignore


def close_pool():
    """Gracefully close all connections in the pool (call at app shutdown)."""
    global _pool
    with _pool_lock:
        if _pool is not None:
            logger.info("[DBPool] Closing all pool connections.")
            _pool.closeall()
            _pool = None


def pool_status() -> dict:
    """Return a status dict — useful for health-check endpoints."""
    global _pool
    if _pool is None:
        return {"status": "not_initialized"}
    # psycopg2 pool doesn't expose counters publicly but we can report basics
    cfg = _get_db_cfg()
    return {
        "status": "active",
        "min_conn": cfg["pool_min"],
        "max_conn": cfg["pool_max"],
        "host": cfg["host"],
        "database": cfg["dbname"],
    }
