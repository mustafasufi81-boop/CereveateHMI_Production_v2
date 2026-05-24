"""
Alarm Service for HMI Dashboard
Monitors tag values and generates alarms for motor health, trips, and other critical conditions
"""

import logging
import json
from datetime import datetime, timedelta
from contextlib import contextmanager
from typing import Dict, List, Optional, Tuple
import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

class AlarmService:
    def __init__(self, connection_pool):
        self.connection_pool = connection_pool
        self.active_alarms = {}  # Cache of active alarms
        self.alarm_config = self._load_alarm_config()
        logger.info("✅ Alarm service initialized")

    @contextmanager
    def _get_connection(self):
        """Get database connection from pool with error handling"""
        conn = None
        try:
            conn = self.connection_pool.getconn()
            yield conn
        except Exception as e:
            logger.error(f"❌ Database connection error: {e}")
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                self.connection_pool.putconn(conn)

    def _load_alarm_config(self) -> Dict:
        """Load alarm configuration for motor health monitoring"""
        return {
            # Motor Health Bit Alarms (Digital)
            'motor_health_tags': [
                {'pattern': '*Motor*Health*', 'alarm_on_value': 0, 'message': 'Motor Health Bit Low'},
                {'pattern': '*Pump*Health*', 'alarm_on_value': 0, 'message': 'Pump Health Bit Low'},
                {'pattern': '*Drive*Health*', 'alarm_on_value': 0, 'message': 'Drive Health Bit Low'},
            ],
            
            # Trip Alarms (Digital)
            'trip_tags': [
                {'pattern': '*Trip*', 'alarm_on_value': 1, 'message': 'Equipment Trip Active'},
                {'pattern': '*Emergency*', 'alarm_on_value': 1, 'message': 'Emergency Stop Active'},
                {'pattern': '*Fault*', 'alarm_on_value': 1, 'message': 'Equipment Fault Active'},
            ],
            
            # Analog Limits (Temperature, Pressure, etc.)
            'analog_limits': [
                {'pattern': '*Temp*', 'high_limit': 85.0, 'low_limit': 5.0, 'message': 'Temperature Out of Range'},
                {'pattern': '*Pressure*', 'high_limit': 150.0, 'low_limit': 10.0, 'message': 'Pressure Out of Range'},
                {'pattern': '*Current*', 'high_limit': 50.0, 'low_limit': 0.5, 'message': 'Motor Current Out of Range'},
                {'pattern': '*RPM*', 'high_limit': 3600.0, 'low_limit': 100.0, 'message': 'Motor Speed Out of Range'},
            ]
        }

    def get_active_alarms(self) -> List[Dict]:
        """Get all currently active alarms"""
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    # Check for active alarms in last 5 minutes
                    cursor.execute("""
                        SELECT 
                            tag_id,
                            alarm_type,
                            alarm_message,
                            alarm_priority,
                            alarm_timestamp,
                            current_value,
                            acknowledged,
                            acknowledged_by,
                            acknowledged_at
                        FROM alarm_events 
                        WHERE alarm_state = 'ACTIVE'
                        AND alarm_timestamp >= %s
                        ORDER BY alarm_priority DESC, alarm_timestamp DESC
                    """, (datetime.now() - timedelta(hours=24),))
                    
                    alarms = cursor.fetchall()
                    return [dict(alarm) for alarm in alarms]
                    
        except Exception as e:
            logger.error(f"❌ Failed to get active alarms: {e}")
            return []

    def check_tag_alarms(self, tag_id: str, current_value: float, quality: str = 'GOOD') -> List[Dict]:
        """Check if a tag value should generate alarms"""
        new_alarms = []
        
        if quality != 'GOOD':
            return new_alarms

        try:
            # Check motor health bit alarms
            for health_config in self.alarm_config['motor_health_tags']:
                if self._match_pattern(tag_id, health_config['pattern']):
                    if current_value == health_config['alarm_on_value']:
                        alarm = self._create_alarm(
                            tag_id, 'MOTOR_HEALTH', health_config['message'], 
                            current_value, priority=4
                        )
                        new_alarms.append(alarm)

            # Check trip alarms
            for trip_config in self.alarm_config['trip_tags']:
                if self._match_pattern(tag_id, trip_config['pattern']):
                    if current_value == trip_config['alarm_on_value']:
                        alarm = self._create_alarm(
                            tag_id, 'TRIP', trip_config['message'], 
                            current_value, priority=5  # Highest priority
                        )
                        new_alarms.append(alarm)

            # Check analog limits
            for limit_config in self.alarm_config['analog_limits']:
                if self._match_pattern(tag_id, limit_config['pattern']):
                    if current_value > limit_config['high_limit']:
                        alarm = self._create_alarm(
                            tag_id, 'HIGH_LIMIT', f"{limit_config['message']} (High)", 
                            current_value, priority=3
                        )
                        new_alarms.append(alarm)
                    elif current_value < limit_config['low_limit']:
                        alarm = self._create_alarm(
                            tag_id, 'LOW_LIMIT', f"{limit_config['message']} (Low)", 
                            current_value, priority=3
                        )
                        new_alarms.append(alarm)

            # Store new alarms in database
            if new_alarms:
                self._store_alarms(new_alarms)
                
            return new_alarms
            
        except Exception as e:
            logger.error(f"❌ Error checking alarms for {tag_id}: {e}")
            return []

    def _match_pattern(self, tag_id: str, pattern: str) -> bool:
        """Simple pattern matching (supports wildcards)"""
        import fnmatch
        return fnmatch.fnmatch(tag_id.upper(), pattern.upper())

    def _create_alarm(self, tag_id: str, alarm_type: str, message: str, 
                     current_value: float, priority: int = 3) -> Dict:
        """Create an alarm dictionary"""
        return {
            'tag_id': tag_id,
            'alarm_type': alarm_type,
            'alarm_message': message,
            'alarm_priority': priority,
            'alarm_timestamp': datetime.now(),
            'current_value': current_value,
            'acknowledged': False,
            'acknowledged_by': None,
            'acknowledged_at': None,
            'alarm_state': 'ACTIVE'
        }

    def _store_alarms(self, alarms: List[Dict]):
        """Store alarms in database"""
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    # Create alarm_events table if it doesn't exist
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS alarm_events (
                            id SERIAL PRIMARY KEY,
                            tag_id VARCHAR(500) NOT NULL,
                            alarm_type VARCHAR(50) NOT NULL,
                            alarm_message TEXT NOT NULL,
                            alarm_priority INTEGER DEFAULT 3,
                            alarm_timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                            current_value FLOAT,
                            acknowledged BOOLEAN DEFAULT FALSE,
                            acknowledged_by VARCHAR(100),
                            acknowledged_at TIMESTAMP WITH TIME ZONE,
                            alarm_state VARCHAR(20) DEFAULT 'ACTIVE'
                        )
                    """)
                    
                    # Create index for performance
                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS idx_alarm_events_active 
                        ON alarm_events(alarm_state, alarm_timestamp) 
                        WHERE alarm_state = 'ACTIVE'
                    """)
                    
                    # Insert alarms
                    for alarm in alarms:
                        cursor.execute("""
                            INSERT INTO alarm_events 
                            (tag_id, alarm_type, alarm_message, alarm_priority, 
                             alarm_timestamp, current_value, alarm_state)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """, (
                            alarm['tag_id'], alarm['alarm_type'], alarm['alarm_message'],
                            alarm['alarm_priority'], alarm['alarm_timestamp'], 
                            alarm['current_value'], alarm['alarm_state']
                        ))
                    
                    conn.commit()
                    logger.info(f"✅ Stored {len(alarms)} new alarms")
                    
        except Exception as e:
            logger.error(f"❌ Failed to store alarms: {e}")

    def acknowledge_alarm(self, alarm_id: int, acknowledged_by: str = 'operator') -> bool:
        """Acknowledge an alarm"""
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        UPDATE alarm_events 
                        SET acknowledged = TRUE, 
                            acknowledged_by = %s, 
                            acknowledged_at = NOW()
                        WHERE id = %s AND acknowledged = FALSE
                    """, (acknowledged_by, alarm_id))
                    
                    conn.commit()
                    if cursor.rowcount > 0:
                        logger.info(f"✅ Acknowledged alarm {alarm_id} by {acknowledged_by}")
                        return True
                    return False
                    
        except Exception as e:
            logger.error(f"❌ Failed to acknowledge alarm {alarm_id}: {e}")
            return False

    def clear_alarm(self, alarm_id: int) -> bool:
        """Clear/resolve an alarm"""
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        UPDATE alarm_events 
                        SET alarm_state = 'CLEARED'
                        WHERE id = %s
                    """, (alarm_id,))
                    
                    conn.commit()
                    if cursor.rowcount > 0:
                        logger.info(f"✅ Cleared alarm {alarm_id}")
                        return True
                    return False
                    
        except Exception as e:
            logger.error(f"❌ Failed to clear alarm {alarm_id}: {e}")
            return False

    def get_alarm_summary(self) -> Dict:
        """Get alarm counts by priority"""
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("""
                        SELECT 
                            alarm_priority,
                            COUNT(*) as count,
                            COUNT(CASE WHEN acknowledged = FALSE THEN 1 END) as unacknowledged
                        FROM alarm_events 
                        WHERE alarm_state = 'ACTIVE'
                        GROUP BY alarm_priority
                        ORDER BY alarm_priority DESC
                    """)
                    
                    results = cursor.fetchall()
                    summary = {
                        'total_active': sum(row['count'] for row in results),
                        'total_unacknowledged': sum(row['unacknowledged'] for row in results),
                        'by_priority': {row['alarm_priority']: dict(row) for row in results}
                    }
                    return summary
                    
        except Exception as e:
            logger.error(f"❌ Failed to get alarm summary: {e}")
            return {'total_active': 0, 'total_unacknowledged': 0, 'by_priority': {}}