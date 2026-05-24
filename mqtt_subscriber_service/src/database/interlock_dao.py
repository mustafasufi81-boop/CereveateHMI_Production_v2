"""
Interlock State Data Access Object
Handles interlock_state_tracking table operations
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class InterlockDAO:
    """Interlock state database operations"""
    
    def __init__(self, db_connection):
        """
        Initialize Interlock DAO
        
        Args:
            db_connection: Database connection instance
        """
        self.db = db_connection
        logger.info("Interlock DAO initialized")
    
    def insert_interlock_state(self, state_data: Dict[str, Any]) -> Optional[int]:
        """
        REMOVED: historian_raw.interlock_state_tracking writes are owned exclusively by the
        C# InterlockEvaluationService. This method is a no-op stub. Any caller receives
        None without touching the database.

        Interlock DB ownership rule:
          - C# evaluates OPC tag values and writes SATISFIED/VIOLATED state transitions.
          - HMI reads interlock states for display and operator bypass actions only.
        """
        logger.warning(
            "insert_interlock_state called on HMI side — BLOCKED. "
            "C# InterlockEvaluationService owns interlock_state_tracking writes. "
            "tag=%s state=%s",
            state_data.get('interlock_tag_id'),
            state_data.get('interlock_state')
        )
        return None  # No-op — C# owns this table

    def _insert_interlock_state_DISABLED(self, state_data: Dict[str, Any]) -> Optional[int]:
        """
        Original implementation preserved for reference only. NOT called from anywhere.
        """
        insert_sql = """
            INSERT INTO historian_raw.interlock_state_tracking (
                event_time,
                interlock_tag_id,
                interlock_type,
                interlock_state,
                previous_state,
                state_duration_seconds,
                affected_equipment,
                bypass_reason,
                bypass_authorized_by,
                bypass_expires_at,
                related_trip_event_id
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            RETURNING interlock_event_id;
        """
        
        try:
            params = (
                state_data.get('event_time'),
                state_data.get('interlock_tag_id'),
                state_data.get('interlock_type'),
                state_data.get('interlock_state'),
                state_data.get('previous_state'),
                state_data.get('state_duration_seconds'),
                state_data.get('affected_equipment'),
                state_data.get('bypass_reason'),
                state_data.get('bypass_authorized_by'),
                state_data.get('bypass_expires_at'),
                state_data.get('related_trip_event_id')
            )
            
            result = self.db.execute_query(insert_sql, params)
            
            if result and len(result) > 0:
                event_id = result[0]['interlock_event_id']
                logger.info(f"Interlock state inserted: event_id={event_id}, "
                          f"tag={state_data.get('interlock_tag_id')}, "
                          f"state={state_data.get('interlock_state')}")
                return event_id
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to insert interlock state: {e}", exc_info=True)
            return None
    
    def get_active_violations(self, equipment_id: Optional[str] = None) -> List[Dict]:
        """
        Get active interlock violations
        
        Args:
            equipment_id: Filter by equipment (optional)
            
        Returns:
            List of violation dictionaries
        """
        where_clause = "WHERE interlock_state = 'VIOLATED'"
        params = []
        
        if equipment_id:
            where_clause += " AND affected_equipment = %s"
            params.append(equipment_id)
        
        query_sql = f"""
            SELECT 
                interlock_event_id,
                event_time,
                interlock_tag_id,
                interlock_type,
                interlock_state,
                affected_equipment,
                state_duration_seconds
            FROM historian_raw.interlock_state_tracking
            {where_clause}
            ORDER BY event_time DESC
            LIMIT 100;
        """
        
        try:
            results = self.db.execute_query(query_sql, params or None)
            return results or []
            
        except Exception as e:
            logger.error(f"Failed to query interlock violations: {e}", exc_info=True)
            return []
    
    def get_active_bypasses(self) -> List[Dict]:
        """
        Get active bypasses (including expired)
        
        Returns:
            List of bypass dictionaries
        """
        query_sql = """
            SELECT 
                interlock_event_id,
                event_time,
                interlock_tag_id,
                interlock_type,
                affected_equipment,
                bypass_reason,
                bypass_authorized_by,
                bypass_expires_at,
                CASE 
                    WHEN bypass_expires_at < NOW() THEN 'EXPIRED'
                    ELSE 'ACTIVE'
                END as bypass_status
            FROM historian_raw.interlock_state_tracking
            WHERE interlock_state = 'BYPASSED'
            ORDER BY event_time DESC
            LIMIT 100;
        """
        
        try:
            results = self.db.execute_query(query_sql)
            return results or []
            
        except Exception as e:
            logger.error(f"Failed to query interlock bypasses: {e}", exc_info=True)
            return []
    
    def get_interlock_statistics(self, hours: int = 24) -> Dict:
        """
        Get interlock statistics
        
        Args:
            hours: Hours of history
            
        Returns:
            Statistics dictionary
        """
        stats_sql = """
            SELECT 
                COUNT(*) as total_events,
                COUNT(*) FILTER (WHERE interlock_state = 'VIOLATED') as violations,
                COUNT(*) FILTER (WHERE interlock_state = 'BYPASSED') as bypasses,
                COUNT(*) FILTER (WHERE interlock_state = 'BYPASSED' 
                                 AND bypass_expires_at < NOW()) as expired_bypasses
            FROM historian_raw.interlock_state_tracking
            WHERE event_time > NOW() - INTERVAL '%s hours';
        """
        
        try:
            results = self.db.execute_query(stats_sql, (hours,))
            return results[0] if results else {}
            
        except Exception as e:
            logger.error(f"Failed to get interlock statistics: {e}", exc_info=True)
            return {}
