"""
Database Connection Pool Module
Manages PostgreSQL connections using psycopg2
"""

import psycopg2
import psycopg2.pool
import psycopg2.extras
from typing import Optional, Any, List, Tuple
from contextlib import contextmanager
import threading
from src.monitoring.logger import get_logger

logger = get_logger(__name__)


class DatabaseConnection:
    """Database connection pool manager"""
    
    def __init__(self, config: dict):
        """
        Initialize database connection pool
        
        Args:
            config: Database configuration dict
        """
        self.config = config
        self._pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None
        self._lock = threading.Lock()
        
    def initialize(self):
        """Initialize connection pool"""
        try:
            self._pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=self.config.get('pool_size', 20),
                host=self.config['host'],
                port=self.config['port'],
                database=self.config['database'],
                user=self.config['username'],
                password=self.config['password'],
                connect_timeout=self.config.get('pool_timeout', 30)
            )
            
            logger.info(f"Database connection pool initialized: {self.config['host']}:{self.config['port']}/{self.config['database']}")
            
            # Test connection
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT version();")
                    version = cur.fetchone()[0]
                    logger.info(f"PostgreSQL version: {version}")
                    
        except Exception as e:
            logger.error(f"Failed to initialize database connection pool: {e}")
            raise
    
    @contextmanager
    def get_connection(self):
        """
        Get database connection from pool
        
        Yields:
            psycopg2 connection
            
        Usage:
            with db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT ...")
        """
        if self._pool is None:
            raise RuntimeError("Database pool not initialized. Call initialize() first.")
        
        conn = None
        try:
            conn = self._pool.getconn()
            yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Database connection error: {e}")
            raise
        finally:
            if conn:
                self._pool.putconn(conn)
    
    @contextmanager
    def get_cursor(self, cursor_factory=None):
        """
        Get database cursor (convenience method)
        
        Args:
            cursor_factory: Optional cursor factory (e.g., RealDictCursor)
            
        Yields:
            Database cursor
        """
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=cursor_factory)
            try:
                yield cursor
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise
            finally:
                cursor.close()
    
    def execute_query(self, query: str, params: tuple = None, fetch: bool = True) -> Optional[List[Tuple]]:
        """
        Execute SQL query
        
        Args:
            query: SQL query string
            params: Query parameters (tuple)
            fetch: Whether to fetch results
            
        Returns:
            Query results if fetch=True, else None
        """
        with self.get_cursor() as cur:
            cur.execute(query, params)
            if fetch:
                return cur.fetchall()
            return None
    
    def execute_many(self, query: str, params_list: List[tuple]):
        """
        Execute batch insert/update
        
        Args:
            query: SQL query string
            params_list: List of parameter tuples
        """
        with self.get_cursor() as cur:
            cur.executemany(query, params_list)
    
    def test_connection(self) -> bool:
        """
        Test database connectivity
        
        Returns:
            True if connected, False otherwise
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    result = cur.fetchone()
                    return result[0] == 1
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            return False
    
    def close(self):
        """Close all connections in pool"""
        if self._pool:
            self._pool.closeall()
            logger.info("Database connection pool closed")
    
    def __del__(self):
        """Destructor to ensure cleanup"""
        self.close()


# Singleton instance
_db_instance: Optional[DatabaseConnection] = None
_db_lock = threading.Lock()


def get_database(config: dict = None) -> DatabaseConnection:
    """
    Get singleton database instance
    
    Args:
        config: Database configuration (only used on first call)
        
    Returns:
        DatabaseConnection instance
    """
    global _db_instance
    
    if _db_instance is None:
        with _db_lock:
            if _db_instance is None:
                if config is None:
                    raise ValueError("Database config required for first initialization")
                _db_instance = DatabaseConnection(config)
                _db_instance.initialize()
    
    return _db_instance
