"""
Container module for Dependency Injection.
Initializes and holds singletons for services and configuration.
"""
import json
import logging
import os
import db_pool
from services.historical_data import HistoricalDataService
from services.tag_cache import TagCacheService
from services.live_data_buffer import LiveDataBuffer
from services.auth_service import AuthService
from services.rbac_service import RBACService
from services.topic_tag_mapper import TopicTagMapper

# Enhanced RBAC Services
from services.audit_service import AuditService
from services.session_service import SessionService
from services.equipment_permission_service import EquipmentPermissionService
from services.shift_service import ShiftService
from services.approval_service import ApprovalService
from services.temporary_permission_service import TemporaryPermissionService
from services.industrial_rbac_service import IndustrialRBACService
from services.area_access_service import AreaAccessService
from services.license_service import LicenseService

logger = logging.getLogger(__name__)

class Container:
    def __init__(self):
        self.config = self._load_config()
        self.secret_key = 'hmi-secret-key-change-in-production'

        # ── Shared DB connection pool (ONE pool for ALL services) ──────────
        db_pool.init_pool(self.config['database'], minconn=2, maxconn=15)

        # Initialize Services
        self.historical_service = HistoricalDataService(self.config['database'])
        self.tag_cache = TagCacheService(self.config['database'])
        self.live_buffer = LiveDataBuffer()
        
        # SignalR listener is initialized in app.py or a dedicated manager
        # because it requires a callback that depends on socketio (which we want to keep at app level or higher)
        self.signalr_listener = None
        
        # MQTT Topic-Tag Mapper
        self.topic_tag_mapper = TopicTagMapper(self.config['database'], refresh_interval=300)
        
        # MQTT client is initialized in app.py with callback
        self.mqtt_client = None
        
        # Auth Service
        self.auth_service = AuthService(self.config['database'], self.secret_key)
        
        # RBAC Service
        self.rbac_service = RBACService(self.config['database'])
        
        # Enhanced RBAC Services
        self.audit_service = AuditService(self.config['database'])
        self.session_service = SessionService(self.config['database'])
        self.equipment_permission_service = EquipmentPermissionService(self.config['database'])
        self.shift_service = ShiftService(self.config['database'])
        self.approval_service = ApprovalService(self.config['database'])
        self.temporary_permission_service = TemporaryPermissionService(self.config['database'])
        self.industrial_rbac_service = IndustrialRBACService(self.historical_service)

        # Plant/Area access control (two-dimension model: role + area)
        self.area_access_service = AreaAccessService(self.config['database'])

        # License enforcement (ECDSA-signed key validation — §16, §27.1)
        # public_key_hex must be set in config.json 'license.public_key_hex'.
        # There is no bypass — enforcement is DB-driven.
        self.license_service = LicenseService(
            db_config=self.config['database'],
            public_key_hex=self.config.get('license', {}).get('public_key_hex'),
        )
        
    def _load_config(self):
        try:
            from _open_config import load_config
            logger.info("[CONFIG] Loading config from encrypted config.enc")
            return load_config()
        except SystemExit:
            raise
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            raise

# Create a singleton instance
container = Container()

