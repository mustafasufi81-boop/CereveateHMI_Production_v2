"""
Historical Data Loader for ML Training
Loads existing parquet data (Nov 2024 - Jun 2025) into ML system format
This allows models to train immediately on historical data
"""

import sys
sys.path.insert(0, '.')
sys.path.insert(0, './ML_System')

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
import logging

from parquet_service import ParquetDataService
from config_reader import ConfigReader
from ML_System.storage_manager import SmartStorageManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class HistoricalDataLoader:
    """Loads historical parquet data for ML training"""
    
    def __init__(self):
        self.config = ConfigReader()
        self.data_dir = self.config.get_data_directory()
        self.parquet_service = ParquetDataService(self.data_dir)
        self.ml_storage = SmartStorageManager()
        
        logger.info(f"Historical Data Loader initialized")
        logger.info(f"Source: {self.data_dir}")
    
    def load_date_range(self, start_date, end_date, tags=None):
        """Load data for a date range"""
        logger.info(f"Loading data from {start_date} to {end_date}")
        
        try:
            data = self.parquet_service.read_parquet_data(
                start_date=start_date.isoformat() + 'T00:00:00',
                end_date=end_date.isoformat() + 'T23:59:59',
                tags=tags
            )
            
            if len(data) == 0:
                logger.warning(f"No data found for {start_date}")
                return None
            
            logger.info(f"  ✓ Loaded {len(data)} records")
            return data
            
        except Exception as e:
            logger.error(f"Failed to load {start_date}: {e}")
            return None
    
    def prepare_ml_format(self, df):
        """Convert parquet data to ML training format"""
        # Ensure timestamp column
        if 'Timestamp' not in df.columns:
            logger.warning("No Timestamp column, adding current time")
            df['Timestamp'] = datetime.now()
        
        # Convert all numeric columns to float
        for col in df.columns:
            if col != 'Timestamp':
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        return df
    
    def save_to_ml_system(self, df, date):
        """Save data in ML system format"""
        try:
            # Format: turbine_data_YYYYMMDD
            filename = f"turbine_data_{date.strftime('%Y%m%d')}"
            
            self.ml_storage.save(df, '01_RawData', filename)
            logger.info(f"  ✓ Saved to ML_System: {filename}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to save {date}: {e}")
            return False
    
    def load_historical_period(self, start_date_str, end_date_str, tags=None):
        """
        Load historical period day by day
        
        Args:
            start_date_str: Start date (YYYY-MM-DD)
            end_date_str: End date (YYYY-MM-DD)
            tags: List of tags to load (None = all available)
        """
        start_date = datetime.fromisoformat(start_date_str)
        end_date = datetime.fromisoformat(end_date_str)
        
        total_days = (end_date - start_date).days + 1
        
        logger.info("=" * 80)
        logger.info(f"HISTORICAL DATA LOADING")
        logger.info("=" * 80)
        logger.info(f"Period: {start_date_str} to {end_date_str}")
        logger.info(f"Total Days: {total_days}")
        logger.info(f"Tags: {'All available' if tags is None else len(tags)}")
        logger.info("=" * 80)
        
        success_count = 0
        fail_count = 0
        total_records = 0
        
        # Load day by day
        current_date = start_date
        while current_date <= end_date:
            logger.info(f"\nProcessing: {current_date.date()}")
            
            # Load data for this day
            df = self.load_date_range(current_date, current_date, tags)
            
            if df is not None and len(df) > 0:
                # Prepare for ML
                df = self.prepare_ml_format(df)
                
                # Save to ML system
                if self.save_to_ml_system(df, current_date):
                    success_count += 1
                    total_records += len(df)
                else:
                    fail_count += 1
            else:
                logger.warning(f"  ✗ No data for {current_date.date()}")
                fail_count += 1
            
            # Next day
            current_date += timedelta(days=1)
        
        # Summary
        logger.info("\n" + "=" * 80)
        logger.info("LOADING COMPLETE")
        logger.info("=" * 80)
        logger.info(f"Total Days Processed: {total_days}")
        logger.info(f"Successful: {success_count}")
        logger.info(f"Failed: {fail_count}")
        logger.info(f"Total Records: {total_records:,}")
        logger.info(f"Success Rate: {(success_count/total_days*100):.1f}%")
        logger.info("=" * 80)
        
        return success_count, fail_count, total_records


def main():
    """Load historical data from Nov 2024 to Jun 2025"""
    
    loader = HistoricalDataLoader()
    
    # Load historical period
    success, failed, total = loader.load_historical_period(
        start_date_str='2024-11-01',
        end_date_str='2025-06-30',
        tags=None  # Load all available tags
    )
    
    if success > 0:
        print("\n" + "=" * 80)
        print("✅ HISTORICAL DATA LOADED SUCCESSFULLY")
        print("=" * 80)
        print(f"\nData is now available in: ML_System/Data/01_RawData/")
        print(f"\nYou can now start ML training with:")
        print(f"  cd ML_System")
        print(f"  python background_process_manager.py")
        print("\nOr run specific components:")
        print(f"  python parameter_discovery.py")
        print(f"  python model_trainer.py")
        print("=" * 80)
    else:
        print("\n❌ No data loaded. Check parquet files in:", loader.data_dir)


if __name__ == '__main__':
    main()
