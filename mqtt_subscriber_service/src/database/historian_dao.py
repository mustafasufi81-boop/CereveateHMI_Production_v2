"""
Historian Data Access Object (DAO)
Handles operations for historian_timeseries and historian_events tables
"""

import json
from datetime import datetime
from typing import List, Dict, Any
from src.monitoring.logger import get_logger
from src.database.alarm_audit_dao import AlarmAuditDAO

logger = get_logger(__name__)


class HistorianDAO:
    """Data Access Object for historian tables"""
    
    def __init__(self, db_connection):
        """
        Initialize Historian DAO
        
        Args:
            db_connection: DatabaseConnection instance
        """
        self.db = db_connection
        try:
            self.audit_dao = AlarmAuditDAO(db_connection)
            logger.info("✅ AlarmAuditDAO initialized in HistorianDAO")
        except Exception as e:
            logger.error(f"Failed to initialize AlarmAuditDAO: {e}")
            self.audit_dao = None
    
    def insert_timeseries_batch(self, tags: List[Dict[str, Any]]) -> int:
        """
        Batch insert into historian_timeseries
        
        Args:
            tags: List of tag dictionaries with keys:
                - time: timestamp
                - tag_id: tag identifier
                - value_num: numeric value (or None)
                - value_text: text value (or None)
                - value_bool: boolean value (or None)
                - quality: quality code (G, B, U)
                - sample_source: source identifier
                - mapping_version: version number
                
        Returns:
            Number of records inserted
        """
        if not tags:
            return 0
        
        query = """
            INSERT INTO historian_raw.historian_timeseries
            (time, tag_id, value_num, value_text, value_bool, quality, sample_source, mapping_version, opc_timestamp)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (time, tag_id) DO UPDATE SET
                value_num = EXCLUDED.value_num,
                value_text = EXCLUDED.value_text,
                value_bool = EXCLUDED.value_bool,
                quality = EXCLUDED.quality,
                opc_timestamp = EXCLUDED.opc_timestamp
        """
        
        try:
            params_list = []
            for tag in tags:
                opc_ts = self._parse_timestamp(tag.get('opc_timestamp')) if tag.get('opc_timestamp') else self._parse_timestamp(tag.get('time'))
                safe_bool = self._coerce_bool(tag.get('value_bool'))
                params_list.append((
                    self._parse_timestamp(tag.get('time')),
                    tag.get('tag_id'),
                    tag.get('value_num'),
                    tag.get('value_text'),
                    safe_bool,
                    tag.get('quality', 'G'),
                    tag.get('sample_source', 'MQTT'),
                    tag.get('mapping_version', 1),
                    opc_ts
                ))
            
            self.db.execute_many(query, params_list)
            
            logger.debug(f"Inserted {len(params_list)} records into historian_timeseries")
            return len(params_list)
            
        except Exception as e:
            logger.error(f"Failed to insert timeseries batch: {e}")
            raise

    @staticmethod
    def _coerce_bool(raw_value):
        """Normalize bool-like payload values to strict bool/None for PostgreSQL boolean columns."""
        if raw_value is None:
            return None

        if isinstance(raw_value, bool):
            return raw_value

        if isinstance(raw_value, (int, float)):
            if raw_value in (0, 0.0):
                return False
            if raw_value in (1, 1.0):
                return True
            return None

        if isinstance(raw_value, str):
            val = raw_value.strip().lower()
            if val in ('true', 't', '1', 'yes', 'y', 'on'):
                return True
            if val in ('false', 'f', '0', 'no', 'n', 'off'):
                return False
            return None

        return None
    
    def insert_events_batch(self, events: List[Dict[str, Any]]) -> int:
        """
        REMOVED: historian_raw.historian_events writes are owned exclusively by the C#
        AlarmEvaluationService (AlarmEvaluationService.cs). This method must not be
        called from HMI or MQTT subscriber code. It is retained as a no-op stub so that
        any accidental caller receives 0 instead of raising AttributeError.

        Alarm DB ownership rule:
          - C# raises ACTIVE alarm rows and marks RTN.
          - HMI operator actions (ACK, CLEAR) UPDATE existing rows only — never INSERT.
        """
        return 0  # No-op — C# owns historian_raw.historian_events

    def _insert_events_batch_DISABLED(self, events: List[Dict[str, Any]]) -> int:
        """Original implementation preserved for reference. NOT called from anywhere."""
        if not events:
            return 0
        
        # For alarms: Check if ACTIVE alarm exists, if yes UPDATE, if no INSERT
        # For non-alarm events: Just INSERT
        insert_query = """
            INSERT INTO historian_raw.historian_events
            (time, tag_id, event_type, severity, message, metadata, alarm_state, alarm_priority, 
             alarm_actual_value, alarm_setpoint, acknowledged_by, acknowledged_at, 
             cleared_at, cleared_by, clear_reason, clear_notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        update_query = """
            UPDATE historian_raw.historian_events
            SET time = %s,
                alarm_actual_value = %s,
                message = %s,
                metadata = %s,
                acknowledged_by = %s,
                acknowledged_at = %s,
                cleared_at = %s,
                cleared_by = %s,
                clear_reason = %s,
                clear_notes = %s
            WHERE tag_id = %s 
              AND event_type = %s 
              AND alarm_state = 'ACTIVE'
        """
        
        check_query = """
            SELECT event_id FROM historian_raw.historian_events
            WHERE tag_id = %s 
              AND event_type = %s 
              AND alarm_state = 'ACTIVE'
            LIMIT 1
        """
        
        try:
            insert_params = []
            update_params = []
            newly_inserted_alarms = []  # Track NEW alarms for audit trail
            records_affected = 0
            
            for event in events:
                # Determine if this is an alarm event (starts with ALARM_)
                event_type = event.get('event_type', '')
                tag_id = event.get('tag_id')
                is_alarm = event_type.startswith('ALARM_')
                
                # Set alarm_state to ACTIVE for alarm events, NULL for regular events
                alarm_state = 'ACTIVE' if is_alarm else None
                
                # Extract alarm-specific fields from metadata if available
                metadata = event.get('metadata', {})
                
                # Map alarm priority from severity (1=CRITICAL=5, 2=WARNING=2, etc.)
                severity = event.get('severity', 3)
                alarm_priority = None
                if is_alarm:
                    if severity == 1:  # CRITICAL
                        alarm_priority = 5
                    elif severity == 2:  # WARNING
                        alarm_priority = 2
                    else:
                        alarm_priority = 3  # DEFAULT
                
                # Map metadata field names (MQTT uses alarm_value, DB uses alarm_actual_value)
                alarm_actual_value = metadata.get('alarm_value') or metadata.get('alarm_actual_value') if is_alarm else None
                alarm_setpoint = metadata.get('setpoint') or metadata.get('alarm_setpoint') if is_alarm else None
                
                # Extract acknowledgment and clearing information
                acknowledged_by = metadata.get('acknowledged_by') if is_alarm else None
                acknowledged_at = self._parse_timestamp(metadata.get('acknowledged_at')) if is_alarm and metadata.get('acknowledged_at') else None
                cleared_at = self._parse_timestamp(metadata.get('cleared_at')) if is_alarm and metadata.get('cleared_at') else None
                cleared_by = metadata.get('cleared_by') if is_alarm else None
                clear_reason = metadata.get('clear_reason') if is_alarm else None
                clear_notes = metadata.get('clear_notes') if is_alarm else None
                
                timestamp = self._parse_timestamp(event.get('time'))
                message = event.get('message')
                metadata_json = json.dumps(metadata) if metadata else None
                
                # For alarms: Check if ACTIVE alarm already exists
                if is_alarm:
                    # Check if duplicate ACTIVE alarm exists (use execute_query to properly manage cursor)
                    existing = self.db.execute_query(check_query, (tag_id, event_type))
                    
                    if existing and len(existing) > 0:
                        # UPDATE existing ACTIVE alarm (ISA-18.2: don't create duplicates)
                        update_params.append((
                            timestamp,
                            alarm_actual_value,
                            message,
                            metadata_json,
                            acknowledged_by,
                            acknowledged_at,
                            cleared_at,
                            cleared_by,
                            clear_reason,
                            clear_notes,
                            tag_id,
                            event_type
                        ))
                        logger.debug(f"Duplicate alarm detected: {tag_id} - {event_type} (will update)")
                    else:
                        # INSERT new alarm - track it for audit trail
                        insert_params.append((
                            timestamp,
                            tag_id,
                            event_type,
                            severity,
                            message,
                            metadata_json,
                            alarm_state,
                            alarm_priority,
                            alarm_actual_value,
                            alarm_setpoint,
                            acknowledged_by,
                            acknowledged_at,
                            cleared_at,
                            cleared_by,
                            clear_reason,
                            clear_notes
                        ))
                        
                        # Track this alarm for audit trail (NEW insert only)
                        newly_inserted_alarms.append({
                            'tag_id': tag_id,
                            'event_type': event_type
                        })
                        
                        logger.debug(f"New alarm to be raised: {tag_id} - {event_type}")
                else:
                    # Non-alarm events: Always insert
                    insert_params.append((
                        timestamp,
                        tag_id,
                        event_type,
                        severity,
                        message,
                        metadata_json,
                        alarm_state,
                        alarm_priority,
                        alarm_actual_value,
                        alarm_setpoint,
                        None,  # acknowledged_by
                        None,  # acknowledged_at
                        None,  # cleared_at
                        None,  # cleared_by
                        None,  # clear_reason
                        None   # clear_notes
                    ))
            
            # Execute batch insert for new alarms/events
            if insert_params:
                self.db.execute_many(insert_query, insert_params)
                records_affected += len(insert_params)
                logger.debug(f"Inserted {len(insert_params)} new records into historian_events")
            
            # Execute batch update for existing ACTIVE alarms
            if update_params:
                # For updates, we don't create audit trail entries (these are just timestamp refreshes)
                # Audit trail is only for state changes: RAISED (INSERT), ACKNOWLEDGED, CLEARED
                self.db.execute_many(update_query, update_params)
                records_affected += len(update_params)
                logger.debug(f"Updated {len(update_params)} existing ACTIVE alarms (deduplication, no audit)")
            
            return records_affected, newly_inserted_alarms
            
        except Exception as e:
            logger.error(f"Failed to insert events batch: {e}")
            raise
    
    def create_audit_trail_for_new_alarms(self, alarm_events: List[Dict[str, Any]]) -> int:
        """
        Create audit trail records for newly inserted alarm events
        
        Args:
            alarm_events: List of alarm event dicts with 'tag_id' and 'event_type'
            
        Returns:
            Number of audit trail records created
        """
        if not alarm_events or not self.audit_dao:
            return 0
        
        audit_count = 0
        
        try:
            for alarm in alarm_events:
                tag_id = alarm.get('tag_id')
                event_type = alarm.get('event_type')
                
                if not tag_id or not event_type:
                    continue
                
                # Query to find the event_id we just inserted
                event_query = """
                    SELECT event_id FROM historian_raw.historian_events
                    WHERE tag_id = %s AND event_type = %s AND alarm_state = 'ACTIVE'
                    ORDER BY time DESC LIMIT 1
                """
                events = self.db.execute_query(event_query, (tag_id, event_type))
                
                if events and len(events) > 0:
                    event_id = events[0][0]
                    
                    # Insert audit trail record
                    audit_query = """
                        INSERT INTO historian_raw.alarm_audit_trail
                        (event_id, tag_id, event_type, action_type, performed_by, 
                         previous_state, new_state, action_notes)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    self.db.execute_query(audit_query, (
                        event_id,
                        tag_id,
                        event_type,
                        'RAISED',
                        'SYSTEM',
                        None,
                        'ACTIVE',
                        f'Alarm raised via MQTT: {event_type}'
                    ), fetch=False)
                    
                    audit_count += 1
                    logger.info(f"✅ Audit trail: RAISED event_id={event_id}, tag={tag_id}")
                    
        except Exception as e:
            logger.error(f"❌ Failed to create audit trail records: {e}")
        
        return audit_count
    
    def _parse_timestamp(self, timestamp_str: str) -> datetime:
        """
        Parse timestamp string to datetime
        
        Args:
            timestamp_str: ISO format timestamp string
            
        Returns:
            datetime object
        """
        if isinstance(timestamp_str, datetime):
            return timestamp_str
        
        try:
            # Try parsing ISO format with timezone
            if '+' in timestamp_str or timestamp_str.endswith('Z'):
                return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            else:
                return datetime.fromisoformat(timestamp_str)
        except Exception as e:
            logger.warning(f"Failed to parse timestamp '{timestamp_str}': {e}, using current time")
            return datetime.utcnow()
