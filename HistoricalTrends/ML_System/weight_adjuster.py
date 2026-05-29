"""
Weight Adjuster - Adjusts model weights based on feedback
Implements learning from prediction errors
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
from storage_manager import SmartStorageManager

logger = logging.getLogger(__name__)


class WeightAdjuster:
    """
    Adjusts model weights based on prediction errors
    Feedback loop for continuous improvement
    """
    
    def __init__(self, config):
        self.config = config
        self.storage = SmartStorageManager()
        
        self.learning_rate = config['feedback']['learning_rate']
        self.learning_rate_decay = config['feedback']['learning_rate_decay']
        self.min_learning_rate = config['feedback']['min_learning_rate']
        
        logger.info("Weight Adjuster initialized")
    
    def get_recent_errors(self, days=7):
        """Get recent prediction errors for all models"""
        try:
            # Load model performance log
            perf_log = self.storage.load('08_ModelComparison', 'model_performance_log')
            
            # Filter recent data
            cutoff_date = datetime.now() - timedelta(days=days)
            perf_log['timestamp'] = pd.to_datetime(perf_log['timestamp'])
            
            recent = perf_log[perf_log['timestamp'] >= cutoff_date]
            
            logger.info(f"Loaded {len(recent)} recent performance records")
            return recent
            
        except FileNotFoundError:
            logger.warning("No performance log found")
            return None
        except Exception as e:
            logger.error(f"Error loading errors: {e}")
            return None
    
    def calculate_weight_adjustments(self, errors_df):
        """
        Calculate weight adjustments for each model
        Models with lower error get higher weights
        """
        try:
            # Group by model
            model_errors = errors_df.groupby('model_name').agg({
                'MAE': 'mean',
                'RMSE': 'mean',
                'MAPE': 'mean',
                'R2': 'mean'
            }).reset_index()
            
            adjustments = {}
            
            for _, row in model_errors.iterrows():
                model_name = row['model_name']
                
                # Lower error = positive adjustment
                # Higher error = negative adjustment
                
                # Normalize errors (0-1 scale, inverted so low error = high score)
                mae_score = 1 / (1 + row['MAE']) if not pd.isna(row['MAE']) else 0.5
                rmse_score = 1 / (1 + row['RMSE']) if not pd.isna(row['RMSE']) else 0.5
                r2_score = row['R2'] if not pd.isna(row['R2']) else 0.5
                
                # Average performance score
                perf_score = (mae_score + rmse_score + r2_score) / 3
                
                # Weight adjustment (centered around 1.0)
                # Good models get >1, bad models get <1
                weight_adjustment = 0.5 + (perf_score * 0.5)
                
                adjustments[model_name] = {
                    'weight_multiplier': weight_adjustment,
                    'performance_score': perf_score,
                    'mae': row['MAE'],
                    'rmse': row['RMSE'],
                    'r2': row['R2']
                }
            
            return adjustments
            
        except Exception as e:
            logger.error(f"Error calculating adjustments: {e}")
            return {}
    
    def apply_weight_adjustments(self, adjustments):
        """
        Apply weight adjustments to models
        Stores new weights for future use
        """
        try:
            # Create weight adjustment record
            weight_records = []
            
            for model_name, adj in adjustments.items():
                weight_records.append({
                    'model_name': model_name,
                    'weight_multiplier': adj['weight_multiplier'],
                    'performance_score': adj['performance_score'],
                    'mae': adj['mae'],
                    'rmse': adj['rmse'],
                    'r2': adj['r2'],
                    'adjusted_at': datetime.now(),
                    'learning_rate': self.learning_rate
                })
            
            weight_df = pd.DataFrame(weight_records)
            
            # Save weight adjustments
            self.storage.save(weight_df, '03_ModelWeights', 
                            f'weight_adjustments_YYYYMMDD')
            
            logger.info(f"Applied weight adjustments for {len(adjustments)} models")
            
            # Log adjustments
            for model_name, adj in adjustments.items():
                logger.info(f"  {model_name}: weight={adj['weight_multiplier']:.3f}, "
                          f"score={adj['performance_score']:.3f}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error applying adjustments: {e}")
            return False
    
    def decay_learning_rate(self):
        """Decay learning rate over time"""
        new_rate = max(
            self.learning_rate * self.learning_rate_decay,
            self.min_learning_rate
        )
        
        if new_rate != self.learning_rate:
            logger.info(f"Learning rate decayed: {self.learning_rate:.4f} → {new_rate:.4f}")
            self.learning_rate = new_rate
            
            # Update config would go here
            # For now just log
    
    def save_feedback_signal(self, adjustments):
        """Save feedback signals for analysis"""
        try:
            feedback_records = []
            
            for model_name, adj in adjustments.items():
                feedback_records.append({
                    'model_name': model_name,
                    'feedback_signal': adj['weight_multiplier'] - 1.0,  # Deviation from neutral
                    'performance_score': adj['performance_score'],
                    'timestamp': datetime.now()
                })
            
            feedback_df = pd.DataFrame(feedback_records)
            
            self.storage.save(feedback_df, '09_FeedbackLoop', 
                            'correction_signals')
            
            logger.debug(f"Saved feedback signals for {len(adjustments)} models")
            
        except Exception as e:
            logger.error(f"Error saving feedback: {e}")
    
    def adjust_weights_from_feedback(self):
        """
        Main adjustment method
        Analyzes errors and adjusts weights
        """
        logger.info("Starting weight adjustment from feedback...")
        
        # Get recent errors
        errors_df = self.get_recent_errors(days=7)
        
        if errors_df is None or len(errors_df) == 0:
            logger.warning("No error data available for adjustment")
            return False
        
        # Calculate adjustments
        adjustments = self.calculate_weight_adjustments(errors_df)
        
        if not adjustments:
            logger.warning("Could not calculate weight adjustments")
            return False
        
        # Apply adjustments
        success = self.apply_weight_adjustments(adjustments)
        
        if success:
            # Save feedback signals
            self.save_feedback_signal(adjustments)
            
            # Decay learning rate
            self.decay_learning_rate()
        
        logger.info("Weight adjustment complete")
        return success


if __name__ == '__main__':
    # Test weight adjuster
    logging.basicConfig(level=logging.INFO)
    
    import yaml
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    adjuster = WeightAdjuster(config)
    
    print("Testing weight adjuster...")
    success = adjuster.adjust_weights_from_feedback()
    
    if success:
        print("✓ Weight adjustment successful")
    else:
        print("✗ Weight adjustment failed (may need more data)")
