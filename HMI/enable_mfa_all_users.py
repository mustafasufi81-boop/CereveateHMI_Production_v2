"""
Enable MFA for All Users
Executes the migration to enable Multi-Factor Authentication for all users
"""

import psycopg2
import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def load_config():
    """Load database configuration"""
    config_path = Path(__file__).parent / 'config.json'
    with open(config_path, 'r') as f:
        return json.load(f)

def enable_mfa_for_all_users():
    """Enable MFA for all users in the system"""
    try:
        config = load_config()
        db_config = config['database']
        
        # Connect to database
        conn = psycopg2.connect(
            host=db_config['host'],
            port=db_config['port'],
            database=db_config['database'],
            user=db_config['user'],
            password=db_config['password']
        )
        
        with conn.cursor() as cur:
            # Get count before update
            cur.execute("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE mfa_enabled = TRUE) as enabled,
                    COUNT(*) FILTER (WHERE mfa_enabled = FALSE) as disabled
                FROM historian_meta.users
            """)
            before = cur.fetchone()
            logger.info(f"Before: Total={before[0]}, MFA Enabled={before[1]}, MFA Disabled={before[2]}")
            
            # Enable MFA for all users
            cur.execute("""
                UPDATE historian_meta.users
                SET mfa_enabled = TRUE
                WHERE mfa_enabled = FALSE
            """)
            updated_count = cur.rowcount
            conn.commit()
            
            logger.info(f"✓ Updated {updated_count} users to enable MFA")
            
            # Get count after update
            cur.execute("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE mfa_enabled = TRUE) as enabled,
                    COUNT(*) FILTER (WHERE mfa_enabled = FALSE) as disabled
                FROM historian_meta.users
            """)
            after = cur.fetchone()
            logger.info(f"After: Total={after[0]}, MFA Enabled={after[1]}, MFA Disabled={after[2]}")
            
            # Show all users with their MFA status
            cur.execute("""
                SELECT id, username, mfa_enabled, status, created_at
                FROM historian_meta.users
                ORDER BY id
            """)
            users = cur.fetchall()
            
            logger.info("\n" + "="*70)
            logger.info("USER MFA STATUS")
            logger.info("="*70)
            logger.info(f"{'ID':<5} {'Username':<20} {'MFA':<10} {'Status':<15} {'Created'}")
            logger.info("-"*70)
            for user in users:
                user_id, username, mfa_enabled, status, created_at = user
                mfa_status = "✓ ENABLED" if mfa_enabled else "✗ DISABLED"
                logger.info(f"{user_id:<5} {username:<20} {mfa_status:<10} {status:<15} {created_at}")
            logger.info("="*70)
            
            logger.info("\n✓ MFA has been successfully enabled for all users!")
            logger.info("\nImportant Notes:")
            logger.info("1. All users will now be required to use MFA on their next login")
            logger.info("2. Users can verify using their 6-digit MFA token OR security questions")
            logger.info("3. Default MFA token for users without custom token: 123456")
            
        conn.close()
        return True
        
    except FileNotFoundError:
        logger.error("❌ config.json not found. Please ensure it exists in the HMI directory")
        return False
    except psycopg2.Error as e:
        logger.error(f"❌ Database error: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        return False

if __name__ == '__main__':
    logger.info("Starting MFA enablement for all users...")
    success = enable_mfa_for_all_users()
    if success:
        logger.info("\n✓ Process completed successfully!")
    else:
        logger.error("\n✗ Process failed. Please check the errors above.")
