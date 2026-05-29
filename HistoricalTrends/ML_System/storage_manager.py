"""
Intelligent Data Storage Manager
Handles CSV (testing) and Parquet (production) transparently
"""

import pandas as pd
import yaml
from pathlib import Path
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class SmartStorageManager:
    """
    Intelligent storage that switches between CSV and Parquet
    based on config - NO hardcoding!
    """
    
    def __init__(self, config_path='ML_System/config.yaml'):
        """Initialize with configuration"""
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        self.testing_mode = self.config['storage']['testing_mode']
        self.testing_format = self.config['storage']['testing_format']
        self.production_format = self.config['storage']['production_format']
        self.compression = self.config['storage']['compression']
        
        # Create base directories
        self.base_path = Path(self.config['storage']['base_path'])
        self.models_path = Path(self.config['storage']['models_path'])
        self.logs_path = Path(self.config['storage']['logs_path'])
        
        self._create_directories()
        
        logger.info(f"Storage initialized: {'CSV (TESTING)' if self.testing_mode else 'PARQUET (PRODUCTION)'}")
    
    def _create_directories(self):
        """Create all required directories"""
        dirs = [
            self.base_path / '01_RawData',
            self.base_path / '02_DiscoveredParameters',
            self.base_path / '03_ModelWeights',
            self.base_path / '04_Predictions',
            self.base_path / '05_ActualResults',
            self.base_path / '06_PredictionErrors',
            self.base_path / '07_OptimizationExperiments',
            self.base_path / '08_ModelComparison',
            self.base_path / '09_FeedbackLoop',
            self.models_path,
            self.logs_path
        ]
        
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Created {len(dirs)} data directories")
    
    def save(self, dataframe, category, filename_base):
        """
        Save dataframe intelligently
        
        Args:
            dataframe: pandas DataFrame to save
            category: '01_RawData', '02_DiscoveredParameters', etc.
            filename_base: base name without extension
        """
        if not isinstance(dataframe, pd.DataFrame):
            raise ValueError("Data must be a pandas DataFrame")
        
        # Add timestamp if not in filename
        if 'YYYYMMDD' in filename_base:
            filename_base = filename_base.replace('YYYYMMDD', datetime.now().strftime('%Y%m%d'))
        
        # Determine file format
        if self.testing_mode:
            ext = '.csv'
            filepath = self.base_path / category / f"{filename_base}{ext}"
            dataframe.to_csv(filepath, index=False)
            logger.debug(f"Saved CSV: {filepath}")
        else:
            ext = '.parquet'
            filepath = self.base_path / category / f"{filename_base}{ext}"
            dataframe.to_parquet(
                filepath,
                engine='pyarrow',
                compression=self.compression,
                index=False
            )
            logger.debug(f"Saved Parquet: {filepath}")
        
        return filepath
    
    def load(self, category, filename_base):
        """
        Load dataframe intelligently
        
        Args:
            category: '01_RawData', '02_DiscoveredParameters', etc.
            filename_base: base name without extension
        """
        # Handle timestamp in filename
        if 'YYYYMMDD' in filename_base:
            filename_base = filename_base.replace('YYYYMMDD', datetime.now().strftime('%Y%m%d'))
        
        # Try both formats (in case switching between modes)
        for ext in ['.csv', '.parquet']:
            filepath = self.base_path / category / f"{filename_base}{ext}"
            if filepath.exists():
                if ext == '.csv':
                    df = pd.read_csv(filepath)
                    logger.debug(f"Loaded CSV: {filepath}")
                else:
                    df = pd.read_parquet(filepath, engine='pyarrow')
                    logger.debug(f"Loaded Parquet: {filepath}")
                return df
        
        raise FileNotFoundError(f"File not found: {filename_base} in {category}")
    
    def list_files(self, category, pattern='*'):
        """
        List all files in a category
        
        Args:
            category: Directory to search
            pattern: Glob pattern (default: all files)
        """
        directory = self.base_path / category
        
        if self.testing_mode:
            files = list(directory.glob(f"{pattern}.csv"))
        else:
            files = list(directory.glob(f"{pattern}.parquet"))
        
        return sorted(files)
    
    def save_model_performance(self, model_name, metrics_dict):
        """
        Save model performance metrics
        
        Args:
            model_name: Name of the model
            metrics_dict: Dictionary of metrics
        """
        # Add metadata
        metrics_dict['model_name'] = model_name
        metrics_dict['timestamp'] = datetime.now()
        metrics_dict['testing_mode'] = self.testing_mode
        
        df = pd.DataFrame([metrics_dict])
        
        # Append to existing file or create new
        filename = 'model_performance_log'
        try:
            existing = self.load('08_ModelComparison', filename)
            df = pd.concat([existing, df], ignore_index=True)
        except FileNotFoundError:
            pass
        
        self.save(df, '08_ModelComparison', filename)
        logger.info(f"Logged performance for {model_name}: {metrics_dict}")
    
    def save_prediction(self, prediction_type, predictions_df):
        """
        Save predictions with timestamp
        
        Args:
            prediction_type: 'health', 'output', 'efficiency'
            predictions_df: DataFrame with predictions
        """
        filename = f"{prediction_type}_predictions_YYYYMMDD"
        return self.save(predictions_df, '04_Predictions', filename)
    
    def save_actual_results(self, result_type, results_df):
        """
        Save actual results for validation
        
        Args:
            result_type: 'health', 'output', 'efficiency'
            results_df: DataFrame with actual results
        """
        filename = f"actual_{result_type}_YYYYMMDD"
        return self.save(results_df, '05_ActualResults', filename)
    
    def calculate_prediction_error(self, prediction_type, date=None):
        """
        Compare predictions vs actuals and calculate error
        
        Args:
            prediction_type: 'health', 'output', 'efficiency'
            date: Date to analyze (default: today)
        """
        if date is None:
            date_str = datetime.now().strftime('%Y%m%d')
        else:
            date_str = date.strftime('%Y%m%d')
        
        try:
            # Load predictions and actuals
            pred_file = f"{prediction_type}_predictions_{date_str}"
            actual_file = f"actual_{prediction_type}_{date_str}"
            
            predictions = self.load('04_Predictions', pred_file)
            actuals = self.load('05_ActualResults', actual_file)
            
            # Merge on timestamp
            merged = pd.merge(
                predictions,
                actuals,
                on='timestamp',
                suffixes=('_pred', '_actual')
            )
            
            # Calculate errors
            value_cols = [c for c in predictions.columns if c != 'timestamp']
            
            errors = {}
            for col in value_cols:
                pred_col = f"{col}_pred"
                actual_col = f"{col}_actual"
                
                if pred_col in merged.columns and actual_col in merged.columns:
                    mae = abs(merged[pred_col] - merged[actual_col]).mean()
                    rmse = ((merged[pred_col] - merged[actual_col]) ** 2).mean() ** 0.5
                    mape = (abs((merged[actual_col] - merged[pred_col]) / merged[actual_col]) * 100).mean()
                    
                    errors[col] = {
                        'MAE': mae,
                        'RMSE': rmse,
                        'MAPE': mape
                    }
            
            # Save error analysis
            error_df = pd.DataFrame([{
                'date': date_str,
                'prediction_type': prediction_type,
                'timestamp': datetime.now(),
                **{f"{k}_{m}": v[m] for k, v in errors.items() for m in ['MAE', 'RMSE', 'MAPE']}
            }])
            
            self.save(error_df, '06_PredictionErrors', 'prediction_accuracy_log')
            
            logger.info(f"Calculated errors for {prediction_type}: {errors}")
            return errors
            
        except FileNotFoundError as e:
            logger.warning(f"Could not calculate errors: {e}")
            return None
    
    def get_best_model(self, task='health', window_days=7):
        """
        Get best performing model for a task
        
        Args:
            task: 'health', 'output', 'efficiency'
            window_days: Look back period
        """
        try:
            perf_log = self.load('08_ModelComparison', 'model_performance_log')
            
            # Filter by task and recent data
            cutoff_date = datetime.now() - pd.Timedelta(days=window_days)
            perf_log['timestamp'] = pd.to_datetime(perf_log['timestamp'])
            
            recent = perf_log[
                (perf_log['timestamp'] >= cutoff_date)
            ]
            
            if len(recent) == 0:
                logger.warning("No recent performance data found")
                return None
            
            # Find best model (lowest error or highest accuracy)
            if 'MAPE' in recent.columns:
                best = recent.loc[recent['MAPE'].idxmin()]
            elif 'accuracy' in recent.columns:
                best = recent.loc[recent['accuracy'].idxmax()]
            else:
                logger.warning("No suitable metric found")
                return None
            
            logger.info(f"Best model for {task}: {best['model_name']}")
            return best['model_name']
            
        except Exception as e:
            logger.error(f"Error getting best model: {e}")
            return None
    
    def cleanup_old_data(self):
        """Clean up old data based on retention policy"""
        retention_days = self.config['data_collection']['keep_raw_data_days']
        cutoff_date = datetime.now() - pd.Timedelta(days=retention_days)
        
        # Cleanup raw data
        for f in self.list_files('01_RawData'):
            # Extract date from filename
            try:
                date_str = f.stem.split('_')[-1]
                file_date = datetime.strptime(date_str, '%Y%m%d')
                
                if file_date < cutoff_date:
                    f.unlink()
                    logger.info(f"Deleted old file: {f}")
            except:
                continue
    
    def get_storage_stats(self):
        """Get storage statistics"""
        stats = {
            'mode': 'CSV (Testing)' if self.testing_mode else 'Parquet (Production)',
            'categories': {}
        }
        
        categories = [
            '01_RawData',
            '02_DiscoveredParameters',
            '03_ModelWeights',
            '04_Predictions',
            '05_ActualResults',
            '06_PredictionErrors',
            '07_OptimizationExperiments',
            '08_ModelComparison',
            '09_FeedbackLoop'
        ]
        
        for cat in categories:
            files = self.list_files(cat)
            total_size = sum(f.stat().st_size for f in files)
            
            stats['categories'][cat] = {
                'file_count': len(files),
                'total_size_mb': round(total_size / (1024 * 1024), 2)
            }
        
        return stats


# Convenience functions
def get_storage():
    """Get storage manager instance"""
    return SmartStorageManager()


if __name__ == '__main__':
    # Test storage manager
    logging.basicConfig(level=logging.INFO)
    
    storage = SmartStorageManager()
    
    # Test save/load
    test_df = pd.DataFrame({
        'timestamp': pd.date_range('2024-01-01', periods=100, freq='1min'),
        'value': range(100)
    })
    
    storage.save(test_df, '01_RawData', 'test_data_YYYYMMDD')
    loaded = storage.load('01_RawData', 'test_data_YYYYMMDD')
    
    print("✓ Storage test passed")
    print(f"\nStorage stats:\n{storage.get_storage_stats()}")
