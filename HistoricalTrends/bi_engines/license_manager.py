"""
License and User Session Manager
Controls concurrent user access with installation-time license
"""

import json
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class LicenseManager:
    """
    Manages user licenses and concurrent access control
    
    Features:
    - Max concurrent users (set during installation)
    - Single session per user (logout from other locations)
    - Installation-time license key (unchangeable)
    - Idle timeout (30 minutes)
    - Active session protection (don't clear if in use)
    """
    
    def __init__(self, license_file: str = None):
        """
        Initialize license manager
        
        Args:
            license_file: Path to license configuration file
        """
        if license_file is None:
            license_file = os.path.join(
                os.path.dirname(__file__),
                'config',
                'license.json'
            )
        
        self.license_file = license_file
        self.license_data = self._load_or_create_license()
        
        # Active sessions: {user_id: session_info}
        self.active_sessions = {}
        
        logger.info(f"License Manager initialized: Max {self.license_data['max_concurrent_users']} users")
    
    def _load_or_create_license(self) -> Dict:
        """Load existing license or create new one"""
        if os.path.exists(self.license_file):
            try:
                with open(self.license_file, 'r') as f:
                    license_data = json.load(f)
                
                # Validate license
                if self._validate_license(license_data):
                    logger.info("✓ Valid license loaded")
                    return license_data
                else:
                    logger.error("❌ Invalid license file")
                    raise ValueError("License file corrupted")
            
            except Exception as e:
                logger.error(f"Error loading license: {e}")
                raise
        else:
            # First installation - create license
            logger.warning("⚠️ No license found - creating default license")
            return self._create_default_license()
    
    def _create_default_license(self) -> Dict:
        """Create default license for first installation"""
        license_data = {
            'max_concurrent_users': 5,  # Default: 5 users
            'installation_date': datetime.now().isoformat(),
            'license_key': self._generate_license_key(),
            'master_api_key': self._generate_master_api_key(),
            'is_locked': False,  # Will be locked after installation
            'idle_timeout_minutes': 30
        }
        
        logger.info(f"📄 Default license created: {license_data['max_concurrent_users']} users")
        logger.info(f"🔑 Master API Key: {license_data['master_api_key']}")
        logger.warning("⚠️ SAVE THIS API KEY - Required to modify license!")
        
        return license_data
    
    def activate_license(
        self,
        max_users: int,
        installation_key: str,
        master_api_key: Optional[str] = None
    ) -> Dict:
        """
        Activate license during installation
        
        Args:
            max_users: Maximum concurrent users (1-100)
            installation_key: Installation verification key
            master_api_key: Optional custom master API key
            
        Returns:
            License activation result
        """
        if self.license_data.get('is_locked', False):
            raise ValueError("License already activated and locked")
        
        # Validate max users
        if not (1 <= max_users <= 100):
            raise ValueError("Max users must be between 1 and 100")
        
        # Generate or use provided master API key
        if master_api_key is None:
            master_api_key = self._generate_master_api_key()
        
        # Update license
        self.license_data.update({
            'max_concurrent_users': max_users,
            'installation_date': datetime.now().isoformat(),
            'license_key': self._generate_license_key(),
            'master_api_key': master_api_key,
            'is_locked': True,  # Lock after activation
            'installation_key': hashlib.sha256(installation_key.encode()).hexdigest()
        })
        
        # Save to file
        self._save_license()
        
        logger.info(f"✅ License activated: {max_users} concurrent users")
        logger.warning(f"🔒 License LOCKED - Master API Key required for changes")
        
        return {
            'status': 'activated',
            'max_concurrent_users': max_users,
            'master_api_key': master_api_key,
            'license_key': self.license_data['license_key']
        }
    
    def modify_license(
        self,
        master_api_key: str,
        max_users: Optional[int] = None
    ) -> Dict:
        """
        Modify license (requires master API key)
        
        Args:
            master_api_key: Master API key from installation
            max_users: New max concurrent users
            
        Returns:
            Modification result
        """
        # Verify master API key
        if master_api_key != self.license_data.get('master_api_key'):
            logger.error("❌ Invalid master API key")
            raise ValueError("Invalid master API key")
        
        changes = {}
        
        if max_users is not None:
            if not (1 <= max_users <= 100):
                raise ValueError("Max users must be between 1 and 100")
            
            old_max = self.license_data['max_concurrent_users']
            self.license_data['max_concurrent_users'] = max_users
            changes['max_users'] = {'old': old_max, 'new': max_users}
        
        # Save changes
        self._save_license()
        
        logger.info(f"✅ License modified: {changes}")
        
        return {
            'status': 'modified',
            'changes': changes,
            'current_max_users': self.license_data['max_concurrent_users']
        }
    
    def check_user_login(self, user_id: str, session_token: str = None) -> Tuple[bool, str, Optional[str]]:
        """
        Check if user can login
        
        Args:
            user_id: User identifier
            session_token: Existing session token (for same-user multi-login check)
            
        Returns:
            Tuple of (can_login, reason, old_session_token_to_logout)
        """
        max_users = self.license_data['max_concurrent_users']
        
        # Clean up idle sessions first
        self._cleanup_idle_sessions()
        
        # Check if same user is already logged in
        if user_id in self.active_sessions:
            existing_session = self.active_sessions[user_id]
            
            # Same user from different location - logout old session
            if session_token != existing_session['session_token']:
                old_token = existing_session['session_token']
                logger.info(f"🔄 User {user_id} logging in from new location - logout old session")
                return (True, "logout_other_session", old_token)
            else:
                # Same session - just update activity
                return (True, "existing_session", None)
        
        # Check concurrent user limit
        active_count = len(self.active_sessions)
        
        if active_count >= max_users:
            logger.warning(f"❌ Max users ({max_users}) reached - cannot login user {user_id}")
            return (False, f"maximum_users_reached_{max_users}", None)
        
        # Can login
        return (True, "new_session", None)
    
    def create_session(self, user_id: str, metadata: Dict = None) -> str:
        """
        Create new user session
        
        Args:
            user_id: User identifier
            metadata: Optional session metadata
            
        Returns:
            Session token
        """
        # Generate session token
        session_token = secrets.token_urlsafe(32)
        
        # Create session
        self.active_sessions[user_id] = {
            'user_id': user_id,
            'session_token': session_token,
            'created_at': datetime.now(),
            'last_activity': datetime.now(),
            'metadata': metadata or {}
        }
        
        logger.info(f"✅ Session created for user: {user_id}")
        logger.info(f"📊 Active users: {len(self.active_sessions)}/{self.license_data['max_concurrent_users']}")
        
        return session_token
    
    def update_session_activity(self, user_id: str):
        """Update session last activity timestamp"""
        if user_id in self.active_sessions:
            self.active_sessions[user_id]['last_activity'] = datetime.now()
    
    def logout_session(self, user_id: str):
        """Logout user session"""
        if user_id in self.active_sessions:
            del self.active_sessions[user_id]
            logger.info(f"👋 User logged out: {user_id}")
            logger.info(f"📊 Active users: {len(self.active_sessions)}/{self.license_data['max_concurrent_users']}")
    
    def _cleanup_idle_sessions(self):
        """
        Remove sessions idle for more than configured timeout
        ONLY removes if idle - not if actively used
        """
        idle_timeout = timedelta(minutes=self.license_data['idle_timeout_minutes'])
        now = datetime.now()
        
        idle_users = []
        
        for user_id, session in self.active_sessions.items():
            time_since_activity = now - session['last_activity']
            
            if time_since_activity > idle_timeout:
                idle_users.append(user_id)
        
        # Remove idle sessions
        for user_id in idle_users:
            logger.info(f"⏱️ Removing idle session: {user_id} (idle {idle_timeout.total_seconds()/60:.1f} min)")
            del self.active_sessions[user_id]
        
        if idle_users:
            logger.info(f"🧹 Cleaned {len(idle_users)} idle sessions")
    
    def get_active_sessions(self) -> Dict:
        """Get all active sessions info"""
        self._cleanup_idle_sessions()
        
        sessions_info = []
        for user_id, session in self.active_sessions.items():
            sessions_info.append({
                'user_id': user_id,
                'created_at': session['created_at'].isoformat(),
                'last_activity': session['last_activity'].isoformat(),
                'idle_minutes': (datetime.now() - session['last_activity']).total_seconds() / 60
            })
        
        return {
            'active_count': len(self.active_sessions),
            'max_users': self.license_data['max_concurrent_users'],
            'available_slots': self.license_data['max_concurrent_users'] - len(self.active_sessions),
            'sessions': sessions_info
        }
    
    def get_license_info(self, include_keys: bool = False) -> Dict:
        """
        Get license information
        
        Args:
            include_keys: Include sensitive keys (requires authentication)
            
        Returns:
            License information
        """
        info = {
            'max_concurrent_users': self.license_data['max_concurrent_users'],
            'installation_date': self.license_data.get('installation_date'),
            'is_locked': self.license_data.get('is_locked', False),
            'idle_timeout_minutes': self.license_data['idle_timeout_minutes'],
            'active_users': len(self.active_sessions),
            'available_slots': self.license_data['max_concurrent_users'] - len(self.active_sessions)
        }
        
        if include_keys:
            info['license_key'] = self.license_data.get('license_key')
            info['master_api_key'] = self.license_data.get('master_api_key')
        
        return info
    
    def _generate_license_key(self) -> str:
        """Generate unique license key"""
        timestamp = datetime.now().isoformat()
        random_data = secrets.token_hex(16)
        combined = f"{timestamp}:{random_data}"
        
        license_hash = hashlib.sha256(combined.encode()).hexdigest()
        
        # Format as XXXX-XXXX-XXXX-XXXX
        formatted = '-'.join([
            license_hash[0:4].upper(),
            license_hash[4:8].upper(),
            license_hash[8:12].upper(),
            license_hash[12:16].upper()
        ])
        
        return formatted
    
    def _generate_master_api_key(self) -> str:
        """Generate master API key for license modifications"""
        return f"MASTER_{secrets.token_urlsafe(32)}"
    
    def _validate_license(self, license_data: Dict) -> bool:
        """Validate license data structure"""
        required_fields = ['max_concurrent_users', 'license_key', 'idle_timeout_minutes']
        
        for field in required_fields:
            if field not in license_data:
                return False
        
        return True
    
    def _save_license(self):
        """Save license to file"""
        # Ensure directory exists
        os.makedirs(os.path.dirname(self.license_file), exist_ok=True)
        
        with open(self.license_file, 'w') as f:
            json.dump(self.license_data, f, indent=2)
        
        logger.info(f"💾 License saved to {self.license_file}")


# Global license manager instance
_global_license_manager = None


def get_license_manager(license_file: str = None) -> LicenseManager:
    """
    Get global license manager instance
    
    Args:
        license_file: Optional path to license file
        
    Returns:
        LicenseManager instance
    """
    global _global_license_manager
    
    if _global_license_manager is None:
        _global_license_manager = LicenseManager(license_file)
    
    return _global_license_manager
