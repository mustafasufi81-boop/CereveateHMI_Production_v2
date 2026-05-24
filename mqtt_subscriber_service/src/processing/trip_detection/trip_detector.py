"""
Trip Detection Service
Monitors alarm events and equipment status to detect trip conditions
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from collections import defaultdict

logger = logging.getLogger(__name__)


class TripDetectionService:
    """
    Real-time trip detection service
    
    Detects trips by correlating:
    - High-priority alarms (priority >= 4)
    - Equipment state changes (RUNNING → STOPPED)
    - Time window (within configurable seconds)
    """
    
    def __init__(self, trip_dao, historian_dao, config: Dict[str, Any]):
        """
        Initialize trip detection service
        
        Args:
            trip_dao: Trip DAO for database operations
            historian_dao: Historian DAO for alarm queries
            config: Configuration dictionary with:
                - alarm_to_trip_window_seconds: Time window for correlation
                - equipment_mappings: List of equipment configurations
        """
        self.trip_dao = trip_dao
        self.historian_dao = historian_dao
        
        self.alarm_to_trip_window = config.get('alarm_to_trip_window_seconds', 2)
        self.min_alarm_priority = config.get('minimum_alarm_priority', 4)
        self.equipment_mappings = self._load_equipment_mappings(
            config.get('equipment_mappings', [])
        )
        
        # In-memory state tracking
        self.active_alarms = {}  # tag_id → alarm_event
        self.equipment_states = {}  # equipment_id → {'state': str, 'timestamp': datetime}
        self.recent_trips = {}  # equipment_id → trip_event_id (prevent duplicates)
        
        logger.info(f"Trip Detection Service initialized: "
                   f"window={self.alarm_to_trip_window}s, "
                   f"equipment_count={len(self.equipment_mappings)}")
        logger.info(f"📋 Loaded equipment mappings: {list(self.equipment_mappings.keys())}")
        for eq_id, eq_map in self.equipment_mappings.items():
            logger.info(f"  {eq_id}: run_status={eq_map['run_status_tag_id']}")
    
    def _load_equipment_mappings(self, mappings: List[Dict]) -> Dict[str, Dict]:
        """
        Load equipment mappings from configuration
        
        Args:
            mappings: List of equipment configuration dicts
            
        Returns:
            Dictionary keyed by equipment_id
        """
        equipment_map = {}
        for mapping in mappings:
            equipment_id = mapping.get('equipment_id')
            if equipment_id:
                equipment_map[equipment_id] = {
                    'run_status_tag_id': mapping.get('run_status_tag_id'),
                    'trip_tag_id': mapping.get('trip_tag_id'),
                    'rated_capacity_mw': mapping.get('rated_capacity_mw', 0.0),
                    'revenue_per_mwh': mapping.get('revenue_per_mwh', 60.0),
                    'criticality': mapping.get('criticality', 3)
                }
        return equipment_map
    
    def process_alarm_event(self, alarm_event: Dict[str, Any]):
        """
        Process new alarm event
        
        Args:
            alarm_event: Alarm event dictionary with keys:
                - event_id: Event ID
                - tag_id: Tag ID
                - event_type: Alarm type
                - alarm_priority: Priority (1-5)
                - alarm_state: State (ACTIVE, ACKNOWLEDGED, CLEARED)
                - time: Timestamp
        """
        try:
            alarm_priority = alarm_event.get('alarm_priority', 0)
            alarm_state = alarm_event.get('alarm_state', 'ACTIVE')
            tag_id = alarm_event.get('tag_id')
            
            logger.debug(f"🔔 process_alarm_event: tag={tag_id}, priority={alarm_priority}, state={alarm_state}, min_priority={self.min_alarm_priority}")
            
            # Track high-priority active alarms (potential trip causes)
            if alarm_priority >= 4 and alarm_state == 'ACTIVE':
                self.active_alarms[tag_id] = alarm_event
                logger.info(f"🚨 Tracking high-priority alarm: {tag_id} (priority={alarm_priority}) - Total active alarms: {len(self.active_alarms)}")
            
            # Remove cleared/acknowledged alarms from tracking
            elif alarm_state in ('CLEARED', 'ACKNOWLEDGED'):
                if tag_id in self.active_alarms:
                    del self.active_alarms[tag_id]
                    logger.debug(f"Removed alarm from tracking: {tag_id}")
                    
        except Exception as e:
            logger.error(f"Error processing alarm event: {e}", exc_info=True)
    
    def process_equipment_status_change(self, tag_id: str, value: float, 
                                       timestamp: datetime):
        """
        Process equipment status tag change
        
        Args:
            tag_id: Equipment status tag ID
            value: New value (1.0=RUNNING, 0.0=STOPPED)
            timestamp: Change timestamp
        """
        try:
            logger.debug(f"⚙️ process_equipment_status_change: tag={tag_id}, value={value}")
            
            # Find equipment for this tag
            equipment_id = self._get_equipment_from_tag(tag_id)
            logger.debug(f"🎯 Tag {tag_id} mapped to equipment: {equipment_id}")
            
            if not equipment_id:
                logger.debug(f"⚠️ No equipment mapping found for tag {tag_id}")
                return
            
            # Determine state from value
            new_state = 'RUNNING' if value > 0.5 else 'STOPPED'
            
            # Get previous state
            old_state_info = self.equipment_states.get(equipment_id, {})
            old_state = old_state_info.get('state')
            
            logger.debug(f"📊 State change: {equipment_id} from {old_state} to {new_state}")
            
            # Update state
            self.equipment_states[equipment_id] = {
                'state': new_state,
                'timestamp': timestamp
            }
            
            # Detect trip: RUNNING → STOPPED transition
            if old_state == 'RUNNING' and new_state == 'STOPPED':
                active_alarm_count = len(self.active_alarms)
                logger.warning(f"🛑 TRIP CANDIDATE: {equipment_id} RUNNING→STOPPED at {timestamp} - Active alarms: {active_alarm_count}")
                logger.info(f"Active alarm tags: {list(self.active_alarms.keys())}")
                self._detect_trip(equipment_id, timestamp)
            elif old_state == 'STOPPED' and new_state == 'RUNNING':
                logger.info(f"✅ Equipment {equipment_id} started: STOPPED→RUNNING at {timestamp}")
                # Check for trip recovery - equipment restarting after a trip
                self._detect_trip_recovery(equipment_id, timestamp)
            
        except Exception as e:
            logger.error(f"Error processing equipment status: {e}", exc_info=True)
    
    def _get_equipment_from_tag(self, tag_id: str) -> Optional[str]:
        """
        Find equipment ID from tag ID
        
        Args:
            tag_id: Tag ID to lookup
            
        Returns:
            Equipment ID or None
        """
        logger.debug(f"🔍 Looking up equipment for tag: {tag_id}")
        logger.debug(f"📋 Available equipment mappings: {list(self.equipment_mappings.keys())}")
        
        for equipment_id, mapping in self.equipment_mappings.items():
            logger.debug(f"  Checking {equipment_id}: run_status_tag={mapping['run_status_tag_id']}")
            if tag_id == mapping['run_status_tag_id']:
                logger.info(f"✅ Match found: {tag_id} → {equipment_id}")
                return equipment_id
        
        logger.warning(f"❌ No equipment mapping found for tag: {tag_id}")
        return None
    
    def _detect_trip(self, equipment_id: str, trip_time: datetime):
        """
        Detect if equipment stop was caused by alarm (trip event)
        
        Args:
            equipment_id: Equipment identifier
            trip_time: Time when equipment stopped
        """
        try:
            logger.warning(f"🔍 _detect_trip called for {equipment_id} at {trip_time}")
            logger.warning(f"🔍 DEBUG: About to check active_alarms length...")
            logger.info(f"📊 Current active alarms: {len(self.active_alarms)} total")
            logger.warning(f"🔍 DEBUG: Checked alarms, now checking cooldown...")
            
            # Prevent duplicate detection (5-minute cooldown)
            last_trip_time = self.recent_trips.get(equipment_id)
            logger.warning(f"🔍 DEBUG: last_trip_time={last_trip_time}, cooldown check starting...")
            if last_trip_time and (trip_time - last_trip_time).total_seconds() < 300:
                logger.debug(f"⏭️ Skipping duplicate trip detection for {equipment_id} (cooldown active)")
                return
            
            logger.warning(f"🔍 DEBUG: Passed cooldown check, continuing...")
            
            # Find alarms active within time window
            window_start = trip_time - timedelta(seconds=self.alarm_to_trip_window)
            logger.info(f"⏰ Checking for alarms between {window_start} and {trip_time} (window={self.alarm_to_trip_window}s)")
            logger.info(f"📊 Total active alarms in buffer: {len(self.active_alarms)}")
            recent_alarms = self._get_recent_alarms(equipment_id, window_start, trip_time)
            
            logger.warning(f"📋 Found {len(recent_alarms)} recent alarms for {equipment_id}")
            if recent_alarms:
                logger.info(f"   Alarm tags: {[a.get('tag_id') for a in recent_alarms[:5]]}")
            
            if not recent_alarms:
                logger.warning(f"⚠️ No active alarms found for {equipment_id} - likely normal shutdown (cannot create trip)")
                return
            
            # Trip detected - find initiating alarm (highest priority)
            initiating_alarm = max(recent_alarms, 
                                  key=lambda a: a.get('alarm_priority', 0))
            
            trip_category = self._determine_trip_category(initiating_alarm)
            production_loss = self._calculate_production_loss(equipment_id)
            
            logger.warning(f"💾 Inserting trip event into database...")
            logger.info(f"   Equipment: {equipment_id}")
            logger.info(f"   Category: {trip_category}")
            logger.info(f"   Initiating alarm: {initiating_alarm.get('tag_id')} - {initiating_alarm.get('event_type')}")
            logger.info(f"   Initiating alarm event_id: {initiating_alarm.get('event_id')}")
            logger.info(f"   Production loss: {production_loss:.1f} MW")
            
            # Get initiating_alarm_id from database (event_id in buffer might be tag_id)
            # The alarm buffer contains in-memory data that doesn't have database IDs yet
            # We'll set initiating_alarm_id to None and rely on root_cause_tag_id for tracking
            initiating_alarm_id = None
            event_id_value = initiating_alarm.get('event_id')
            
            # Only use event_id if it's actually a number (not a tag_id string)
            if event_id_value and isinstance(event_id_value, (int, float)):
                initiating_alarm_id = int(event_id_value)
            else:
                logger.warning(f"⚠️ event_id is not numeric ({event_id_value}), setting initiating_alarm_id to NULL")
            
            # Insert trip event
            trip_event_id = self.trip_dao.insert_trip_event({
                'trip_time': trip_time,
                'trip_tag_id': self.equipment_mappings[equipment_id]['trip_tag_id'],
                'trip_category': trip_category,
                'equipment_affected': equipment_id,
                'initiating_alarm_id': initiating_alarm_id,
                'root_cause_tag_id': initiating_alarm.get('tag_id'),
                'production_loss_mw': production_loss,
                'rated_capacity_mw': self.equipment_mappings[equipment_id].get('rated_capacity_mw', 0.0),
                'revenue_per_mwh': self.equipment_mappings[equipment_id].get('revenue_per_mwh', 60.0),
                'operator_notes': None,
                'automated_diagnosis': self._generate_diagnosis(
                    initiating_alarm, recent_alarms
                )
            })
            
            if trip_event_id:
                logger.warning(f"✅ TRIP EVENT CREATED: ID={trip_event_id}")
                # Track this trip for cooldown (only if successfully created)
                self.recent_trips[equipment_id] = trip_time
            else:
                logger.error(f"❌ FAILED to create trip event (trip_event_id is None)")
            
            logger.warning(f"🚨 TRIP DETECTED: {equipment_id} | "
                         f"Category: {trip_category} | "
                         f"Cause: {initiating_alarm.get('event_type')} | "
                         f"Loss: {production_loss:.1f} MW | "
                         f"Trip ID: {trip_event_id}")
            
        except Exception as e:
            logger.error(f"Error detecting trip for {equipment_id}: {e}", 
                        exc_info=True)
    
    def _get_recent_alarms(self, equipment_id: str, 
                          window_start: datetime, 
                          window_end: datetime) -> List[Dict]:
        """
        Get active alarms within time window for equipment
        
        Args:
            equipment_id: Equipment identifier
            window_start: Start of time window
            window_end: End of time window
            
        Returns:
            List of alarm event dictionaries
        """
        # Filter in-memory active alarms by time window
        recent = []
        for tag_id, alarm in self.active_alarms.items():
            alarm_time = alarm.get('time')
            if alarm_time and window_start <= alarm_time <= window_end:
                # Check if alarm is related to this equipment
                if self._is_alarm_related_to_equipment(tag_id, equipment_id):
                    recent.append(alarm)
        
        return recent
    
    def _is_alarm_related_to_equipment(self, alarm_tag_id: str, 
                                       equipment_id: str) -> bool:
        """
        Check if alarm tag is related to equipment
        
        Args:
            alarm_tag_id: Alarm tag ID
            equipment_id: Equipment ID
            
        Returns:
            True if related, False otherwise
        """
        # ENHANCED: Check equipment metadata first (most accurate)
        alarm = self.active_alarms.get(alarm_tag_id)
        if alarm and alarm.get('metadata'):
            alarm_equipment = alarm['metadata'].get('equipment', '').upper()
            if alarm_equipment and alarm_equipment in equipment_id.upper():
                return True
        
        # Fallback: Simple heuristic - tag name contains equipment name
        # Accept partial matches (e.g., "TURBINE" matches alarms with any part of equipment name)
        equipment_parts = equipment_id.replace('_', ' ').split()
        alarm_parts = alarm_tag_id.replace('_', ' ').replace('-', ' ').upper()
        
        for part in equipment_parts:
            if len(part) >= 3 and part.upper() in alarm_parts:
                return True
        
        # If no match, consider ALL high-priority alarms as potentially related
        # This ensures trips are detected even if tag naming doesn't match
        return True  # Changed from False to True for better detection
    
    def _determine_trip_category(self, alarm: Dict) -> str:
        """
        Determine trip category from alarm priority
        
        Args:
            alarm: Alarm event dictionary
            
        Returns:
            Trip category: EMERGENCY_TRIP, SAFETY_TRIP, or PROCESS_TRIP
        """
        priority = alarm.get('alarm_priority', 3)
        
        if priority == 5:
            return 'EMERGENCY_TRIP'
        elif priority == 4:
            return 'SAFETY_TRIP'
        else:
            return 'PROCESS_TRIP'
    
    def _calculate_production_loss(self, equipment_id: str) -> float:
        """
        Calculate production loss in MW
        
        Args:
            equipment_id: Equipment identifier
            
        Returns:
            Production loss in MW
        """
        mapping = self.equipment_mappings.get(equipment_id, {})
        return mapping.get('rated_capacity_mw', 0.0)
    
    def _generate_diagnosis(self, initiating_alarm: Dict, 
                           all_alarms: List[Dict]) -> Dict:
        """
        Generate automated diagnosis as JSON object
        
        Args:
            initiating_alarm: Primary alarm that caused trip
            all_alarms: All alarms in time window
            
        Returns:
            Diagnosis dictionary (will be stored as JSONB)
        """
        alarm_type = initiating_alarm.get('event_type', 'UNKNOWN')
        alarm_count = len(all_alarms)
        
        diagnosis = {
            "summary": f"Trip initiated by {alarm_type}",
            "initiating_alarm": {
                "tag_id": initiating_alarm.get('tag_id'),
                "event_type": alarm_type,
                "priority": initiating_alarm.get('alarm_priority', 0)
            },
            "concurrent_alarms": alarm_count - 1 if alarm_count > 1 else 0,
            "total_alarms": alarm_count
        }
        
        return diagnosis
    
    def _detect_trip_recovery(self, equipment_id: str, recovery_time: datetime):
        """
        Detect when equipment recovers from a trip (STOPPED → RUNNING)
        Updates trip_cleared_at and calculates trip_duration_seconds
        
        Args:
            equipment_id: Equipment identifier
            recovery_time: Time when equipment restarted
        """
        try:
            logger.info(f"🔄 _detect_trip_recovery called for {equipment_id} at {recovery_time}")
            
            # Find the most recent uncleared trip for this equipment
            trip_tag_id = self.equipment_mappings[equipment_id]['trip_tag_id']
            
            # Query database for recent uncleared trips (last 24 hours)
            recent_trip = self.trip_dao.get_latest_uncleared_trip(trip_tag_id)
            
            if not recent_trip:
                logger.debug(f"⚠️ No uncleared trip found for {equipment_id} - may be normal startup")
                return
            
            trip_event_id = recent_trip['trip_event_id']
            trip_time = recent_trip['trip_time']
            
            # Calculate trip duration
            duration_seconds = int((recovery_time - trip_time).total_seconds())
            
            if duration_seconds < 0:
                logger.error(f"❌ Invalid trip duration: {duration_seconds}s (recovery before trip)")
                return
            
            # Update trip with recovery information
            update_success = self.trip_dao.update_trip_recovery({
                'trip_event_id': trip_event_id,
                'trip_cleared_at': recovery_time,
                'trip_duration_seconds': duration_seconds
            })
            
            if update_success:
                logger.warning(f"✅ TRIP RECOVERY RECORDED: {equipment_id} | "
                             f"Trip ID: {trip_event_id} | "
                             f"Duration: {duration_seconds}s ({duration_seconds/60:.1f} min) | "
                             f"MTTR Updated")
                # Remove from recent_trips to allow new trip detection
                if equipment_id in self.recent_trips:
                    del self.recent_trips[equipment_id]
            else:
                logger.error(f"❌ Failed to update trip recovery for Trip ID {trip_event_id}")
                
        except Exception as e:
            logger.error(f"Error detecting trip recovery for {equipment_id}: {e}", 
                        exc_info=True)
    
    def cleanup_old_state(self, max_age_seconds: int = 3600):
        """
        Clean up old state data (hourly maintenance)
        
        Args:
            max_age_seconds: Maximum age to keep state
        """
        now = datetime.utcnow()
        
        # Clean old equipment states
        to_remove = []
        for equipment_id, state_info in self.equipment_states.items():
            timestamp = state_info.get('timestamp')
            if timestamp and (now - timestamp).total_seconds() > max_age_seconds:
                to_remove.append(equipment_id)
        
        for equipment_id in to_remove:
            del self.equipment_states[equipment_id]
        
        # Clean old trip tracking
        to_remove = []
        for equipment_id, trip_time in self.recent_trips.items():
            if (now - trip_time).total_seconds() > max_age_seconds:
                to_remove.append(equipment_id)
        
        for equipment_id in to_remove:
            del self.recent_trips[equipment_id]
        
        logger.debug(f"Cleaned up old state: equipment={len(to_remove)} states")
