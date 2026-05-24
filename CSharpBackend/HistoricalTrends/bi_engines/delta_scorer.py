"""
Weighted Production Delta Scorer
Performance scoring with weighted penalties for operating conditions
"""

import numpy as np
import pandas as pd
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class WeightedDeltaScorer:
    """
    Calculates weighted performance scores based on operating conditions
    Different weights applied for trips, ramps, stable operation, etc.
    """
    
    def __init__(self, config: Dict = None):
        """
        Initialize delta scorer with event weights
        
        Args:
            config: Configuration with:
                - event_weights: Dict mapping conditions to weight multipliers
                - ramp_threshold: Percentage deviation indicating ramping (default: 0.20)
        """
        config = config or {}
        
        self.event_weights = config.get('event_weights', {
            'trip': 10.0,        # High penalty for trips
            'startup': 5.0,      # High penalty during startup
            'shutdown': 5.0,     # High penalty during shutdown
            'load_ramp': 3.0,    # Medium penalty for load changes
            'low_load': 2.0,     # Medium penalty for low load
            'part_load': 1.5,    # Low-medium penalty for part load
            'stable_run': 1.0    # Baseline (no penalty)
        })
        
        self.ramp_threshold = config.get('ramp_threshold', 0.20)  # 20%
        
        logger.info(f"Delta Scorer initialized with {len(self.event_weights)} event types")
    
    def calculate_weighted_delta(
        self,
        actual: float,
        expected: float,
        metadata: Optional[Dict] = None,
        timestamp: Optional[str] = None
    ) -> Dict:
        """
        Calculate weighted delta score
        
        Args:
            actual: Actual production (MW)
            expected: Expected production (MW)
            metadata: Operating metadata (trip, startup, shutdown flags)
            timestamp: Timestamp for the data point
            
        Returns:
            Dictionary with weighted delta and performance score
        """
        # Ensure numeric types (handle string input from JSON)
        actual = float(actual) if actual is not None else 0.0
        expected = float(expected) if expected is not None else 0.001
        
        # Zero protection
        if expected == 0 or np.isnan(expected):
            expected = 0.001
        
        raw_delta = actual - expected
        
        # Identify operating condition
        condition = self._identify_condition(actual, expected, metadata or {})
        weight = self.event_weights.get(condition, 1.0)
        
        # Calculate weighted delta
        weighted_delta = raw_delta * weight
        
        # Calculate performance score (0-100)
        performance_score = self._calculate_performance_score(actual, expected, weight)
        
        return {
            'raw_delta': float(raw_delta),
            'weighted_delta': float(weighted_delta),
            'condition': condition,
            'weight': float(weight),
            'performance_score': float(performance_score),
            'timestamp': timestamp,
            'actual': float(actual),
            'expected': float(expected)
        }
    
    def _identify_condition(
        self,
        actual: float,
        expected: float,
        metadata: Dict
    ) -> str:
        """
        Identify current operating condition
        
        Args:
            actual: Actual production
            expected: Expected production
            metadata: Operating flags
            
        Returns:
            Condition name string
        """
        # Check explicit flags first
        if metadata.get('trip', False):
            return 'trip'
        if metadata.get('startup', False):
            return 'startup'
        if metadata.get('shutdown', False):
            return 'shutdown'
        
        # Zero protection
        if expected < 0.001:
            return 'shutdown'
        
        # Calculate load factor
        load_factor = actual / expected
        
        # Classify based on load factor
        if load_factor < 0.3:
            return 'low_load'
        elif load_factor < 0.7:
            return 'part_load'
        elif abs(actual - expected) > expected * self.ramp_threshold:
            return 'load_ramp'
        else:
            return 'stable_run'
    
    def _calculate_performance_score(
        self,
        actual: float,
        expected: float,
        weight: float
    ) -> float:
        """
        Calculate performance score (0-100)
        
        Args:
            actual: Actual production
            expected: Expected production
            weight: Event weight multiplier
            
        Returns:
            Performance score (0-100)
        """
        # Base efficiency percentage
        if expected > 0:
            efficiency = (actual / expected) * 100
        else:
            efficiency = 0
        
        # Weight penalty (each weight point reduces score by 10)
        weight_penalty = (weight - 1) * 10
        
        # Final score (clamped 0-100)
        score = max(0, min(100, efficiency - weight_penalty))
        
        return score
    
    def batch_calculate_scores(
        self,
        df: pd.DataFrame,
        actual_col: str,
        expected_col: str,
        metadata_cols: Dict[str, str] = None
    ) -> pd.DataFrame:
        """
        Calculate weighted scores for all rows in DataFrame
        
        Args:
            df: Input DataFrame
            actual_col: Column name for actual production
            expected_col: Column name for expected production
            metadata_cols: Mapping of metadata flag columns
            
        Returns:
            DataFrame with added score columns
        """
        logger.info(f"📊 Batch calculating weighted scores for {len(df)} rows")
        
        metadata_cols = metadata_cols or {}
        results = []
        
        for idx, row in df.iterrows():
            # Extract metadata
            metadata = {}
            for flag_name, col_name in metadata_cols.items():
                if col_name in row.index:
                    metadata[flag_name] = bool(row[col_name])
            
            # Get timestamp if available
            timestamp = row.get('Timestamp', None)
            if timestamp is not None and hasattr(timestamp, 'isoformat'):
                timestamp = timestamp.isoformat()
            
            # Calculate score
            score = self.calculate_weighted_delta(
                actual=row[actual_col],
                expected=row[expected_col],
                metadata=metadata,
                timestamp=timestamp
            )
            
            results.append(score)
        
        result_df = pd.DataFrame(results)
        logger.info(f"  ✓ Completed batch scoring")
        
        return pd.concat([df.reset_index(drop=True), result_df], axis=1)
