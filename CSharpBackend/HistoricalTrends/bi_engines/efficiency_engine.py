"""
Efficiency-Adjusted Expected Production Engine
Adjusts baseline production based on influencing operational parameters
"""

import numpy as np
import pandas as pd
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class EfficiencyAdjustmentEngine:
    """
    Calculates efficiency-adjusted expected production based on
    current operating conditions and their impact on performance
    """
    
    def __init__(self, config: Dict = None):
        """
        Initialize efficiency adjustment engine
        
        Args:
            config: Configuration with influencing_parameters dict:
                {
                    'parameter_name': {
                        'weight': float,           # Impact weight (0-1)
                        'threshold': float,        # Nominal/threshold value
                        'unit': str,              # Unit for display
                        'direction': str          # 'higher_worse' or 'lower_worse'
                    }
                }
        """
        config = config or {}
        
        # Default configuration (plant-specific, should come from config file)
        self.influencing_parameters = config.get('influencing_parameters', {
            'Vibration': {
                'weight': 0.15,
                'threshold': 3.0,
                'unit': 'mm/s',
                'direction': 'higher_worse'
            },
            'CondenserVacuum': {
                'weight': 0.20,
                'threshold': -650,
                'unit': 'mmHg',
                'direction': 'lower_worse'
            },
            'NOx': {
                'weight': 0.10,
                'threshold': 150,
                'unit': 'PPM',
                'direction': 'higher_worse'
            },
            'CoalQuality': {
                'weight': 0.15,
                'threshold': 3500,
                'unit': 'kcal/kg',
                'direction': 'lower_worse'
            },
            'MSPressure': {
                'weight': 0.12,
                'threshold': 0.02,
                'unit': '% deviation',
                'direction': 'higher_worse'
            },
            'FeedwaterTemp': {
                'weight': 0.08,
                'threshold': 200,
                'unit': '°C',
                'direction': 'higher_worse'
            },
            'AuxPower': {
                'weight': 0.10,
                'threshold': 5,
                'unit': '% of gross',
                'direction': 'higher_worse'
            },
            'Fouling': {
                'weight': 0.10,
                'threshold': 0.05,
                'unit': 'factor',
                'direction': 'higher_worse'
            }
        })
        
        logger.info(f"Efficiency Engine initialized with {len(self.influencing_parameters)} parameters")
    
    def calculate_adjusted_expected(
        self,
        baseline_production: float,
        current_conditions: Dict[str, float]
    ) -> Dict:
        """
        Calculate efficiency-adjusted expected production
        
        Args:
            baseline_production: Baseline production value (MW)
            current_conditions: Dictionary of current parameter values
            
        Returns:
            Dictionary with adjusted production and loss breakdown
        """
        logger.info("⚙️ Calculating efficiency-adjusted expected production")
        
        # Ensure numeric types (handle string from JSON)
        baseline_production = float(baseline_production) if baseline_production is not None else 0.0
        current_conditions = {k: float(v) if v is not None else 0.0 for k, v in current_conditions.items()}
        
        total_loss_factor = 0.0
        loss_breakdown = {}
        
        # Calculate loss from each influencing parameter
        for param_name, config in self.influencing_parameters.items():
            if param_name in current_conditions and current_conditions[param_name] is not None:
                loss = self._calculate_parameter_loss(
                    param_name,
                    current_conditions[param_name],
                    config
                )
                
                total_loss_factor += loss
                
                loss_breakdown[param_name] = {
                    'loss': float(loss),
                    'percentage': float(loss * 100),
                    'current_value': float(current_conditions[param_name]),
                    'threshold': float(config['threshold']),
                    'unit': config['unit'],
                    'weight': float(config['weight'])
                }
        
        # Cap total loss at 50% (physically realistic constraint)
        total_loss_factor = min(total_loss_factor, 0.5)
        
        # Calculate adjusted expected production
        adjusted_expected = baseline_production * (1 - total_loss_factor)
        
        logger.info(f"  ✓ Baseline: {baseline_production:.2f} MW")
        logger.info(f"  ✓ Total Loss Factor: {total_loss_factor * 100:.2f}%")
        logger.info(f"  ✓ Adjusted Expected: {adjusted_expected:.2f} MW")
        
        return {
            'baseline': float(baseline_production),
            'total_loss_factor': float(total_loss_factor),
            'adjusted_expected': float(adjusted_expected),
            'loss_breakdown': loss_breakdown,
            'efficiency_percentage': float((1 - total_loss_factor) * 100)
        }
    
    def _calculate_parameter_loss(
        self,
        param_name: str,
        current_value: float,
        config: Dict
    ) -> float:
        """
        Calculate loss factor for a single parameter
        
        Args:
            param_name: Parameter name
            current_value: Current measured value
            config: Parameter configuration
            
        Returns:
            Loss factor (0.0 to 1.0)
        """
        threshold = config['threshold']
        direction = config['direction']
        weight = config['weight']
        
        # Calculate deviation based on direction
        if direction == 'lower_worse':
            # Lower values are worse (e.g., coal quality, vacuum)
            if threshold == 0:
                deviation = 0
            else:
                deviation = max(0, (threshold - current_value) / abs(threshold))
        else:  # 'higher_worse'
            # Higher values are worse (e.g., vibration, NOx)
            if threshold == 0:
                threshold = 0.001  # Avoid division by zero
            deviation = max(0, (current_value - threshold) / abs(threshold))
        
        # Cap deviation at 100%
        deviation = min(deviation, 1.0)
        
        # Apply weight
        loss = deviation * weight
        
        return loss
    
    def batch_calculate_adjustments(
        self,
        df: pd.DataFrame,
        baseline_production_col: str
    ) -> pd.DataFrame:
        """
        Calculate efficiency adjustments for all rows in DataFrame
        
        Args:
            df: DataFrame with baseline production and condition columns
            baseline_production_col: Column name for baseline production
            
        Returns:
            DataFrame with added columns: adjusted_expected, total_loss_factor
        """
        logger.info(f"⚙️ Batch calculating efficiency adjustments for {len(df)} rows")
        
        results = []
        
        for idx, row in df.iterrows():
            baseline = row[baseline_production_col]
            
            # Extract current conditions from row
            current_conditions = {}
            for param_name in self.influencing_parameters.keys():
                if param_name in row.index:
                    current_conditions[param_name] = row[param_name]
            
            # Calculate adjustment
            adjustment = self.calculate_adjusted_expected(baseline, current_conditions)
            
            results.append({
                'adjusted_expected': adjustment['adjusted_expected'],
                'total_loss_factor': adjustment['total_loss_factor'],
                'efficiency_percentage': adjustment['efficiency_percentage']
            })
        
        result_df = pd.DataFrame(results)
        logger.info(f"  ✓ Completed batch adjustments")
        
        return pd.concat([df.reset_index(drop=True), result_df], axis=1)
