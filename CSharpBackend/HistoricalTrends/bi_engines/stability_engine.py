"""
Performance Stability Index Engine
Calculates stability metrics for plant performance
"""

import numpy as np
import pandas as pd
from typing import Dict, List
import logging

logger = logging.getLogger(__name__)


class StabilityIndexEngine:
    """
    Calculates performance stability index based on coefficient of variation
    Lower variation = higher stability
    """
    
    def __init__(self, config: Dict = None):
        """
        Initialize stability index engine
        
        Args:
            config: Configuration dictionary (currently unused, for future expansion)
        """
        config = config or {}
        logger.info("Stability Index Engine initialized")
    
    def calculate_stability_index(self, values: np.ndarray) -> Dict:
        """
        Calculate stability index for a series of values
        
        Args:
            values: Array of values to analyze
            
        Returns:
            Dictionary with stability metrics
        """
        if values is None or len(values) < 2:
            return self._empty_result()
        
        # Remove NaN values
        clean_values = values[~np.isnan(values)]
        
        if len(clean_values) < 2:
            return self._empty_result()
        
        # Calculate statistics
        mean = np.mean(clean_values)
        std_dev = np.std(clean_values, ddof=1)
        
        # Coefficient of variation
        if mean != 0:
            cv = std_dev / abs(mean)
        else:
            cv = 0
        
        # Stability index (1 = perfect stability, 0 = highly variable)
        stability = max(0, 1 - cv)
        
        # Rating
        rating = self._rate_stability(stability)
        
        return {
            'index': float(stability),
            'rating': rating,
            'mean': float(mean),
            'std_dev': float(std_dev),
            'coefficient_of_variation': float(cv),
            'min': float(np.min(clean_values)),
            'max': float(np.max(clean_values)),
            'range': float(np.ptp(clean_values)),
            'sample_size': int(len(clean_values))
        }
    
    def calculate_rolling_stability(
        self,
        df: pd.DataFrame,
        value_col: str,
        window_hours: int = 24,
        timestamp_col: str = 'Timestamp'
    ) -> pd.DataFrame:
        """
        Calculate rolling stability index
        
        Args:
            df: DataFrame with values
            value_col: Column to analyze
            window_hours: Rolling window size in hours
            timestamp_col: Timestamp column name
            
        Returns:
            DataFrame with rolling_stability column
        """
        logger.info(f"📊 Calculating {window_hours}h rolling stability for {value_col}")
        
        # Ensure timestamp is datetime
        if not pd.api.types.is_datetime64_any_dtype(df[timestamp_col]):
            df[timestamp_col] = pd.to_datetime(df[timestamp_col])
        
        df = df.sort_values(timestamp_col).reset_index(drop=True)
        
        rolling_stability = []
        
        for i in range(len(df)):
            current_time = df[timestamp_col].iloc[i]
            window_start = current_time - pd.Timedelta(hours=window_hours)
            
            # Filter to window
            window_df = df[(df[timestamp_col] >= window_start) & (df[timestamp_col] <= current_time)]
            
            if len(window_df) < 2:
                rolling_stability.append(np.nan)
                continue
            
            # Calculate stability for window
            values = window_df[value_col].values
            metrics = self.calculate_stability_index(values)
            
            rolling_stability.append(metrics['index'])
        
        df['rolling_stability'] = rolling_stability
        logger.info(f"  ✓ Completed rolling stability calculation")
        
        return df
    
    def _rate_stability(self, index: float) -> str:
        """Rate stability based on index value"""
        if index >= 0.95:
            return 'Excellent'
        elif index >= 0.85:
            return 'Good'
        elif index >= 0.70:
            return 'Fair'
        elif index >= 0.50:
            return 'Poor'
        else:
            return 'Unstable'
    
    def _empty_result(self) -> Dict:
        """Return empty result for invalid input"""
        return {
            'index': 0.0,
            'rating': 'Unknown',
            'mean': 0.0,
            'std_dev': 0.0,
            'coefficient_of_variation': 0.0,
            'min': 0.0,
            'max': 0.0,
            'range': 0.0,
            'sample_size': 0
        }
