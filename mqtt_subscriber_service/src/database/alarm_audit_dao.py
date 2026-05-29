"""
Alarm Audit Trail Data Access Object (DAO)
Handles all alarm audit trail operations for ISA-18.2 compliance
"""

import json
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from src.monitoring.logger import get_logger

logger = get_logger(__name__)


class AlarmAuditDAO:
    """Data Access Object for alarm_audit_trail table"""
    
    def __init__(self, db_connection):
        """
        Initialize Alarm Audit DAO
        
        Args:
            db_connection: DatabaseConnection instance or HistoricalDataService instance
        """
        self.db = db_connection
        # Check if it's a HistoricalDataService (has 'connection' attribute) or DatabaseConnection (has 'get_cursor' method)
        self.use_direct_connection = hasattr(db_connection, 'connection') and not hasattr(db_connection, 'get_cursor')
    
    def _get_cursor(self):
        """Get a database cursor compatible with both connection types"""
        if self.use_direct_connection:
            # HistoricalDataService - use connection directly
            return self.db.connection.cursor()
        else:
            # DatabaseConnection - use get_cursor context manager
            return self.db.get_cursor()
    
    def insert_audit_record(self, 
                           event_id: int,
                           tag_id: str,
                           event_type: str,
                           action_type: str,
                           performed_by: str,
                           previous_state: Optional[str] = None,
                           new_state: str = None,
                           alarm_priority: Optional[int] = None,
                           alarm_actual_value: Optional[float] = None,
                           alarm_setpoint: Optional[float] = None,
                           action_reason: Optional[str] = None,
                           action_notes: Optional[str] = None,
                           session_id: Optional[str] = None,
                           client_ip: Optional[str] = None,
                           occurrence_id: Optional[str] = None,
                           metadata: Optional[Dict[str, Any]] = None) -> Optional[int]:
        """
        Insert a new audit trail record for an alarm action
        
        Args:
            event_id: Reference to historian_events.event_id
            tag_id: Tag identifier
            event_type: Alarm event type (e.g., ALARM_HIGH_CRITICAL)
            action_type: Type of action ('RAISED', 'ACKNOWLEDGED', 'CLEARED', 'SUPPRESSED', etc.)
            performed_by: Username/operator who performed the action
            previous_state: Previous alarm_state before action
            new_state: New alarm_state after action
            alarm_priority: Priority level (1-5)
            alarm_actual_value: Process value at time of action
            alarm_setpoint: Alarm threshold/setpoint
            action_reason: Reason for the action (e.g., clear reason)
            action_notes: Additional operator notes
            session_id: User session ID for tracking
            client_ip: IP address of client making the change
            metadata: Additional context as dictionary (shift, location, etc.)
            
        Returns:
            audit_id if successful, None otherwise
        """
        query = """
            INSERT INTO historian_raw.alarm_audit_trail 
            (event_id, tag_id, event_type, action_type, action_timestamp, performed_by,
             previous_state, new_state, alarm_priority, alarm_actual_value, alarm_setpoint,
             action_reason, action_notes, session_id, client_ip, occurrence_id, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING audit_id
        """
        
        cursor = None
        try:
            metadata_json = json.dumps(metadata) if metadata else None
            
            if self.use_direct_connection:
                # HistoricalDataService - use connection directly
                cursor = self.db.connection.cursor()
                
                cursor.execute(query, (
                    event_id,
                    tag_id,
                    event_type,
                    action_type,
                    datetime.now(timezone.utc),
                    performed_by,
                    previous_state,
                    new_state,
                    alarm_priority,
                    alarm_actual_value,
                    alarm_setpoint,
                    action_reason,
                    action_notes,
                    session_id,
                    client_ip,
                    occurrence_id,
                    metadata_json
                ))
                
                result = cursor.fetchone()
                self.db.connection.commit()
                cursor.close()
                
                if result:
                    # HistoricalDataService uses RealDictCursor, so result is a dict
                    audit_id = result.get('audit_id') if isinstance(result, dict) else result[0]
                    logger.info(f"Alarm audit record created: audit_id={audit_id}, event_id={event_id}, "
                               f"action={action_type}, performed_by={performed_by}, {previous_state}→{new_state}")
                    return audit_id
                else:
                    logger.error(f"INSERT RETURNING returned no audit_id for event_id={event_id}")
                    return None
            else:
                # DatabaseConnection - use execute_query with fetch=False, then query for audit_id
                # INSERT without RETURNING for compatibility
                insert_query = """
                    INSERT INTO historian_raw.alarm_audit_trail 
                    (event_id, tag_id, event_type, action_type, action_timestamp, performed_by,
                     previous_state, new_state, alarm_priority, alarm_actual_value, alarm_setpoint,
                     action_reason, action_notes, session_id, client_ip, occurrence_id, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                
                self.db.execute_query(insert_query, (
                    event_id,
                    tag_id,
                    event_type,
                    action_type,
                    datetime.now(timezone.utc),
                    performed_by,
                    previous_state,
                    new_state,
                    alarm_priority,
                    alarm_actual_value,
                    alarm_setpoint,
                    action_reason,
                    action_notes,
                    session_id,
                    client_ip,
                    occurrence_id,
                    metadata_json
                ), fetch=False)
                
                logger.info(f"Alarm audit record created: event_id={event_id}, "
                           f"action={action_type}, performed_by={performed_by}, {previous_state}→{new_state}")
                return True
                
        except Exception as e:
            if self.use_direct_connection and cursor:
                try:
                    cursor.close()
                except:
                    pass
            logger.error(f"Failed to insert alarm audit record: {e}")
            logger.error(f"event_id={event_id}, action_type={action_type}, performed_by={performed_by}")
            return None
    
    def get_audit_trail(self, 
                       event_id: Optional[int] = None,
                       tag_id: Optional[str] = None,
                       limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get audit trail records for an alarm or tag
        
        Args:
            event_id: Filter by specific alarm event_id
            tag_id: Filter by tag_id
            limit: Maximum number of records to return
            
        Returns:
            List of audit records as dictionaries
        """
        # Build query with optional filters
        where_clauses = []
        params = []
        
        if event_id is not None:
            where_clauses.append("event_id = %s")
            params.append(event_id)
        
        if tag_id is not None:
            where_clauses.append("tag_id = %s")
            params.append(tag_id)
        
        where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
        
        query = f"""
            SELECT 
                audit_id,
                event_id,
                tag_id,
                event_type,
                action_type,
                action_timestamp,
                performed_by,
                previous_state,
                new_state,
                alarm_priority,
                alarm_actual_value,
                alarm_setpoint,
                action_reason,
                action_notes,
                session_id,
                client_ip,
                metadata,
                created_at
            FROM historian_raw.alarm_audit_trail
            {where_sql}
            ORDER BY action_timestamp DESC
            LIMIT %s
        """
        
        params.append(limit)
        
        cursor = None
        try:
            if self.use_direct_connection:
                cursor = self._get_cursor()
                cursor.execute(query, tuple(params))
                results = cursor.fetchall()
                cursor.close()
            else:
                with self._get_cursor() as cur:
                    cur.execute(query, tuple(params))
                    results = cur.fetchall()
            
            if not results:
                return []
            
            audit_records = []
            for row in results:
                record = {
                    'audit_id': row[0],
                    'event_id': row[1],
                    'tag_id': row[2],
                    'event_type': row[3],
                    'action_type': row[4],
                    'action_timestamp': row[5].isoformat() if row[5] else None,
                    'performed_by': row[6],
                    'previous_state': row[7],
                    'new_state': row[8],
                    'alarm_priority': row[9],
                    'alarm_actual_value': row[10],
                    'alarm_setpoint': row[11],
                    'action_reason': row[12],
                    'action_notes': row[13],
                    'session_id': row[14],
                    'client_ip': row[15],
                    'metadata': row[16],  # Already JSON/dict from JSONB column
                    'created_at': row[17].isoformat() if row[17] else None
                }
                audit_records.append(record)
            
            logger.debug(f"Retrieved {len(audit_records)} audit records (event_id={event_id}, tag_id={tag_id})")
            return audit_records
            
        except Exception as e:
            if self.use_direct_connection and cursor:
                try:
                    cursor.close()
                except:
                    pass
            logger.error(f"Failed to retrieve audit trail: {e}")
            return []
    
    def count_audit_records(self,
                           event_id: Optional[int] = None,
                           tag_id: Optional[str] = None) -> int:
        """
        Count total audit records matching filters (for pagination)
        
        Args:
            event_id: Filter by specific alarm event_id
            tag_id: Filter by tag_id
            
        Returns:
            Total count of matching records
        """
        where_clauses = []
        params = []
        
        if event_id is not None:
            where_clauses.append("event_id = %s")
            params.append(event_id)
        
        if tag_id is not None:
            where_clauses.append("tag_id = %s")
            params.append(tag_id)
        
        where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
        
        query = f"""
            SELECT COUNT(*)
            FROM historian_raw.alarm_audit_trail
            {where_sql}
        """
        
        cursor = None
        try:
            if self.use_direct_connection:
                cursor = self._get_cursor()
                cursor.execute(query, tuple(params))
                result = cursor.fetchone()
                cursor.close()
            else:
                with self._get_cursor() as cur:
                    cur.execute(query, tuple(params))
                    result = cur.fetchone()
            
            count = result[0] if result else 0
            logger.debug(f"Counted {count} audit records")
            return count
            
        except Exception as e:
            if self.use_direct_connection and cursor:
                try:
                    cursor.close()
                except:
                    pass
            logger.error(f"Failed to count audit records: {e}")
            return 0
    
    def get_audit_trail_enhanced(self, 
                                event_id: Optional[int] = None,
                                tag_id: Optional[str] = None,
                                limit: int = 100,
                                offset: int = 0,
                                sort_order: str = 'desc') -> List[Dict[str, Any]]:
        """
        Get enhanced audit trail with tag names and timing calculations
        Uses the v_alarm_audit_trail view
        
        Args:
            event_id: Filter by specific alarm event_id
            tag_id: Filter by tag_id
            limit: Maximum number of records to return
            offset: Number of records to skip (for pagination)
            sort_order: 'desc' for newest first, 'asc' for oldest first (timeline view)
            
        Returns:
            List of enhanced audit records as dictionaries
        """
        where_clauses = []
        params = []
        
        if event_id is not None:
            where_clauses.append("event_id = %s")
            params.append(event_id)
        
        if tag_id is not None:
            where_clauses.append("tag_id = %s")
            params.append(tag_id)
        
        where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
        
        # Validate and set sort order
        order_direction = 'DESC' if sort_order.lower() == 'desc' else 'ASC'
        
        query = f"""
            SELECT 
                audit_id,
                event_id,
                tag_id,
                tag_name,
                tag_description,
                plant,
                area,
                equipment,
                event_type,
                action_type,
                action_timestamp,
                performed_by,
                previous_state,
                new_state,
                alarm_priority,
                priority_label,
                alarm_actual_value,
                alarm_setpoint,
                action_reason,
                action_notes,
                session_id,
                client_ip,
                metadata,
                created_at,
                minutes_since_previous_action,
                minutes_since_raised,
                response_time_seconds,
                occurrence_id,
                sequence_number,
                performed_by_display_name,
                performed_by_user_id
            FROM historian_raw.v_alarm_audit_trail
            {where_sql}
            ORDER BY action_timestamp {order_direction}
            LIMIT %s OFFSET %s
        """
        
        params.append(limit)
        params.append(offset)
        
        cursor = None
        try:
            if self.use_direct_connection:
                cursor = self._get_cursor()
                cursor.execute(query, tuple(params))
                results = cursor.fetchall()
                cursor.close()
            else:
                with self._get_cursor() as cur:
                    cur.execute(query, tuple(params))
                    results = cur.fetchall()
            
            if not results:
                return []
            
            audit_records = []
            for row in results:
                # Handle both RealDictCursor (dict) and regular cursor (tuple)
                if isinstance(row, dict):
                    record = {
                        'audit_id': row.get('audit_id'),
                        'event_id': row.get('event_id'),
                        'tag_id': row.get('tag_id'),
                        'tag_name': row.get('tag_name'),
                        'tag_description': row.get('tag_description'),
                        'plant': row.get('plant'),
                        'area': row.get('area'),
                        'equipment': row.get('equipment'),
                        'event_type': row.get('event_type'),
                        'action_type': row.get('action_type'),
                        'action_timestamp': row.get('action_timestamp').isoformat() if row.get('action_timestamp') else None,
                        'performed_by': row.get('performed_by'),
                        'previous_state': row.get('previous_state'),
                        'new_state': row.get('new_state'),
                        'alarm_priority': row.get('alarm_priority'),
                        'priority_label': row.get('priority_label'),
                        'alarm_actual_value': row.get('alarm_actual_value'),
                        'alarm_setpoint': row.get('alarm_setpoint'),
                        'action_reason': row.get('action_reason'),
                        'action_notes': row.get('action_notes'),
                        'session_id': row.get('session_id'),
                        'client_ip': row.get('client_ip'),
                        'metadata': row.get('metadata'),
                        'created_at': row.get('created_at').isoformat() if row.get('created_at') else None,
                        'minutes_since_previous_action': float(row.get('minutes_since_previous_action')) if row.get('minutes_since_previous_action') else None,
                        'minutes_since_raised': float(row.get('minutes_since_raised')) if row.get('minutes_since_raised') else None,
                        'response_time_seconds': float(row.get('response_time_seconds')) if row.get('response_time_seconds') else None,
                        'occurrence_id': str(row.get('occurrence_id')) if row.get('occurrence_id') else None,
                        'sequence_number': row.get('sequence_number'),
                        'performed_by_display_name': row.get('performed_by_display_name'),
                        'performed_by_user_id': row.get('performed_by_user_id')
                    }
                else:
                    # Tuple-based cursor
                    record = {
                        'audit_id': row[0],
                        'event_id': row[1],
                        'tag_id': row[2],
                        'tag_name': row[3],
                        'tag_description': row[4],
                        'plant': row[5],
                        'area': row[6],
                        'equipment': row[7],
                        'event_type': row[8],
                        'action_type': row[9],
                        'action_timestamp': row[10].isoformat() if row[10] else None,
                        'performed_by': row[11],
                        'previous_state': row[12],
                        'new_state': row[13],
                        'alarm_priority': row[14],
                        'priority_label': row[15],
                        'alarm_actual_value': row[16],
                        'alarm_setpoint': row[17],
                        'action_reason': row[18],
                        'action_notes': row[19],
                        'session_id': row[20],
                        'client_ip': row[21],
                        'metadata': row[22],
                        'created_at': row[23].isoformat() if row[23] else None,
                        'minutes_since_previous_action': float(row[24]) if row[24] else None,
                        'minutes_since_raised': float(row[25]) if row[25] else None,
                        'response_time_seconds': float(row[26]) if row[26] else None,
                        'occurrence_id': str(row[27]) if row[27] else None,
                        'sequence_number': row[28],
                        'performed_by_display_name': row[29],
                        'performed_by_user_id': row[30]
                    }
                audit_records.append(record)
            
            logger.debug(f"Retrieved {len(audit_records)} enhanced audit records")
            return audit_records
            
        except Exception as e:
            if self.use_direct_connection and cursor:
                try:
                    cursor.close()
                except:
                    pass
            logger.error(f"Failed to retrieve enhanced audit trail: {e}")
            return []
    
    def get_operator_statistics(self, 
                               performed_by: str,
                               days: int = 7) -> Dict[str, Any]:
        """
        Get statistics for a specific operator's alarm actions
        
        Args:
            performed_by: Operator username
            days: Number of days to look back
            
        Returns:
            Dictionary with operator statistics
        """
        query = """
            SELECT 
                COUNT(*) as total_actions,
                COUNT(*) FILTER (WHERE action_type = 'ACKNOWLEDGED') as acks_count,
                COUNT(*) FILTER (WHERE action_type = 'CLEARED') as clears_count,
                AVG(minutes_since_previous_action) FILTER (WHERE action_type = 'ACKNOWLEDGED') as avg_ack_response_minutes,
                MIN(minutes_since_previous_action) FILTER (WHERE action_type = 'ACKNOWLEDGED') as fastest_ack_minutes,
                MAX(minutes_since_previous_action) FILTER (WHERE action_type = 'ACKNOWLEDGED') as slowest_ack_minutes
            FROM historian_raw.v_alarm_audit_trail
            WHERE performed_by = %s
              AND action_timestamp >= NOW() - INTERVAL '%s days'
        """
        
        cursor = None
        try:
            if self.use_direct_connection:
                cursor = self._get_cursor()
                cursor.execute(query, (performed_by, days))
                result = cursor.fetchall()
                cursor.close()
            else:
                with self._get_cursor() as cur:
                    cur.execute(query, (performed_by, days))
                    result = cur.fetchall()
            
            if not result or len(result) == 0:
                return {
                    'performed_by': performed_by,
                    'days': days,
                    'total_actions': 0,
                    'acks_count': 0,
                    'clears_count': 0,
                    'avg_ack_response_minutes': None,
                    'fastest_ack_minutes': None,
                    'slowest_ack_minutes': None
                }
            
            row = result[0]
            stats = {
                'performed_by': performed_by,
                'days': days,
                'total_actions': row[0] or 0,
                'acks_count': row[1] or 0,
                'clears_count': row[2] or 0,
                'avg_ack_response_minutes': float(row[3]) if row[3] else None,
                'fastest_ack_minutes': float(row[4]) if row[4] else None,
                'slowest_ack_minutes': float(row[5]) if row[5] else None
            }
            
            logger.debug(f"Retrieved operator statistics for {performed_by}")
            return stats
            
        except Exception as e:
            if self.use_direct_connection and cursor:
                try:
                    cursor.close()
                except:
                    pass
            logger.error(f"Failed to retrieve operator statistics: {e}")
            return {
                'performed_by': performed_by,
                'days': days,
                'error': str(e)
            }
    
    def get_unacknowledged_alarms(self, hours: int = 24) -> List[Dict[str, Any]]:
        """
        Get alarms that were raised but never acknowledged
        
        Args:
            hours: Number of hours to look back
            
        Returns:
            List of unacknowledged alarm records
        """
        query = """
            SELECT 
                event_id,
                tag_id,
                tag_name,
                event_type,
                action_timestamp as raised_at,
                alarm_priority,
                priority_label,
                alarm_actual_value,
                alarm_setpoint,
                EXTRACT(EPOCH FROM (NOW() - action_timestamp))/60 as minutes_since_raised
            FROM historian_raw.v_alarm_audit_trail
            WHERE action_type = 'RAISED'
              AND action_timestamp >= NOW() - INTERVAL '%s hours'
              AND event_id NOT IN (
                  SELECT DISTINCT event_id 
                  FROM historian_raw.alarm_audit_trail 
                  WHERE action_type = 'ACKNOWLEDGED'
              )
            ORDER BY alarm_priority DESC, action_timestamp DESC
        """
        
        cursor = None
        try:
            if self.use_direct_connection:
                cursor = self._get_cursor()
                cursor.execute(query, (hours,))
                results = cursor.fetchall()
                cursor.close()
            else:
                with self._get_cursor() as cur:
                    cur.execute(query, (hours,))
                    results = cur.fetchall()
            
            if not results:
                return []
            
            unacked_alarms = []
            for row in results:
                alarm = {
                    'event_id': row[0],
                    'tag_id': row[1],
                    'tag_name': row[2],
                    'event_type': row[3],
                    'raised_at': row[4].isoformat() if row[4] else None,
                    'alarm_priority': row[5],
                    'priority_label': row[6],
                    'alarm_actual_value': row[7],
                    'alarm_setpoint': row[8],
                    'minutes_since_raised': float(row[9]) if row[9] else None
                }
                unacked_alarms.append(alarm)
            
            logger.info(f"Found {len(unacked_alarms)} unacknowledged alarms in last {hours} hours")
            return unacked_alarms
            
        except Exception as e:
            if self.use_direct_connection and cursor:
                try:
                    cursor.close()
                except:
                    pass
            logger.error(f"Failed to retrieve unacknowledged alarms: {e}")
            return []
