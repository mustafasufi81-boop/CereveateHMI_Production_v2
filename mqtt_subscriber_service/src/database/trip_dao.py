"""
Trip Event Data Access Object
Handles trip_event_tracking table operations
"""

import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class TripDAO:
    """Trip event database operations"""
    
    def __init__(self, db_connection):
        """
        Initialize Trip DAO
        
        Args:
            db_connection: Database connection instance
        """
        self.db = db_connection
        logger.info("Trip DAO initialized")
    
    def insert_trip_event(self, trip_data: Dict[str, Any]) -> Optional[int]:
        """
        Insert trip event into trip_event_tracking table
        
        Args:
            trip_data: Dictionary with keys:
                - trip_time: Timestamp of trip
                - trip_tag_id: Trip status tag ID
                - trip_category: EMERGENCY_TRIP, SAFETY_TRIP, or PROCESS_TRIP
                - equipment_affected: Equipment name
                - trip_duration_seconds: Duration (optional)
                - trip_cleared_at: Clear timestamp (optional)
                - production_loss_mw: Production loss (optional)
                - root_cause_tag_id: Root cause tag (optional)
                - operator_notes: Notes (optional)
                - automated_diagnosis: Diagnosis text (optional)
                - initiating_alarm_id: Alarm event ID (optional)
                
        Returns:
            trip_event_id or None on error
        """
        insert_sql = """
            INSERT INTO historian_raw.trip_event_tracking (
                trip_time,
                trip_tag_id,
                trip_category,
                equipment_affected,
                trip_duration_seconds,
                trip_cleared_at,
                production_loss_mw,
                rated_capacity_mw,
                revenue_per_mwh,
                root_cause_tag_id,
                operator_notes,
                automated_diagnosis,
                initiating_alarm_id
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            RETURNING trip_event_id;
        """
        
        try:
            # Convert automated_diagnosis dict to JSON string for JSONB column
            automated_diagnosis = trip_data.get('automated_diagnosis')
            if automated_diagnosis and isinstance(automated_diagnosis, dict):
                automated_diagnosis = json.dumps(automated_diagnosis)
            
            params = (
                trip_data.get('trip_time'),
                trip_data.get('trip_tag_id'),
                trip_data.get('trip_category'),
                trip_data.get('equipment_affected'),
                trip_data.get('trip_duration_seconds'),
                trip_data.get('trip_cleared_at'),
                trip_data.get('production_loss_mw'),
                trip_data.get('rated_capacity_mw'),
                trip_data.get('revenue_per_mwh'),
                trip_data.get('root_cause_tag_id'),
                trip_data.get('operator_notes'),
                automated_diagnosis,
                trip_data.get('initiating_alarm_id')
            )
            
            result = self.db.execute_query(insert_sql, params)
            
            if result and len(result) > 0:
                # Result is a list of tuples, not dictionaries
                trip_event_id = result[0][0] if isinstance(result[0], tuple) else result[0]['trip_event_id']
                logger.info(f"Trip event inserted: trip_event_id={trip_event_id}, "
                          f"equipment={trip_data.get('equipment_affected')}, "
                          f"category={trip_data.get('trip_category')}")
                return trip_event_id
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to insert trip event: {e}", exc_info=True)
            return None
    
    def update_trip_cleared(self, trip_event_id: int, 
                           cleared_at: datetime,
                           duration_seconds: Optional[int] = None) -> bool:
        """
        Update trip as cleared
        
        Args:
            trip_event_id: Trip event ID
            cleared_at: Clear timestamp
            duration_seconds: Trip duration (optional, will calculate if None)
            
        Returns:
            True on success, False otherwise
        """
        update_sql = """
            UPDATE historian_raw.trip_event_tracking
            SET trip_cleared_at = %s,
                trip_duration_seconds = COALESCE(%s, 
                    EXTRACT(EPOCH FROM (%s - trip_time))::INTEGER)
            WHERE trip_event_id = %s;
        """
        
        try:
            params = (cleared_at, duration_seconds, cleared_at, trip_event_id)
            self.db.execute_query(update_sql, params)
            
            logger.info(f"Trip cleared: trip_event_id={trip_event_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update trip cleared: {e}", exc_info=True)
            return False
    
    def get_recent_trips(self, equipment_id: Optional[str] = None,
                        hours: int = 24,
                        limit: int = 100) -> List[Dict]:
        """
        Get recent trip events
        
        Args:
            equipment_id: Filter by equipment (optional)
            hours: Hours of history
            limit: Maximum results
            
        Returns:
            List of trip event dictionaries
        """
        where_clause = "WHERE trip_time > now() - interval '%s hours'"
        params = [hours]
        
        if equipment_id:
            where_clause += " AND equipment_affected = %s"
            params.append(equipment_id)
        
        query_sql = f"""
            SELECT 
                trip_event_id,
                trip_time,
                trip_tag_id,
                trip_category,
                equipment_affected,
                trip_duration_seconds,
                trip_cleared_at,
                production_loss_mw,
                root_cause_tag_id,
                operator_notes,
                automated_diagnosis,
                initiating_alarm_id
            FROM historian_raw.trip_event_tracking
            {where_clause}
            ORDER BY trip_time DESC
            LIMIT %s;
        """
        params.append(limit)
        
        try:
            results = self.db.execute_query(query_sql, params)
            return results or []
            
        except Exception as e:
            logger.error(f"Failed to query recent trips: {e}", exc_info=True)
            return []
    
    def get_trip_by_id(self, trip_event_id: int) -> Optional[Dict]:
        """
        Get trip event by ID
        
        Args:
            trip_event_id: Trip event ID
            
        Returns:
            Trip event dictionary or None
        """
        query_sql = """
            SELECT * FROM historian_raw.trip_event_tracking
            WHERE trip_event_id = %s;
        """
        
        try:
            results = self.db.execute_query(query_sql, (trip_event_id,))
            return results[0] if results else None
            
        except Exception as e:
            logger.error(f"Failed to get trip by ID: {e}", exc_info=True)
            return None
    
    def get_trip_statistics(self, equipment_id: Optional[str] = None,
                           days: int = 30) -> Dict:
        """
        Get trip statistics
        
        Args:
            equipment_id: Filter by equipment (optional)
            days: Days of history
            
        Returns:
            Statistics dictionary
        """
        where_clause = "WHERE trip_time > now() - interval '%s days'"
        params = [days]
        
        if equipment_id:
            where_clause += " AND equipment_affected = %s"
            params.append(equipment_id)
        
        stats_sql = f"""
            SELECT 
                COUNT(*) as total_trips,
                COUNT(*) FILTER (WHERE trip_category = 'EMERGENCY_TRIP') as emergency_trips,
                COUNT(*) FILTER (WHERE trip_category = 'SAFETY_TRIP') as safety_trips,
                COUNT(*) FILTER (WHERE trip_category = 'PROCESS_TRIP') as process_trips,
                COUNT(*) FILTER (WHERE trip_cleared_at IS NULL) as ongoing_trips,
                SUM(production_loss_mw) as total_production_loss_mw,
                AVG(trip_duration_seconds) as avg_duration_seconds
            FROM historian_raw.trip_event_tracking
            {where_clause};
        """
        
        try:
            results = self.db.execute_query(stats_sql, params)
            return results[0] if results else {}
            
        except Exception as e:
            logger.error(f"Failed to get trip statistics: {e}", exc_info=True)
            return {}    
    def get_latest_uncleared_trip(self, trip_tag_id: str) -> Optional[Dict]:
        """
        Get the most recent uncleared trip for given equipment
        Used for trip recovery detection
        
        Args:
            trip_tag_id: Trip status tag ID
            
        Returns:
            Trip event dictionary or None
        """
        query_sql = """
            SELECT 
                trip_event_id,
                trip_time,
                trip_tag_id,
                trip_category,
                equipment_affected,
                production_loss_mw,
                root_cause_tag_id
            FROM historian_raw.trip_event_tracking
            WHERE trip_tag_id = %s 
                AND trip_cleared_at IS NULL
                AND trip_time > NOW() - INTERVAL '24 hours'
            ORDER BY trip_time DESC
            LIMIT 1;
        """
        
        try:
            results = self.db.execute_query(query_sql, (trip_tag_id,))
            if results and len(results) > 0:
                # Convert tuple result to dictionary
                row = results[0]
                return {
                    'trip_event_id': row[0],
                    'trip_time': row[1],
                    'trip_tag_id': row[2],
                    'trip_category': row[3],
                    'equipment_affected': row[4],
                    'production_loss_mw': row[5],
                    'root_cause_tag_id': row[6]
                }
            return None
            
        except Exception as e:
            logger.error(f"Failed to get latest uncleared trip: {e}", exc_info=True)
            return None
    
    def update_trip_recovery(self, recovery_data: Dict[str, Any]) -> bool:
        """
        Update trip with recovery information (trip_cleared_at, trip_duration_seconds)
        
        Args:
            recovery_data: Dictionary with keys:
                - trip_event_id: Trip event ID
                - trip_cleared_at: Recovery timestamp
                - trip_duration_seconds: Duration in seconds
                
        Returns:
            True on success, False otherwise
        """
        update_sql = """
            UPDATE historian_raw.trip_event_tracking
            SET trip_cleared_at = %s,
                trip_duration_seconds = %s
            WHERE trip_event_id = %s;
        """
        
        try:
            params = (
                recovery_data.get('trip_cleared_at'),
                recovery_data.get('trip_duration_seconds'),
                recovery_data.get('trip_event_id')
            )
            self.db.execute_query(update_sql, params)
            
            logger.info(f"Trip recovery updated: trip_event_id={recovery_data.get('trip_event_id')}, "
                       f"duration={recovery_data.get('trip_duration_seconds')}s")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update trip recovery: {e}", exc_info=True)
            return False