"""
Causality Analyzer
Analyzes alarm-trip relationships and root cause determination
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class CausalityAnalyzer:
    """
    Analyzes causality between alarms and trips
    
    Determines:
    - Which alarm caused a trip
    - Root cause tag identification
    - Confidence scoring
    - Alarm cascades and correlations
    """
    
    def __init__(self, historian_dao):
        """
        Initialize causality analyzer
        
        Args:
            historian_dao: Historian DAO for alarm queries
        """
        self.historian_dao = historian_dao
        
        # Causality rules configuration
        self.time_window_seconds = 5  # Max time between alarm and trip
        self.cascade_window_seconds = 10  # Time window for alarm cascades
        
        logger.info("Causality Analyzer initialized")
    
    def analyze_trip_cause(self, equipment_id: str, trip_time: datetime,
                          active_alarms: List[Dict]) -> Tuple[Optional[Dict], float]:
        """
        Analyze which alarm caused the trip
        
        Args:
            equipment_id: Equipment that tripped
            trip_time: Time of trip
            active_alarms: List of active alarms
            
        Returns:
            Tuple of (initiating_alarm, confidence_score)
        """
        if not active_alarms:
            return None, 0.0
        
        # Score each alarm
        scored_alarms = []
        for alarm in active_alarms:
            score = self._calculate_causality_score(
                alarm, equipment_id, trip_time
            )
            scored_alarms.append((alarm, score))
        
        # Sort by score (highest first)
        scored_alarms.sort(key=lambda x: x[1], reverse=True)
        
        # Return highest scoring alarm
        best_alarm, confidence = scored_alarms[0]
        
        logger.debug(f"Causality analysis for {equipment_id}: "
                    f"best_alarm={best_alarm.get('event_type')}, "
                    f"confidence={confidence:.2f}")
        
        return best_alarm, confidence
    
    def _calculate_causality_score(self, alarm: Dict, equipment_id: str,
                                   trip_time: datetime) -> float:
        """
        Calculate causality score (0.0 to 1.0)
        
        Scoring factors:
        - Alarm priority (weight: 0.4)
        - Time proximity (weight: 0.3)
        - Tag relationship (weight: 0.2)
        - Alarm type (weight: 0.1)
        
        Args:
            alarm: Alarm event dictionary
            equipment_id: Equipment identifier
            trip_time: Trip timestamp
            
        Returns:
            Causality score (0.0 to 1.0)
        """
        score = 0.0
        
        # Factor 1: Alarm priority (higher = more likely cause)
        priority = alarm.get('alarm_priority', 3)
        priority_score = (priority / 5.0) * 0.4
        score += priority_score
        
        # Factor 2: Time proximity (closer = more likely)
        alarm_time = alarm.get('time')
        if alarm_time:
            time_diff = abs((trip_time - alarm_time).total_seconds())
            # Exponential decay: 1.0 at 0s, 0.5 at 2s, ~0.0 at 5s
            time_score = max(0.0, 1.0 - (time_diff / self.time_window_seconds)) * 0.3
            score += time_score
        
        # Factor 3: Tag relationship (same equipment = more likely)
        alarm_tag = alarm.get('tag_id', '')
        if equipment_id.replace('_', '').lower() in alarm_tag.replace('_', '').lower():
            score += 0.2
        
        # Factor 4: Alarm type (critical types = more likely)
        alarm_type = alarm.get('event_type', '')
        critical_types = ['HIGH_HIGH', 'EMERGENCY', 'CRITICAL', 'TRIP']
        if any(ct in alarm_type for ct in critical_types):
            score += 0.1
        
        return min(1.0, score)
    
    def identify_root_cause(self, alarm: Dict, 
                           all_alarms: List[Dict]) -> Optional[str]:
        """
        Identify root cause tag from alarm cascade
        
        Args:
            alarm: Primary alarm
            all_alarms: All alarms in time window
            
        Returns:
            Root cause tag ID or None
        """
        # If only one alarm, it's the root cause
        if len(all_alarms) <= 1:
            return alarm.get('tag_id')
        
        # Build alarm timeline
        timeline = sorted(all_alarms, key=lambda a: a.get('time', datetime.min))
        
        # First alarm in cascade is likely root cause
        if timeline:
            root_alarm = timeline[0]
            return root_alarm.get('tag_id')
        
        return alarm.get('tag_id')
    
    def detect_alarm_cascade(self, alarms: List[Dict],
                            window_seconds: Optional[int] = None) -> List[List[Dict]]:
        """
        Detect alarm cascades (one failure causing multiple alarms)
        
        Args:
            alarms: List of alarms to analyze
            window_seconds: Time window for cascade (default: use class setting)
            
        Returns:
            List of alarm cascades (each cascade is a list of alarms)
        """
        if not alarms:
            return []
        
        window = window_seconds or self.cascade_window_seconds
        
        # Sort alarms by time
        sorted_alarms = sorted(alarms, key=lambda a: a.get('time', datetime.min))
        
        cascades = []
        current_cascade = [sorted_alarms[0]]
        
        for i in range(1, len(sorted_alarms)):
            prev_alarm = sorted_alarms[i - 1]
            curr_alarm = sorted_alarms[i]
            
            prev_time = prev_alarm.get('time')
            curr_time = curr_alarm.get('time')
            
            if prev_time and curr_time:
                time_diff = (curr_time - prev_time).total_seconds()
                
                # If within window, add to current cascade
                if time_diff <= window:
                    current_cascade.append(curr_alarm)
                else:
                    # Start new cascade
                    cascades.append(current_cascade)
                    current_cascade = [curr_alarm]
        
        # Add last cascade
        if current_cascade:
            cascades.append(current_cascade)
        
        # Filter cascades (need at least 2 alarms)
        return [c for c in cascades if len(c) >= 2]
    
    def analyze_alarm_patterns(self, equipment_id: str,
                               hours: int = 24) -> Dict:
        """
        Analyze alarm patterns for equipment
        
        Args:
            equipment_id: Equipment identifier
            hours: Hours of history to analyze
            
        Returns:
            Pattern analysis dictionary
        """
        # TODO: Query historian_events for equipment alarms
        # For now, return placeholder
        return {
            'total_alarms': 0,
            'high_priority_count': 0,
            'most_common_type': None,
            'cascades_detected': 0
        }
    
    def generate_diagnosis_report(self, trip_event: Dict,
                                 alarms: List[Dict]) -> Dict:
        """
        Generate detailed diagnosis report
        
        Args:
            trip_event: Trip event dictionary
            alarms: Related alarms
            
        Returns:
            Diagnosis report dictionary
        """
        # Analyze alarm cascade
        cascades = self.detect_alarm_cascade(alarms)
        
        # Identify root cause
        initiating_alarm = None
        for alarm in alarms:
            if alarm.get('event_id') == trip_event.get('initiating_alarm_id'):
                initiating_alarm = alarm
                break
        
        root_cause_tag = self.identify_root_cause(
            initiating_alarm or alarms[0], alarms
        ) if alarms else None
        
        return {
            'trip_event_id': trip_event.get('trip_event_id'),
            'equipment': trip_event.get('equipment_affected'),
            'trip_time': trip_event.get('trip_time'),
            'trip_category': trip_event.get('trip_category'),
            'total_alarms': len(alarms),
            'initiating_alarm_type': initiating_alarm.get('event_type') if initiating_alarm else None,
            'root_cause_tag': root_cause_tag,
            'cascades_detected': len(cascades),
            'alarm_sequence': [
                {
                    'tag_id': a.get('tag_id'),
                    'event_type': a.get('event_type'),
                    'time': a.get('time')
                }
                for a in sorted(alarms, key=lambda x: x.get('time', datetime.min))
            ]
        }
