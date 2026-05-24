#!/usr/bin/env python3
"""
Database Migration Runner for Auth and RBAC System

This script runs the database migrations for the authentication and RBAC system.
It connects to the PostgreSQL database and executes the migration SQL files.

Usage:
    python run_migrations.py [--config path/to/config.json]
"""

import os
import sys
import json
import argparse
import psycopg2
from pathlib import Path
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_config(config_path='config.json'):
    """Load database configuration from config file"""
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        return config['database']
    except FileNotFoundError:
        logger.error(f"Configuration file not found: {config_path}")
        sys.exit(1)
    except KeyError:
        logger.error("Database configuration not found in config file")
        sys.exit(1)
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON in configuration file: {config_path}")
        sys.exit(1)


def get_db_connection(db_config):
    """Create database connection"""
    try:
        conn = psycopg2.connect(
            host=db_config.get('host', 'localhost'),
            port=db_config.get('port', 5432),
            database=db_config.get('database'),
            user=db_config.get('user'),
            password=db_config.get('password')
        )
        return conn
    except psycopg2.Error as e:
        logger.error(f"Database connection failed: {e}")
        sys.exit(1)


def create_migrations_table(conn):
    """Create migrations tracking table if it doesn't exist"""
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS historian_meta.migrations (
                    id SERIAL PRIMARY KEY,
                    filename VARCHAR(255) UNIQUE NOT NULL,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    success BOOLEAN DEFAULT TRUE,
                    error_message TEXT
                )
            """)
            conn.commit()
            logger.info("Migrations tracking table ready")
    except psycopg2.Error as e:
        logger.error(f"Failed to create migrations table: {e}")
        conn.rollback()
        raise


def get_applied_migrations(conn):
    """Get list of already applied migrations"""
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT filename FROM historian_meta.migrations 
                WHERE success = TRUE
                ORDER BY id
            """)
            return {row[0] for row in cur.fetchall()}
    except psycopg2.Error as e:
        logger.error(f"Failed to get applied migrations: {e}")
        return set()


def run_migration_file(conn, filepath):
    """Execute a single migration file"""
    filename = os.path.basename(filepath)
    
    try:
        # Read migration file
        with open(filepath, 'r', encoding='utf-8') as f:
            sql = f.read()
        
        logger.info(f"Applying migration: {filename}")
        
        # Execute migration
        with conn.cursor() as cur:
            cur.execute(sql)
        
        # Record successful migration
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO historian_meta.migrations (filename, success)
                VALUES (%s, TRUE)
                ON CONFLICT (filename) DO UPDATE
                SET applied_at = CURRENT_TIMESTAMP, success = TRUE, error_message = NULL
            """, (filename,))
        
        conn.commit()
        logger.info(f"✓ Successfully applied: {filename}")
        return True
        
    except psycopg2.Error as e:
        error_msg = str(e)
        logger.error(f"✗ Failed to apply {filename}: {error_msg}")
        
        # Record failed migration
        try:
            conn.rollback()
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO historian_meta.migrations (filename, success, error_message)
                    VALUES (%s, FALSE, %s)
                    ON CONFLICT (filename) DO UPDATE
                    SET applied_at = CURRENT_TIMESTAMP, success = FALSE, error_message = EXCLUDED.error_message
                """, (filename, error_msg))
            conn.commit()
        except:
            pass
        
        return False
    
    except Exception as e:
        logger.error(f"✗ Unexpected error with {filename}: {e}")
        conn.rollback()
        return False


def run_migrations(db_config, migrations_dir='migrations'):
    """Run all pending migrations"""
    # Get absolute path to migrations directory
    script_dir = Path(__file__).parent
    migrations_path = script_dir / migrations_dir
    
    if not migrations_path.exists():
        logger.error(f"Migrations directory not found: {migrations_path}")
        sys.exit(1)
    
    # Get all .sql files in migrations directory
    migration_files = sorted(migrations_path.glob('*.sql'))
    
    if not migration_files:
        logger.warning(f"No migration files found in {migrations_path}")
        return
    
    logger.info(f"Found {len(migration_files)} migration file(s)")
    
    # Connect to database
    conn = get_db_connection(db_config)
    
    try:
        # Create migrations tracking table
        create_migrations_table(conn)
        
        # Get already applied migrations
        applied = get_applied_migrations(conn)
        
        # Run pending migrations
        pending_count = 0
        success_count = 0
        
        for migration_file in migration_files:
            filename = migration_file.name
            
            if filename in applied:
                logger.info(f"⊘ Skipping already applied: {filename}")
                continue
            
            pending_count += 1
            if run_migration_file(conn, migration_file):
                success_count += 1
        
        # Summary
        logger.info("=" * 60)
        if pending_count == 0:
            logger.info("No pending migrations. Database is up to date.")
        else:
            logger.info(f"Migration Summary:")
            logger.info(f"  Total pending: {pending_count}")
            logger.info(f"  Successfully applied: {success_count}")
            logger.info(f"  Failed: {pending_count - success_count}")
        
        if success_count < pending_count:
            logger.error("Some migrations failed. Please check the errors above.")
            sys.exit(1)
        
    finally:
        conn.close()
        logger.info("Database connection closed")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Run database migrations for Auth and RBAC system'
    )
    parser.add_argument(
        '--config',
        default='config.json',
        help='Path to configuration file (default: config.json)'
    )
    parser.add_argument(
        '--migrations-dir',
        default='migrations',
        help='Path to migrations directory (default: migrations)'
    )
    
    args = parser.parse_args()
    
    # Load configuration
    db_config = load_config(args.config)
    
    # Run migrations
    logger.info("Starting database migration...")
    logger.info("=" * 60)
    run_migrations(db_config, args.migrations_dir)
    logger.info("=" * 60)
    logger.info("Migration process completed")


if __name__ == '__main__':
    main()
