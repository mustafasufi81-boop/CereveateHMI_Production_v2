#!/usr/bin/env python3
"""
Create Admin User Script

This script creates an initial admin user for the system.
It uses the AuthService to properly hash passwords and set up the user.

Usage:
    python create_admin_user.py [--config path/to/config.json]
    
The script will prompt for username and password if not provided.
"""

import os
import sys
import json
import argparse
import getpass
import logging
from pathlib import Path

# Add parent directory to path to import services
sys.path.insert(0, str(Path(__file__).parent))

from services.auth_service import AuthService
from services.rbac_service import RBACService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_config(config_path='config.json'):
    """Load configuration from config file"""
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        return config
    except FileNotFoundError:
        logger.error(f"Configuration file not found: {config_path}")
        sys.exit(1)
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON in configuration file: {config_path}")
        sys.exit(1)


def get_user_input(username=None, password=None):
    """Get username and password from user input"""
    if not username:
        username = input("Enter admin username (default: admin): ").strip()
        if not username:
            username = "admin"
    
    if not password:
        while True:
            password = getpass.getpass("Enter admin password: ")
            if len(password) < 8:
                print("Password must be at least 8 characters long. Please try again.")
                continue
            
            password_confirm = getpass.getpass("Confirm admin password: ")
            if password != password_confirm:
                print("Passwords do not match. Please try again.")
                continue
            
            break
    
    return username, password


def create_admin_user(config, username, password):
    """Create an admin user with the Admin role"""
    try:
        # Initialize services
        db_config = config['database']
        secret_key = config.get('secret_key', 'your-secret-key-here')
        
        auth_service = AuthService(db_config, secret_key)
        rbac_service = RBACService(db_config)
        
        logger.info(f"Creating admin user: {username}")
        
        # Check if user already exists
        existing_user_id = auth_service.get_user_id_by_username(username)
        if existing_user_id:
            logger.warning(f"User '{username}' already exists with ID: {existing_user_id}")
            
            # Ask if they want to reset password
            response = input("Do you want to reset the password for this user? (yes/no): ").strip().lower()
            if response in ['yes', 'y']:
                auth_service.reset_password(existing_user_id, password)
                logger.info(f"✓ Password reset for user '{username}'")
                
                # Ensure user is approved and has admin role
                admin_role = None
                roles = rbac_service.get_all_roles()
                for role in roles:
                    if role['is_admin']:
                        admin_role = role['id']
                        break
                
                if admin_role:
                    rbac_service.approve_user(existing_user_id, admin_role)
                    logger.info(f"✓ User '{username}' set to Admin role")
                
                return existing_user_id
            else:
                logger.info("Operation cancelled")
                return None
        
        # Register new user
        result = auth_service.register_user(username, password)
        user_id = result['user_id']
        backup_key = result['backup_key']
        
        logger.info(f"✓ User created with ID: {user_id}")
        logger.info(f"✓ Backup recovery key: {backup_key}")
        logger.warning("⚠ IMPORTANT: Save the backup key in a secure location!")
        
        # Get Admin role ID
        admin_role = None
        roles = rbac_service.get_all_roles()
        for role in roles:
            if role['is_admin']:
                admin_role = role['id']
                break
        
        if not admin_role:
            logger.error("Admin role not found in database. Please run migrations first.")
            return None
        
        # Approve user and assign Admin role
        rbac_service.approve_user(user_id, admin_role)
        logger.info(f"✓ User approved and assigned Admin role")
        
        # Print summary
        print("\n" + "=" * 60)
        print("Admin User Created Successfully!")
        print("=" * 60)
        print(f"Username: {username}")
        print(f"User ID: {user_id}")
        print(f"Role: Admin (Full Access)")
        print(f"Backup Key: {backup_key}")
        print("=" * 60)
        print("\n⚠ SECURITY REMINDER:")
        print("  1. Store the backup key securely")
        print("  2. Enable MFA for this account after first login")
        print("  3. Change the password if this is a temporary one")
        print("=" * 60)
        
        return user_id
        
    except Exception as e:
        logger.error(f"Failed to create admin user: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Create an admin user for the system'
    )
    parser.add_argument(
        '--config',
        default='config.json',
        help='Path to configuration file (default: config.json)'
    )
    parser.add_argument(
        '--username',
        help='Admin username (will prompt if not provided)'
    )
    parser.add_argument(
        '--password',
        help='Admin password (will prompt securely if not provided)'
    )
    
    args = parser.parse_args()
    
    # Load configuration
    config = load_config(args.config)
    
    # Get username and password
    username, password = get_user_input(args.username, args.password)
    
    # Create admin user
    logger.info("=" * 60)
    logger.info("Admin User Creation")
    logger.info("=" * 60)
    
    user_id = create_admin_user(config, username, password)
    
    if user_id:
        logger.info("=" * 60)
        logger.info("Admin user creation completed successfully")
        logger.info("=" * 60)
        sys.exit(0)
    else:
        logger.error("=" * 60)
        logger.error("Admin user creation failed")
        logger.error("=" * 60)
        sys.exit(1)


if __name__ == '__main__':
    main()
