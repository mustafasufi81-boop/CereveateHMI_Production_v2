"""
Historical Data Loader for ML Training
Loads parquet data from Nov 2024 - Jun 2025 for immediate model training
"""
import sys
import os

# Set UTF-8 encoding
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

sys.path.insert(0, './ML_System')
sys.path.insert(0, '.')

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from parquet_service import ParquetDataService
from config_reader import ConfigReader

# ML System imports
from ML_System.storage_manager import SmartStorageManager
from ML_System.parameter_discovery import ParameterDiscovery
from ML_System.model_trainer import ModelTrainer
from ML_System.model_registry import ModelRegistry
import yaml

def load_ml_config():
    """Load ML system config"""
    with open('ML_System/config.yaml', 'r') as f:
        return yaml.safe_load(f)

def load_historical_data():
    """Load all historical parquet data from Nov 2024 - Jun 2025"""
    logger.info("=" * 80)
    logger.info("LOADING HISTORICAL DATA (Nov 2024 - Jun 2025)")
    logger.info("=" * 80)
    
    # Initialize parquet service
    config = ConfigReader()
    data_dir = config.get_data_directory()
    parquet_service = ParquetDataService(data_dir)
    
    # Date range
    start_date = datetime(2024, 11, 1, 0, 0, 0)
    end_date = datetime(2025, 6, 30, 23, 59, 59)
    
    logger.info(f"Loading data from: {start_date.date()} to {end_date.date()}")
    
    # Load all data
    df = parquet_service.read_parquet_data(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        tags=None  # All tags
    )
    
    if df is None or len(df) == 0:
        logger.error("No data loaded!")
        return None
    
    logger.info(f"✓ Loaded {len(df):,} rows")
    logger.info(f"✓ Columns: {len(df.columns)} tags")
    logger.info(f"✓ Date range: {df['Timestamp'].min()} to {df['Timestamp'].max()}")
    
    # Show column info
    logger.info("\nColumns found:")
    for col in df.columns[:10]:  # First 10
        non_null = df[col].notna().sum()
        pct = (non_null / len(df)) * 100
        logger.info(f"  {col}: {non_null:,} values ({pct:.1f}% available)")
    
    if len(df.columns) > 10:
        logger.info(f"  ... and {len(df.columns) - 10} more columns")
    
    return df

def save_to_ml_format(df, storage):
    """Save data in ML system format"""
    logger.info("\n" + "=" * 80)
    logger.info("CONVERTING TO ML FORMAT")
    logger.info("=" * 80)
    
    # Rename timestamp column if needed
    if 'Timestamp' in df.columns:
        df = df.rename(columns={'Timestamp': 'timestamp'})
    
    # Convert all numeric columns
    for col in df.columns:
        if col != 'timestamp':
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # Split by day and save
    df['date'] = pd.to_datetime(df['timestamp']).dt.date
    unique_dates = df['date'].unique()
    
    logger.info(f"Saving {len(unique_dates)} days of data...")
    
    saved_count = 0
    for i, date in enumerate(unique_dates):
        day_data = df[df['date'] == date].copy()
        day_data = day_data.drop(columns=['date'])
        day_data = day_data.reset_index(drop=True)
        
        if len(day_data) > 0:
            filename = f"raw_data_{date.strftime('%Y%m%d')}"
            
            # Extra validation
            assert isinstance(day_data, pd.DataFrame), f"Not a DataFrame: {type(day_data)}"
            
            try:
                storage.save(day_data, '01_RawData', filename)
                saved_count += 1
                
                if (saved_count) % 10 == 0:
                    logger.info(f"  Saved {saved_count}/{len(unique_dates)} days...")
            except Exception as e:
                logger.error(f"Failed to save {date}: {e}")
                logger.error(f"Data type: {type(day_data)}, shape: {day_data.shape}")
                raise
            
            if saved_count % 30 == 0:
                logger.info(f"  Saved {saved_count}/{len(unique_dates)} days...")
    
    logger.info(f"✓ Saved {saved_count} daily files to ML_System/Data/01_RawData/")
    return saved_count

def discover_parameters(config, storage):
    """Discover important parameters"""
    logger.info("\n" + "=" * 80)
    logger.info("DISCOVERING IMPORTANT PARAMETERS")
    logger.info("=" * 80)
    
    discoverer = ParameterDiscovery(config)
    
    # OVERRIDE discover_and_rank to use all data
    # Monkey patch the load_recent_data to return all data
    original_load = discoverer.load_recent_data
    
    def load_all_data(days=30):
        """Load ALL available data regardless of dates"""
        try:
            files = storage.list_files('01_RawData')
            if not files:
                logger.warning("No raw data files found")
                return None
            
            dfs = []
            for f in files:
                try:
                    df = storage.load('01_RawData', f.stem)
                    dfs.append(df)
                except Exception as e:
                    logger.debug(f"Skipping file {f}: {e}")
            
            if not dfs:
                return None
            
            combined = pd.concat(dfs, ignore_index=True)
            logger.info(f"Loaded {len(combined)} rows from {len(dfs)} files for discovery")
            return combined
        except Exception as e:
            logger.error(f"Error loading data: {e}")
            return None
    
    # Replace the method
    discoverer.load_recent_data = load_all_data
    
    # Run discovery
    success = discoverer.discover_and_rank()
    
    if success:
        logger.info("✓ Parameter discovery complete")
        return True
    else:
        logger.error("Parameter discovery failed")
        return False

def train_models(config, storage):
    """Train all ML models"""
    logger.info("\n" + "=" * 80)
    logger.info("TRAINING ALL MODELS")
    logger.info("=" * 80)
    
    trainer = ModelTrainer(config)
    
    # Check data
    if not trainer.has_sufficient_data():
        logger.error("Insufficient data for training")
        return False
    
    # Train all models
    success = trainer.train_all_models()
    
    if success:
        logger.info("✓ Model training complete")
        return True
    else:
        logger.error("Model training failed")
        return False

def show_results(storage):
    """Display training results"""
    logger.info("\n" + "=" * 80)
    logger.info("TRAINING RESULTS")
    logger.info("=" * 80)
    
    try:
        # Load performance comparison
        comparison = storage.load('08_ModelComparison', 'performance_comparison')
        
        logger.info("\nModel Performance:")
        logger.info("-" * 80)
        logger.info(f"{'Model':<25} {'MAE':<10} {'RMSE':<10} {'R²':<10} {'MAPE':<10}")
        logger.info("-" * 80)
        
        for _, row in comparison.iterrows():
            logger.info(f"{row['model_name']:<25} {row['MAE']:<10.3f} {row['RMSE']:<10.3f} {row['R2']:<10.3f} {row['MAPE']:<10.2f}%")
        
        # Find best model
        best_idx = comparison['MAE'].idxmin()
        best_model = comparison.loc[best_idx]
        
        logger.info("\n" + "=" * 80)
        logger.info(f"🏆 BEST MODEL: {best_model['model_name']}")
        logger.info(f"   MAE: {best_model['MAE']:.3f} MW")
        logger.info(f"   RMSE: {best_model['RMSE']:.3f} MW")
        logger.info(f"   R²: {best_model['R2']:.3f}")
        logger.info(f"   MAPE: {best_model['MAPE']:.2f}%")
        logger.info("=" * 80)
        
        return True
        
    except Exception as e:
        logger.error(f"Could not load results: {e}")
        return False

def main():
    """Main execution"""
    logger.info("=" * 80)
    logger.info("ML HISTORICAL DATA TRAINING SCRIPT")
    logger.info("=" * 80)
    
    # Load config
    ml_config = load_ml_config()
    storage = SmartStorageManager()
    
    # Step 1: Load historical data
    df = load_historical_data()
    if df is None:
        logger.error("Failed to load historical data")
        return
    
    # Step 2: Save in ML format
    saved = save_to_ml_format(df, storage)
    if saved == 0:
        logger.error("Failed to save data")
        return
    
    # Step 3: Discover parameters
    if not discover_parameters(ml_config, storage):
        logger.error("Parameter discovery failed")
        return
    
    # Step 4: Train models
    if not train_models(ml_config, storage):
        logger.error("Model training failed")
        return
    
    # Step 5: Show results
    show_results(storage)
    
    logger.info("\n" + "=" * 80)
    logger.info("✓ TRAINING COMPLETE!")
    logger.info("=" * 80)
    logger.info("\nModel files saved to: ML_System/Models/")
    logger.info("Performance logs saved to: ML_System/Data/08_ModelComparison/")

if __name__ == '__main__':
    main()
