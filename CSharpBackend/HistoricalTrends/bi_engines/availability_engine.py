"""
Cumulative Availability-Based Production Calculator
Calculates availability metrics and cumulative production
"""

import numpy as np
import pandas as pd
from datetime import datetime
from typing import Dict, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class AvailabilityProductionEngine:
    """
    Calculates availability-corrected production metrics
    Tracks breakdown time, low load operation, and cumulative production
    """
    
    def __init__(self, config: Dict = None):
        """
        Initialize availability engine
        
        Args:
            config: Configuration with:
                - low_load_threshold: Fraction of rated capacity (default: 0.3)
        """
        config = config or {}
        self.low_load_threshold = config.get('low_load_threshold', 0.3)
        
        logger.info(f"Availability Engine initialized: low_load={self.low_load_threshold * 100}%")
    
    def calculate_availability_production(
        self,
        df: pd.DataFrame,
        load_col: str,
        rated_capacity: float,
        timestamp_col: str = 'Timestamp',
        trip_col: Optional[str] = None
    ) -> Dict:
        """
        Calculate availability-based production metrics
        
        Args:
            df: DataFrame with production data
            load_col: Column name for load/production (MW)
            rated_capacity: Rated capacity of the plant (MW)
            timestamp_col: Column name for timestamps
            trip_col: Optional column indicating trip events
            
        Returns:
            Dictionary with availability metrics and cumulative production
        """
        logger.info("📈 Calculating availability-based production")
        
        if len(df) < 2:
            logger.error("❌ Insufficient data points")
            return {}
        
        # Ensure timestamp is datetime
        if not pd.api.types.is_datetime64_any_dtype(df[timestamp_col]):
            df[timestamp_col] = pd.to_datetime(df[timestamp_col])
        
        # Sort by timestamp
        df = df.sort_values(timestamp_col).reset_index(drop=True)
        
        # Calculate time range
        total_seconds = (df[timestamp_col].iloc[-1] - df[timestamp_col].iloc[0]).total_seconds()
        
        # Initialize counters
        available_seconds = 0
        breakdown_seconds = 0
        low_load_seconds = 0
        cumulative_production = 0.0  # MWh
        
        # Process each interval
        for i in range(len(df) - 1):
            current = df.iloc[i]
            next_point = df.iloc[i + 1]
            
            # Calculate duration (seconds)
            duration = (next_point[timestamp_col] - current[timestamp_col]).total_seconds()
            
            # Get load value
            load = current[load_col] if not pd.isna(current[load_col]) else 0
            
            # Check trip flag if available
            is_trip = False
            if trip_col and trip_col in current.index:
                is_trip = bool(current[trip_col])
            
            # Classify time period
            if load == 0 or is_trip:
                breakdown_seconds += duration
            elif load < rated_capacity * self.low_load_threshold:
                low_load_seconds += duration
                # Still running, so it's available
                available_seconds += duration
            else:
                available_seconds += duration
            
            # Cumulative production (MWh = MW * hours)
            cumulative_production += (load * duration) / 3600
        
        # Average load - CALCULATE THIS FIRST
        average_load = (cumulative_production / (total_seconds / 3600)) if total_seconds > 0 else 0
        
        # Calculate percentages
        if total_seconds > 0:
            # SIMPLE AVAILABILITY = Running Time / Total Time * 100
            # Running Time = Total Time - Breakdown Time
            running_seconds = total_seconds - breakdown_seconds
            availability = (running_seconds / total_seconds) * 100
            
            # UTILIZATION = How much of rated capacity we used
            utilization_factor = (average_load / rated_capacity) * 100 if rated_capacity > 0 else 0
        else:
            availability = 0
            utilization_factor = 0
        
        logger.info(f"  ✓ Total Time: {total_seconds / 3600:.2f} hours")
        logger.info(f"  ✓ Available Time: {available_seconds / 3600:.2f} hours")
        logger.info(f"  ✓ Breakdown Time: {breakdown_seconds / 3600:.2f} hours")
        logger.info(f"  ✓ Availability: {availability:.2f}%")
        logger.info(f"  ✓ Cumulative Production: {cumulative_production:.2f} MWh")
        
        return {
            'total_seconds': float(total_seconds),
            'total_hours': float(total_seconds / 3600),
            'available_seconds': float(available_seconds),
            'available_hours': float(available_seconds / 3600),
            'breakdown_seconds': float(breakdown_seconds),
            'breakdown_hours': float(breakdown_seconds / 3600),
            'low_load_seconds': float(low_load_seconds),
            'low_load_hours': float(low_load_seconds / 3600),
            'availability': float(availability),  # Percentage 0-100
            'utilizationFactor': float(utilization_factor / 100),  # Decimal 0-1 for UI
            'cumulativeProduction': float(cumulative_production),  # MWh
            'averageLoad': float(average_load),  # MW
            'ratedCapacity': float(rated_capacity),  # MW
            'capacityFactor': float((cumulative_production / (rated_capacity * total_seconds / 3600)) / 100) if total_seconds > 0 else 0  # Decimal 0-1 for UI
        }
    
    def calculate_rolling_availability(
        self,
        df: pd.DataFrame,
        load_col: str,
        rated_capacity: float,
        window_hours: int = 24,
        timestamp_col: str = 'Timestamp'
    ) -> pd.DataFrame:
        """
        Calculate rolling availability for each timestamp
        
        Args:
            df: DataFrame with production data
            load_col: Column name for load
            rated_capacity: Rated capacity
            window_hours: Rolling window size in hours
            timestamp_col: Timestamp column name
            
        Returns:
            DataFrame with rolling availability column
        """
        logger.info(f"📊 Calculating {window_hours}h rolling availability")
        
        # Ensure timestamp is datetime
        if not pd.api.types.is_datetime64_any_dtype(df[timestamp_col]):
            df[timestamp_col] = pd.to_datetime(df[timestamp_col])
        
        df = df.sort_values(timestamp_col).reset_index(drop=True)
        
        rolling_availability = []
        
        for i in range(len(df)):
            current_time = df[timestamp_col].iloc[i]
            window_start = current_time - pd.Timedelta(hours=window_hours)
            
            # Filter to window
            window_df = df[(df[timestamp_col] >= window_start) & (df[timestamp_col] <= current_time)]
            
            if len(window_df) < 2:
                rolling_availability.append(np.nan)
                continue
            
            # Calculate availability for window
            metrics = self.calculate_availability_production(
                window_df,
                load_col,
                rated_capacity,
                timestamp_col
            )
            
            rolling_availability.append(metrics['availability'])
        
        df['rolling_availability'] = rolling_availability
        logger.info(f"  ✓ Completed rolling availability calculation")
        
        return df
