"""
Model Selector - Selects best performing model
Automatically chooses winner based on performance
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
from storage_manager import SmartStorageManager

logger = logging.getLogger(__name__)


class ModelSelector:
    """
    Selects best performing models
    One best model for each task (health, output, efficiency)
    """
    
    def __init__(self, config):
        self.config = config
        self.storage = SmartStorageManager()
        
        self.selection_window = config['feedback']['model_selection_window_days']
        self.min_accuracy = config['feedback']['min_accuracy_threshold']
        
        logger.info("Model Selector initialized")
    
    def get_model_performance(self, days=None):
        """Get model performance for selection period"""
        if days is None:
            days = self.selection_window
        
        try:
            # Load performance log
            perf_log = self.storage.load('08_ModelComparison', 'model_performance_log')
            
            # Filter recent data
            cutoff_date = datetime.now() - timedelta(days=days)
            perf_log['timestamp'] = pd.to_datetime(perf_log['timestamp'])
            
            recent = perf_log[perf_log['timestamp'] >= cutoff_date]
            
            logger.info(f"Loaded {len(recent)} performance records from last {days} days")
            return recent
            
        except FileNotFoundError:
            logger.warning("No performance log found")
            return None
        except Exception as e:
            logger.error(f"Error loading performance: {e}")
            return None
    
    def rank_models(self, perf_df):
        """
        Rank models by performance
        Uses multiple metrics for robust ranking
        """
        try:
            # Group by model and calculate average metrics
            model_stats = perf_df.groupby('model_name').agg({
                'MAE': ['mean', 'std', 'count'],
                'RMSE': ['mean', 'std'],
                'MAPE': ['mean', 'std'],
                'R2': ['mean', 'std']
            }).reset_index()
            
            # Flatten column names
            model_stats.columns = ['_'.join(col).strip('_') for col in model_stats.columns.values]
            
            rankings = []
            
            for _, row in model_stats.iterrows():
                model_name = row['model_name']
                
                # Calculate composite score
                # Lower error is better, higher R2 is better
                
                mae_score = 1 / (1 + row['MAE_mean']) if not pd.isna(row['MAE_mean']) else 0
                rmse_score = 1 / (1 + row['RMSE_mean']) if not pd.isna(row['RMSE_mean']) else 0
                mape_score = 1 / (1 + row['MAPE_mean']) if not pd.isna(row['MAPE_mean']) else 0
                r2_score = row['R2_mean'] if not pd.isna(row['R2_mean']) else 0
                
                # Weighted composite score
                composite_score = (
                    mae_score * 0.3 +
                    rmse_score * 0.3 +
                    mape_score * 0.2 +
                    r2_score * 0.2
                )
                
                # Penalize high variance (unstable models)
                stability_penalty = 1 / (1 + row['MAE_std']) if not pd.isna(row['MAE_std']) else 1
                
                final_score = composite_score * stability_penalty
                
                rankings.append({
                    'model_name': model_name,
                    'composite_score': final_score,
                    'mae': row['MAE_mean'],
                    'rmse': row['RMSE_mean'],
                    'mape': row['MAPE_mean'],
                    'r2': row['R2_mean'],
                    'stability': stability_penalty,
                    'prediction_count': row['MAE_count']
                })
            
            # Sort by composite score
            rankings_df = pd.DataFrame(rankings)
            rankings_df = rankings_df.sort_values('composite_score', ascending=False)
            
            return rankings_df
            
        except Exception as e:
            logger.error(f"Error ranking models: {e}")
            return None
    
    def select_best_model(self, rankings_df):
        """Select the best model from rankings"""
        if rankings_df is None or len(rankings_df) == 0:
            logger.warning("No models to select from")
            return None
        
        best = rankings_df.iloc[0]
        
        # Check minimum accuracy threshold
        if best['r2'] < self.min_accuracy:
            logger.warning(f"Best model R2 ({best['r2']:.3f}) below threshold ({self.min_accuracy})")
            return None
        
        return best
    
    def save_selection(self, best_model, rankings_df):
        """Save model selection results"""
        try:
            # Save selection record
            selection = {
                'selected_model': best_model['model_name'],
                'composite_score': best_model['composite_score'],
                'mae': best_model['mae'],
                'rmse': best_model['rmse'],
                'r2': best_model['r2'],
                'selected_at': datetime.now(),
                'competitors': len(rankings_df),
                'selection_window_days': self.selection_window
            }
            
            selection_df = pd.DataFrame([selection])
            
            # Append to selection history
            try:
                existing = self.storage.load('08_ModelComparison', 'best_model_selection')
                selection_df = pd.concat([existing, selection_df], ignore_index=True)
            except FileNotFoundError:
                pass
            
            self.storage.save(selection_df, '08_ModelComparison', 'best_model_selection')
            
            # Save full rankings
            self.storage.save(rankings_df, '08_ModelComparison', 
                            f'model_rankings_YYYYMMDD')
            
            logger.info(f"Saved model selection: {best_model['model_name']}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving selection: {e}")
            return False
    
    def select_best_models(self):
        """
        Main selection method
        Selects best model from recent performance
        """
        logger.info("Starting model selection...")
        
        # Get recent performance
        perf_df = self.get_model_performance()
        
        if perf_df is None or len(perf_df) == 0:
            logger.warning("No performance data available")
            return False
        
        # Rank all models
        rankings = self.rank_models(perf_df)
        
        if rankings is None:
            logger.error("Model ranking failed")
            return False
        
        # Select best
        best = self.select_best_model(rankings)
        
        if best is None:
            logger.warning("No suitable model found")
            return False
        
        # Log results
        logger.info("Model Selection Results:")
        logger.info(f"  Winner: {best['model_name']}")
        logger.info(f"  Composite Score: {best['composite_score']:.4f}")
        logger.info(f"  MAE: {best['mae']:.4f}")
        logger.info(f"  RMSE: {best['rmse']:.4f}")
        logger.info(f"  R²: {best['r2']:.4f}")
        
        logger.info("\nAll Rankings:")
        for i, row in rankings.head(5).iterrows():
            logger.info(f"  {i+1}. {row['model_name']}: score={row['composite_score']:.4f}, "
                       f"R²={row['r2']:.4f}")
        
        # Save selection
        success = self.save_selection(best, rankings)
        
        logger.info("Model selection complete")
        return success


if __name__ == '__main__':
    # Test model selector
    logging.basicConfig(level=logging.INFO)
    
    import yaml
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    selector = ModelSelector(config)
    
    print("Testing model selector...")
    success = selector.select_best_models()
    
    if success:
        print("✓ Model selection successful")
    else:
        print("✗ Model selection failed (may need more data)")
