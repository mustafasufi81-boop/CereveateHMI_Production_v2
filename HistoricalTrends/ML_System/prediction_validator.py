"""
Prediction Validator - Compares predictions vs actual results
Calculates errors for each model separately
Feeds back to weight adjuster
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
from storage_manager import SmartStorageManager

logger = logging.getLogger(__name__)


class PredictionValidator:
    """
    Validates predictions against actual results
    Each model's accuracy logged separately
    """
    
    def __init__(self, config):
        self.config = config
        self.storage = SmartStorageManager()
        
        self.validation_delay = config['feedback']['validation_delay_hours']
        
        logger.info("Prediction Validator initialized")
    
    def get_predictions_to_validate(self):
        """
        Get predictions that are ready for validation
        (predictions made N hours ago)
        """
        try:
            # Get all prediction files
            pred_files = self.storage.list_files('04_Predictions')
            
            if not pred_files:
                logger.info("No predictions to validate")
                return []
            
            # Find predictions from validation_delay hours ago
            target_date = datetime.now() - timedelta(hours=self.validation_delay)
            target_date_str = target_date.strftime('%Y%m%d')
            
            ready_files = [f for f in pred_files if target_date_str in f.name]
            
            logger.info(f"Found {len(ready_files)} prediction files ready for validation")
            return ready_files
            
        except Exception as e:
            logger.error(f"Error getting predictions: {e}")
            return []
    
    def get_actual_results(self, date_str):
        """Get actual results for a specific date"""
        try:
            # Try to load actual results
            actual = self.storage.load('05_ActualResults', f"actual_output_{date_str}")
            return actual
            
        except FileNotFoundError:
            logger.warning(f"No actual results found for {date_str}")
            return None
        except Exception as e:
            logger.error(f"Error loading actual results: {e}")
            return None
    
    def calculate_errors(self, predictions, actuals, model_name):
        """
        Calculate error metrics for a model
        Returns dict of metrics
        """
        try:
            # Merge on timestamp
            merged = pd.merge(
                predictions,
                actuals,
                on='timestamp',
                suffixes=('_pred', '_actual')
            )
            
            if len(merged) == 0:
                logger.warning(f"No matching timestamps for {model_name}")
                return None
            
            # Find prediction and actual columns
            pred_cols = [c for c in merged.columns if c.endswith('_pred')]
            
            metrics = {}
            
            for pred_col in pred_cols:
                actual_col = pred_col.replace('_pred', '_actual')
                
                if actual_col not in merged.columns:
                    continue
                
                # Calculate errors
                errors = merged[actual_col] - merged[pred_col]
                
                mae = np.abs(errors).mean()
                rmse = np.sqrt((errors ** 2).mean())
                
                # MAPE (handle division by zero)
                mape = np.mean(np.abs(errors / np.where(merged[actual_col] != 0, 
                                                        merged[actual_col], 1))) * 100
                
                # R-squared
                ss_res = ((errors) ** 2).sum()
                ss_tot = ((merged[actual_col] - merged[actual_col].mean()) ** 2).sum()
                r2 = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0
                
                metric_name = pred_col.replace('_pred', '')
                metrics[metric_name] = {
                    'MAE': mae,
                    'RMSE': rmse,
                    'MAPE': mape,
                    'R2': r2,
                    'samples': len(merged)
                }
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error calculating errors for {model_name}: {e}")
            return None
    
    def validate_predictions(self, pred_file):
        """
        Validate a single prediction file
        """
        try:
            # Extract date from filename
            date_str = None
            for part in pred_file.stem.split('_'):
                if len(part) == 8 and part.isdigit():
                    date_str = part
                    break
            
            if not date_str:
                logger.warning(f"Could not extract date from {pred_file}")
                return False
            
            # Load predictions
            predictions = self.storage.load('04_Predictions', pred_file.stem)
            
            # Get model name from predictions
            if 'model_name' not in predictions.columns:
                logger.warning(f"No model_name column in {pred_file}")
                return False
            
            # Get actual results
            actuals = self.get_actual_results(date_str)
            
            if actuals is None:
                logger.warning(f"No actuals available for {date_str}")
                return False
            
            # Validate each model's predictions
            for model_name in predictions['model_name'].unique():
                model_preds = predictions[predictions['model_name'] == model_name]
                
                # Calculate errors
                metrics = self.calculate_errors(model_preds, actuals, model_name)
                
                if metrics:
                    # Save performance for this model
                    for metric_type, values in metrics.items():
                        perf_dict = {
                            'model_name': model_name,
                            'metric_type': metric_type,
                            'validation_date': date_str,
                            **values
                        }
                        
                        self.storage.save_model_performance(model_name, perf_dict)
                    
                    logger.info(f"Validated {model_name} for {date_str}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating {pred_file}: {e}")
            return False
    
    def validate_all_predictions(self):
        """
        Main validation method
        Validates all ready predictions
        """
        logger.info("Starting prediction validation...")
        
        # Get predictions ready for validation
        ready_files = self.get_predictions_to_validate()
        
        if not ready_files:
            logger.info("No predictions ready for validation")
            return True
        
        # Validate each file
        validated_count = 0
        for pred_file in ready_files:
            if self.validate_predictions(pred_file):
                validated_count += 1
        
        logger.info(f"Validated {validated_count} / {len(ready_files)} prediction files")
        return True


if __name__ == '__main__':
    # Test prediction validator
    logging.basicConfig(level=logging.INFO)
    
    import yaml
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    validator = PredictionValidator(config)
    
    print("Testing prediction validator...")
    success = validator.validate_all_predictions()
    
    if success:
        print("✓ Validation complete")
    else:
        print("✗ Validation failed")
