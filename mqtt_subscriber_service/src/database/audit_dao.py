"""
Audit Data Access Object (DAO)
Handles all audit table operations
"""

import json
from datetime import datetime
from typing import Optional, Dict, Any
from src.monitoring.logger import get_logger

logger = get_logger(__name__)


class AuditDAO:
    """Data Access Object for audit tables"""
    
    def __init__(self, db_connection):
        """
        Initialize Audit DAO
        
        Args:
            db_connection: DatabaseConnection instance
        """
        self.db = db_connection
    
    def insert_audit_main(self, message_id: str, topic: str, payload_size: int, status: str = 'processing') -> Optional[int]:
        """
        Insert record into mqtt_audit_main
        
        Args:
            message_id: Unique message identifier
            topic: MQTT topic name
            payload_size: Size of message payload in bytes
            status: Initial status (default: 'processing')
            
        Returns:
            audit_id if successful, None otherwise
        """
        query = """
            INSERT INTO historian_raw.mqtt_audit_main 
            (message_id, topic_name, payload_size, first_received_time, status)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING audit_id
        """
        
        try:
            with self.db.get_cursor() as cur:
                cur.execute(query, (
                    message_id,
                    topic,
                    payload_size,
                    datetime.utcnow(),
                    status
                ))
                audit_id = cur.fetchone()[0]
                logger.debug(f"Inserted audit_main: audit_id={audit_id}, message_id={message_id}")
                return audit_id
                
        except Exception as e:
            logger.error(f"Failed to insert audit_main: {e}")
            return None
    
    def insert_audit_history(self, audit_id: int, step: str, status: str, details: str = None):
        """
        Insert record into mqtt_audit_history
        
        Args:
            audit_id: Reference to audit_main record
            step: Processing step name (not stored, used for error_message)
            status: 'processing', 'completed', or 'failed'
            details: Optional details as text or JSON string (stored in error_message)
        
        Note: Table schema has audit_id, topic_name, message_id, status, error_message
        """
        # Get topic_name and message_id from audit_main
        query_main = """
            SELECT topic_name, message_id 
            FROM historian_raw.mqtt_audit_main 
            WHERE audit_id = %s
        """
        
        query_insert = """
            INSERT INTO historian_raw.mqtt_audit_history
            (audit_id, topic_name, message_id, status, error_message, processed_time)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        
        try:
            with self.db.get_cursor() as cur:
                # Get topic and message info
                cur.execute(query_main, (audit_id,))
                result = cur.fetchone()
                
                if not result:
                    logger.warning(f"No audit_main record found for audit_id={audit_id}")
                    return
                
                topic_name, message_id = result
                
                # Format error message with step info
                error_msg = f"{step}: {details}" if details else step if status == 'failed' else None
                
                # Insert history record
                cur.execute(query_insert, (
                    audit_id,
                    topic_name,
                    message_id,
                    status,
                    error_msg,
                    datetime.utcnow()
                ))
                logger.debug(f"Inserted audit_history: audit_id={audit_id}, step={step}, status={status}")
                
        except Exception as e:
            logger.error(f"Failed to insert audit_history: {e}")
            raise
    
    def update_audit_main_status(self, audit_id: int, status: str, 
                                 error_message: str = None, 
                                 records_inserted: int = None):
        """
        Update audit_main record with final status
        
        Args:
            audit_id: Audit record ID
            status: Final status ('completed', 'failed')
            error_message: Optional error message
            records_inserted: Number of records inserted (timeseries + events)
        """
        query = """
            UPDATE historian_raw.mqtt_audit_main
            SET status = %s,
                processed_time = %s,
                error_message = %s,
                records_inserted = %s
            WHERE audit_id = %s
        """
        
        try:
            with self.db.get_cursor() as cur:
                cur.execute(query, (
                    status,
                    datetime.utcnow(),
                    error_message,
                    records_inserted,
                    audit_id
                ))
                logger.debug(f"Updated audit_main: audit_id={audit_id}, status={status}")
                
        except Exception as e:
            logger.error(f"Failed to update audit_main: {e}")
            raise
    
    def get_audit_by_message_id(self, message_id: str) -> Optional[Dict[str, Any]]:
        """
        Get audit record by message_id
        
        Args:
            message_id: Unique message identifier
            
        Returns:
            Audit record dict or None
        """
        query = """
            SELECT audit_id, topic_name, message_id, status, first_received_time
            FROM historian_raw.mqtt_audit_main
            WHERE message_id = %s
        """
        
        try:
            with self.db.get_cursor() as cur:
                cur.execute(query, (message_id,))
                result = cur.fetchone()
                
                if result:
                    return {
                        'audit_id': result[0],
                        'topic_name': result[1],
                        'message_id': result[2],
                        'status': result[3],
                        'first_received_time': result[4]
                    }
                return None
                
        except Exception as e:
            logger.error(f"Failed to get audit by message_id: {e}")
            return None
    
    def check_duplicate_message_id(self, message_id: str) -> bool:
        """
        Check if message_id already exists
        
        Args:
            message_id: Message identifier
            
        Returns:
            True if exists, False otherwise
        """
        query = """
            SELECT EXISTS(
                SELECT 1 FROM historian_raw.mqtt_audit_main 
                WHERE message_id = %s
            )
        """
        
        try:
            with self.db.get_cursor() as cur:
                cur.execute(query, (message_id,))
                return cur.fetchone()[0]
                
        except Exception as e:
            logger.error(f"Failed to check duplicate message_id: {e}")
            return False
