"""
Equipment Monitor
Tracks equipment state transitions and provides historical context
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import deque

logger = logging.getLogger(__name__)


class EquipmentMonitor:
    """
    Equipment state monitoring and history tracking
    
    Provides:
    - Real-time equipment state tracking
    - State transition history
    - Run time calculations
    - State pattern detection
    """
    
    def __init__(self, max_history_size: int = 100):
        """
        Initialize equipment monitor
        
        Args:
            max_history_size: Maximum state transitions to keep in memory
        """
        self.max_history_size = max_history_size
        
        # Current state: equipment_id → state_info
        self.current_states: Dict[str, Dict] = {}
        
        # State history: equipment_id → deque of transitions
        self.state_history: Dict[str, deque] = {}
        
        # Run time tracking: equipment_id → start_time
        self.run_start_times: Dict[str, datetime] = {}
        
        logger.info(f"Equipment Monitor initialized: max_history={max_history_size}")
    
    def update_state(self, equipment_id: str, new_state: str, 
                     timestamp: datetime, metadata: Optional[Dict] = None):
        """
        Update equipment state
        
        Args:
            equipment_id: Equipment identifier
            new_state: New state (RUNNING, STOPPED, STARTING, etc.)
            timestamp: State change timestamp
            metadata: Optional metadata dictionary
        """
        # Get previous state
        prev_state_info = self.current_states.get(equipment_id)
        prev_state = prev_state_info.get('state') if prev_state_info else None
        
        # Only update if state changed
        if prev_state == new_state:
            return
        
        # Calculate duration of previous state
        duration_seconds = 0
        if prev_state_info:
            prev_timestamp = prev_state_info.get('timestamp')
            if prev_timestamp:
                duration_seconds = (timestamp - prev_timestamp).total_seconds()
        
        # Update current state
        self.current_states[equipment_id] = {
            'state': new_state,
            'timestamp': timestamp,
            'previous_state': prev_state,
            'metadata': metadata or {}
        }
        
        # Add to history
        if equipment_id not in self.state_history:
            self.state_history[equipment_id] = deque(maxlen=self.max_history_size)
        
        self.state_history[equipment_id].append({
            'state': new_state,
            'previous_state': prev_state,
            'timestamp': timestamp,
            'duration_seconds': duration_seconds,
            'metadata': metadata or {}
        })
        
        # Track run time
        if new_state == 'RUNNING':
            self.run_start_times[equipment_id] = timestamp
        elif new_state == 'STOPPED' and equipment_id in self.run_start_times:
            del self.run_start_times[equipment_id]
        
        logger.debug(f"Equipment state updated: {equipment_id} "
                    f"{prev_state or 'UNKNOWN'} → {new_state} "
                    f"(duration: {duration_seconds:.1f}s)")
    
    def get_current_state(self, equipment_id: str) -> Optional[str]:
        """
        Get current equipment state
        
        Args:
            equipment_id: Equipment identifier
            
        Returns:
            Current state or None
        """
        state_info = self.current_states.get(equipment_id)
        return state_info.get('state') if state_info else None
    
    def get_state_info(self, equipment_id: str) -> Optional[Dict]:
        """
        Get detailed current state information
        
        Args:
            equipment_id: Equipment identifier
            
        Returns:
            State info dictionary or None
        """
        return self.current_states.get(equipment_id)
    
    def get_run_duration(self, equipment_id: str) -> Optional[float]:
        """
        Get current run duration in seconds
        
        Args:
            equipment_id: Equipment identifier
            
        Returns:
            Run duration in seconds or None
        """
        start_time = self.run_start_times.get(equipment_id)
        if start_time:
            return (datetime.utcnow() - start_time).total_seconds()
        return None
    
    def get_recent_transitions(self, equipment_id: str, 
                              count: int = 10) -> List[Dict]:
        """
        Get recent state transitions
        
        Args:
            equipment_id: Equipment identifier
            count: Number of transitions to retrieve
            
        Returns:
            List of transition dictionaries
        """
        history = self.state_history.get(equipment_id, deque())
        return list(history)[-count:]
    
    def get_transition_before(self, equipment_id: str, 
                             timestamp: datetime) -> Optional[Dict]:
        """
        Get state transition immediately before given timestamp
        
        Args:
            equipment_id: Equipment identifier
            timestamp: Reference timestamp
            
        Returns:
            Transition dictionary or None
        """
        history = self.state_history.get(equipment_id, deque())
        
        # Search backwards from most recent
        for transition in reversed(history):
            if transition['timestamp'] < timestamp:
                return transition
        
        return None
    
    def detect_rapid_cycling(self, equipment_id: str, 
                            window_minutes: int = 5,
                            min_transitions: int = 3) -> bool:
        """
        Detect rapid state cycling (potential issue)
        
        Args:
            equipment_id: Equipment identifier
            window_minutes: Time window to check
            min_transitions: Minimum transitions to flag
            
        Returns:
            True if rapid cycling detected
        """
        history = self.state_history.get(equipment_id, deque())
        if len(history) < min_transitions:
            return False
        
        # Check recent history
        cutoff_time = datetime.utcnow() - timedelta(minutes=window_minutes)
        recent_transitions = [
            t for t in history 
            if t['timestamp'] > cutoff_time
        ]
        
        return len(recent_transitions) >= min_transitions
    
    def get_statistics(self, equipment_id: str, 
                      hours: int = 24) -> Dict:
        """
        Get equipment statistics for time period
        
        Args:
            equipment_id: Equipment identifier
            hours: Number of hours to analyze
            
        Returns:
            Statistics dictionary
        """
        history = self.state_history.get(equipment_id, deque())
        if not history:
            return {
                'total_transitions': 0,
                'running_time_seconds': 0,
                'stopped_time_seconds': 0,
                'availability_pct': 0.0
            }
        
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        
        # Filter recent history
        recent = [t for t in history if t['timestamp'] > cutoff_time]
        
        # Calculate time in each state
        running_time = sum(
            t['duration_seconds'] 
            for t in recent 
            if t['state'] == 'RUNNING'
        )
        stopped_time = sum(
            t['duration_seconds'] 
            for t in recent 
            if t['state'] == 'STOPPED'
        )
        
        total_time = running_time + stopped_time
        availability = (running_time / total_time * 100) if total_time > 0 else 0.0
        
        return {
            'total_transitions': len(recent),
            'running_time_seconds': running_time,
            'stopped_time_seconds': stopped_time,
            'availability_pct': availability,
            'rapid_cycling_detected': self.detect_rapid_cycling(equipment_id)
        }
    
    def clear_history(self, equipment_id: str):
        """
        Clear history for equipment
        
        Args:
            equipment_id: Equipment identifier
        """
        if equipment_id in self.state_history:
            self.state_history[equipment_id].clear()
        if equipment_id in self.run_start_times:
            del self.run_start_times[equipment_id]
        
        logger.debug(f"Cleared history for equipment: {equipment_id}")
