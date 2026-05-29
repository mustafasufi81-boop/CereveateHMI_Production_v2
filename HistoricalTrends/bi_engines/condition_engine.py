"""
Condition Scoring Engine
Scores parameters based on configurable thresholds (Green/Yellow/Red zones)
"""

import numpy as np
import pandas as pd
from typing import Dict, Optional, List
import logging

logger = logging.getLogger(__name__)


class ConditionScoringEngine:
    """
    Scores parameter conditions based on threshold zones
    Supports custom thresholds per plant/parameter
    """
    
    def __init__(self, config: Dict = None):
        """
        Initialize condition scoring engine
        
        Args:
            config: Configuration with default_thresholds:
                {
                    'parameter_name': {
                        'green': [min, max],
                        'yellow': [min, max],
                        'red': [min, max],
                        'unit': 'unit_string'
                    }
                }
        """
        config = config or {}
        
        # Default thresholds (plant-specific, should come from config)
        self.default_thresholds = config.get('default_thresholds', {
            'Vibration': {
                'green': [0, 3],
                'yellow': [3, 5],
                'red': [5, 100],
                'unit': 'mm/s'
            },
            'NOx': {
                'green': [0, 150],
                'yellow': [150, 180],
                'red': [180, 1000],
                'unit': 'PPM'
            },
            'MSPressure': {
                'green': [0, 1],
                'yellow': [1, 3],
                'red': [3, 100],
                'unit': '% dev'
            },
            'Vacuum': {
                'green': [-680, -640],
                'yellow': [-640, -620],
                'red': [-620, 0],
                'unit': 'mmHg'
            },
            'Temperature': {
                'green': [0, 550],
                'yellow': [550, 575],
                'red': [575, 1000],
                'unit': '°C'
            },
            'Efficiency': {
                'green': [35, 100],
                'yellow': [30, 35],
                'red': [0, 30],
                'unit': '%'
            }
        })
        
        logger.info(f"Condition Scoring Engine initialized with {len(self.default_thresholds)} default parameters")
    
    def score_condition(
        self,
        parameter: str,
        value: float,
        custom_thresholds: Optional[Dict] = None
    ) -> Dict:
        """
        Score a parameter value based on thresholds
        
        Args:
            parameter: Parameter name
            value: Current value
            custom_thresholds: Optional custom thresholds for this parameter
            
        Returns:
            Dictionary with score, color, status, value, unit
        """
        # Ensure numeric (handle string from JSON)
        value = float(value) if value is not None else 0.0
        
        # Use custom thresholds if provided, else default
        thresholds = custom_thresholds or self.default_thresholds.get(parameter)
        
        if not thresholds:
            return {
                'score': 50,
                'color': 'yellow',
                'status': 'Unknown',
                'value': float(value),
                'unit': 'Unknown',
                'parameter': parameter
            }
        
        # Check which zone the value falls into
        if self._in_range(value, thresholds['green']):
            score = 100
            color = 'green'
            status = 'Good'
        elif self._in_range(value, thresholds['yellow']):
            score = 50
            color = 'yellow'
            status = 'Warning'
        else:
            score = 0
            color = 'red'
            status = 'Critical'
        
        return {
            'score': int(score),
            'color': color,
            'status': status,
            'value': float(value),
            'unit': thresholds.get('unit', 'Unknown'),
            'parameter': parameter,
            'thresholds': thresholds
        }
    
    def batch_score_conditions(
        self,
        df: pd.DataFrame,
        parameter_columns: List[str],
        custom_thresholds: Optional[Dict[str, Dict]] = None
    ) -> pd.DataFrame:
        """
        Score multiple parameters for all rows in DataFrame
        
        Args:
            df: Input DataFrame
            parameter_columns: List of parameter column names to score
            custom_thresholds: Optional dict mapping parameter names to custom thresholds
            
        Returns:
            DataFrame with added score columns
        """
        logger.info(f"📊 Batch scoring {len(parameter_columns)} parameters for {len(df)} rows")
        
        custom_thresholds = custom_thresholds or {}
        
        for param in parameter_columns:
            if param not in df.columns:
                logger.warning(f"⚠️ Parameter {param} not found in DataFrame")
                continue
            
            scores = []
            colors = []
            statuses = []
            
            for idx, row in df.iterrows():
                value = row[param]
                
                if pd.isna(value):
                    scores.append(np.nan)
                    colors.append('gray')
                    statuses.append('No Data')
                    continue
                
                result = self.score_condition(
                    param,
                    value,
                    custom_thresholds.get(param)
                )
                
                scores.append(result['score'])
                colors.append(result['color'])
                statuses.append(result['status'])
            
            # Add columns to DataFrame
            df[f'{param}_score'] = scores
            df[f'{param}_color'] = colors
            df[f'{param}_status'] = statuses
        
        logger.info(f"  ✓ Completed condition scoring")
        
        return df
    
    def calculate_overall_health_score(
        self,
        scores: Dict[str, int],
        weights: Optional[Dict[str, float]] = None
    ) -> Dict:
        """
        Calculate overall plant health score from individual parameter scores
        
        Args:
            scores: Dictionary mapping parameter names to scores (0-100)
            weights: Optional weights for each parameter
            
        Returns:
            Dictionary with overall health score and rating
        """
        if not scores:
            return {'score': 0, 'rating': 'Unknown', 'breakdown': {}}
        
        # Default equal weights if not provided
        if weights is None:
            weights = {param: 1.0 for param in scores.keys()}
        
        # Normalize weights
        total_weight = sum(weights.get(param, 1.0) for param in scores.keys())
        
        weighted_sum = 0
        for param, score in scores.items():
            weight = weights.get(param, 1.0) / total_weight
            weighted_sum += score * weight
        
        overall_score = weighted_sum
        rating = self._rate_health(overall_score)
        
        return {
            'score': float(overall_score),
            'rating': rating,
            'breakdown': scores,
            'weights': weights
        }
    
    def _in_range(self, value: float, range_bounds: List[float]) -> bool:
        """Check if value is within range [min, max]"""
        return range_bounds[0] <= value <= range_bounds[1]
    
    def _rate_health(self, score: float) -> str:
        """Rate overall health based on score"""
        if score >= 90:
            return 'Excellent'
        elif score >= 75:
            return 'Good'
        elif score >= 60:
            return 'Fair'
        elif score >= 40:
            return 'Poor'
        else:
            return 'Critical'
