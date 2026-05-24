"""
Simple Baseline Calculator for Power Plant Performance
Calculates average load for selected time period - Industry Standard KPI
"""

import numpy as np
import pandas as pd
from datetime import datetime
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class AdaptiveBaselineEngine:
    """
    Simple baseline calculator - calculates average load for any time period
    """
    
    def __init__(self, config: Dict = None):
        """
        Initialize baseline engine
        
        Args:
            config: Configuration dictionary with:
                - min_data_points: Minimum samples required (default: 50)
        """
        config = config or {}
        self.min_data_points = config.get('min_data_points', 50)
        
        logger.info(f"Baseline Engine initialized - Simple Average Method")
    
    def calculate_adaptive_baseline(self, df: pd.DataFrame, tag: str) -> Optional[Dict]:
        """
        Calculate baseline (simple average) for selected time period
        
        Args:
            df: DataFrame with Timestamp and tag columns
            tag: Column name to calculate baseline for
            
        Returns:
            Dictionary with baseline statistics or None if insufficient data
        """
        logger.info(f"📊 Calculating baseline for {tag}")
        
        # Convert Timestamp to datetime if it's not already
        if 'Timestamp' in df.columns and not pd.api.types.is_datetime64_any_dtype(df['Timestamp']):
            df['Timestamp'] = pd.to_datetime(df['Timestamp'])
        
        # Use ALL data provided by user - exactly what they selected
        if len(df) < self.min_data_points:
            logger.warning(f"⚠️ Insufficient data: {len(df)}/{self.min_data_points}")
            return None
        
        # Extract values (remove only nulls)
        values = df[tag].dropna().values
        
        if len(values) == 0:
            return None
        
        # Log data statistics
        logger.info(f"  Data points: {len(values)}")
        logger.info(f"  Min value: {np.min(values):.2f}")
        logger.info(f"  Max value: {np.max(values):.2f}")
        logger.info(f"  Average (baseline): {np.mean(values):.2f}")
        
        # Calculate date range
        date_range_days = (df['Timestamp'].max() - df['Timestamp'].min()).days
        
        # SIMPLE AVERAGE - Industry Standard
        baseline_value = float(np.mean(values))
        min_value = float(np.min(values))
        max_value = float(np.max(values))
        std_dev = float(np.std(values, ddof=1))
        
        baseline = {
            'value': baseline_value,
            'min': min_value,
            'max': max_value,
            'std_dev': std_dev,
            'sample_size': int(len(values)),
            'calculated_at': datetime.now().isoformat(),
            'method': 'average',
            'window_days': date_range_days,
            'date_from': df['Timestamp'].min().isoformat(),
            'date_to': df['Timestamp'].max().isoformat()
        }
        
        logger.info(f"  ✓ Baseline: {baseline['value']:.2f} MW (n={baseline['sample_size']})")
        
        return baseline
