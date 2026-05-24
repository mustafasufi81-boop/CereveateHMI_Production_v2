"""
Shared PostgreSQL Connection Pool
==================================
Single ThreadedConnectionPool used by ALL Flask HMI services.

Rules (MUST follow):
  - Call init_pool(db_config) ONCE at startup (done in container.py).
  - NEVER call psycopg2.connect() directly inside any service.
  - Always use:   with db_pool.get_conn() as conn:
  - Pool is thread-safe — safe for Flask + gevent workers.

Pool sizing (defaults):
  minconn =  2  — always-warm connections kept alive
  maxconn = 15  — hard cap; getconn() blocks if all 15 are in use

If all connections are busy (e.g., runaway queries), psycopg2 raises
pool.PoolError — caught in get_conn() and re-raised as RuntimeError
with a clear message so it surfaces in Flask error logs.
"""

import logging
import threading
from contextlib import contextmanager

import psycopg2
from psycopg2 import pool as pg_pool

logger = logging.getLogger(__name__)

# ── Module-level singleton ────────────────────────────────────────────────────
_pool: pg_pool.ThreadedConnectionPool | None = None
_pool_lock = threading.Lock()


def init_pool(db_config: dict, minconn: int = 2, maxconn: int = 15) -> None:
    """
    Create the shared connection pool.  Idempotent — safe to call multiple times
    (subsequent calls are ignored with a warning).

    Must be called before any service tries to use get_conn().
    Called once from container.py during app startup.
    """
    global _pool
    with _pool_lock:
        if _pool is not None:
            logger.warning("[DBPool] init_pool() called again — pool already initialised, ignoring")
            return

        try:
            _pool = pg_pool.ThreadedConnectionPool(
                minconn,
                maxconn,
                host=db_config.get('host', 'localhost'),
                port=int(db_config.get('port', 5432)),
                database=db_config.get('database', 'Automation_DB'),
                user=db_config.get('user', 'cereveate'),
                password=db_config.get('password', ''),
                connect_timeout=10,
                application_name='HMI_Flask',
            )
            logger.info(
                "[DBPool] ThreadedConnectionPool ready — min=%d max=%d db=%s@%s:%s",
                minconn, maxconn,
                db_config.get('database'),
                db_config.get('host', 'localhost'),
                db_config.get('port', 5432),
            )
        except Exception as exc:
            logger.critical("[DBPool] Failed to create connection pool: %s", exc, exc_info=True)
            raise


@contextmanager
def get_conn():
    """
    Acquire a connection from the shared pool.

    Usage (identical to the old psycopg2.connect() pattern):

        with db_pool.get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(...)
                return cur.fetchall()

    Transaction behaviour:
        - Clean exit  → commit automatically
        - Exception   → rollback automatically, connection returned to pool
        - The connection is ALWAYS returned to the pool in the finally block.
    """
    if _pool is None:
        raise RuntimeError(
            "[DBPool] Pool not initialised — init_pool() must be called before get_conn(). "
            "Check that container.py starts before any service request."
        )

    conn = None
    try:
        conn = _pool.getconn()
    except pg_pool.PoolError as exc:
        raise RuntimeError(
            f"[DBPool] Connection pool exhausted (all {_pool.maxconn} connections in use). "
            f"Original error: {exc}"
        ) from exc

    try:
        yield conn
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        if conn is not None:
            _pool.putconn(conn)


def close_pool() -> None:
    """Close all pool connections.  Call on app shutdown."""
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.closeall()
            _pool = None
            logger.info("[DBPool] Connection pool closed")


def pool_status() -> dict:
    """Return a dict with pool health info for the /health endpoint."""
    if _pool is None:
        return {"initialised": False}
    return {
        "initialised": True,
        "minconn": _pool.minconn,
        "maxconn": _pool.maxconn,
    }
