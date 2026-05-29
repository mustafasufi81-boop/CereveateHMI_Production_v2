"""
Historical Data Loader - Converts ANY CSV/Parquet to ML Training Format
Allows adding historical data anytime for continuous model improvement
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import logging
from storage_manager import SmartStorageManager
import yaml

logger = logging.getLogger(__name__)


class HistoricalDataLoader:
    """
    Loads historical data from any source and prepares for ML training
    Supports: CSV, Parquet, Excel, Database dumps
    """
    
    def __init__(self, config_path='ML_System/config.yaml'):
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        self.storage = SmartStorageManager()
        self.target_column = self.config['models']['training']['target_column']
        
        logger.info("Historical Data Loader initialized")
    
    def load_from_parquet(self, source_path, start_date=None, end_date=None):
        """
        Load data from parquet files
        
        Args:
            source_path: Directory containing parquet files or single file path
            start_date: Optional start date filter (YYYY-MM-DD)
            end_date: Optional end date filter (YYYY-MM-DD)
        
        Returns:
            DataFrame with loaded data
        """
        logger.info(f"Loading parquet data from: {source_path}")
        
        source = Path(source_path)
        
        if source.is_file():
            # Single file
            df = pd.read_parquet(source)
            logger.info(f"Loaded {len(df)} rows from {source.name}")
        else:
            # Directory - load all parquet files
            files = list(source.glob("*.parquet"))
            
            if not files:
                logger.error(f"No parquet files found in {source}")
                return None
            
            dfs = []
            for file in files:
                try:
                    file_df = pd.read_parquet(file)
                    dfs.append(file_df)
                    logger.debug(f"Loaded {len(file_df)} rows from {file.name}")
                except Exception as e:
                    logger.warning(f"Failed to load {file.name}: {e}")
            
            if not dfs:
                logger.error("No data loaded from any files")
                return None
            
            df = pd.concat(dfs, ignore_index=True)
            logger.info(f"Loaded {len(df)} total rows from {len(dfs)} files")
        
        # Filter by date if specified
        if start_date or end_date:
            df = self._filter_by_date(df, start_date, end_date)
        
        return df
    
    def load_from_csv(self, source_path, start_date=None, end_date=None):
        """Load data from CSV files"""
        logger.info(f"Loading CSV data from: {source_path}")
        
        source = Path(source_path)
        
        if source.is_file():
            df = pd.read_csv(source)
            logger.info(f"Loaded {len(df)} rows from {source.name}")
        else:
            files = list(source.glob("*.csv"))
            
            if not files:
                logger.error(f"No CSV files found in {source}")
                return None
            
            dfs = []
            for file in files:
                try:
                    file_df = pd.read_csv(file)
                    dfs.append(file_df)
                except Exception as e:
                    logger.warning(f"Failed to load {file.name}: {e}")
            
            df = pd.concat(dfs, ignore_index=True)
            logger.info(f"Loaded {len(df)} total rows from {len(dfs)} files")
        
        if start_date or end_date:
            df = self._filter_by_date(df, start_date, end_date)
        
        return df
    
    def _filter_by_date(self, df, start_date, end_date):
        """Filter dataframe by date range"""
        # Find timestamp column
        timestamp_col = None
        for col in ['timestamp', 'Timestamp', 'DateTime', 'Date', 'Time']:
            if col in df.columns:
                timestamp_col = col
                break
        
        if not timestamp_col:
            logger.warning("No timestamp column found, cannot filter by date")
            return df
        
        df[timestamp_col] = pd.to_datetime(df[timestamp_col])
        
        original_len = len(df)
        
        if start_date:
            start = pd.to_datetime(start_date)
            df = df[df[timestamp_col] >= start]
        
        if end_date:
            end = pd.to_datetime(end_date)
            df = df[df[timestamp_col] <= end]
        
        logger.info(f"Filtered from {original_len} to {len(df)} rows")
        return df
    
    def prepare_for_training(self, df):
        """
        Prepare data for ML training
        - Normalize column names
        - Convert to numeric
        - Handle missing values
        - Sort by timestamp
        """
        logger.info("Preparing data for training...")
        
        # Normalize timestamp column name
        for col in ['Timestamp', 'DateTime', 'Date']:
            if col in df.columns:
                df = df.rename(columns={col: 'timestamp'})
                break
        
        # Convert timestamp
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.sort_values('timestamp')
        
        # Convert all numeric columns
        for col in df.columns:
            if col != 'timestamp':
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Report missing values
        missing = df.isnull().sum()
        if missing.any():
            logger.warning("Missing values found:")
            for col, count in missing[missing > 0].items():
                pct = (count / len(df)) * 100
                logger.warning(f"  {col}: {count} ({pct:.1f}%)")
        
        # Forward fill missing values (use last known value)
        df = df.fillna(method='ffill')
        
        # Check target column exists
        if self.target_column not in df.columns:
            logger.error(f"Target column '{self.target_column}' not found!")
            logger.info(f"Available columns: {list(df.columns)}")
            return None
        
        logger.info(f"Data prepared: {len(df)} rows, {len(df.columns)} columns")
        return df
    
    def save_to_ml_format(self, df, split_by_day=True):
        """
        Save data in ML system format (01_RawData/)
        
        Args:
            df: DataFrame to save
            split_by_day: If True, split into daily files (recommended)
        
        Returns:
            Number of files saved
        """
        logger.info("Saving data to ML format...")
        
        if 'timestamp' not in df.columns:
            logger.error("No timestamp column - cannot split by day")
            split_by_day = False
        
        if not split_by_day:
            # Save as single file
            filename = f"historical_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            self.storage.save(df, '01_RawData', filename)
            logger.info(f"Saved 1 file: {filename}")
            return 1
        
        # Split by day
        df['date'] = pd.to_datetime(df['timestamp']).dt.date
        unique_dates = sorted(df['date'].unique())
        
        saved_count = 0
        for date in unique_dates:
            day_data = df[df['date'] == date].copy()
            day_data = day_data.drop(columns=['date'])
            
            if len(day_data) > 0:
                filename = f"raw_data_{date.strftime('%Y%m%d')}"
                self.storage.save(day_data, '01_RawData', filename)
                saved_count += 1
                
                if saved_count % 30 == 0:
                    logger.info(f"  Saved {saved_count}/{len(unique_dates)} days...")
        
        logger.info(f"Saved {saved_count} daily files to 01_RawData/")
        return saved_count
    
    def import_historical_data(self, source_path, file_type='parquet', 
                              start_date=None, end_date=None):
        """
        Complete import workflow: Load → Prepare → Save
        
        Args:
            source_path: Path to data files
            file_type: 'parquet', 'csv', or 'auto'
            start_date: Optional filter (YYYY-MM-DD)
            end_date: Optional filter (YYYY-MM-DD)
        
        Returns:
            Number of files created
        """
        logger.info("=" * 80)
        logger.info("IMPORTING HISTORICAL DATA")
        logger.info("=" * 80)
        
        # Auto-detect file type
        if file_type == 'auto':
            source = Path(source_path)
            if source.is_file():
                file_type = source.suffix.lower().replace('.', '')
            else:
                # Check what files exist
                if list(source.glob("*.parquet")):
                    file_type = 'parquet'
                elif list(source.glob("*.csv")):
                    file_type = 'csv'
                else:
                    logger.error("Could not auto-detect file type")
                    return 0
        
        # Load data
        if file_type == 'parquet':
            df = self.load_from_parquet(source_path, start_date, end_date)
        elif file_type == 'csv':
            df = self.load_from_csv(source_path, start_date, end_date)
        else:
            logger.error(f"Unsupported file type: {file_type}")
            return 0
        
        if df is None or len(df) == 0:
            logger.error("No data loaded")
            return 0
        
        # Prepare
        df = self.prepare_for_training(df)
        
        if df is None:
            logger.error("Data preparation failed")
            return 0
        
        # Save
        count = self.save_to_ml_format(df)
        
        logger.info("=" * 80)
        logger.info(f"IMPORT COMPLETE: {count} files created")
        logger.info("=" * 80)
        
        return count


def main():
    """Command-line interface for importing historical data"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Import historical data for ML training'
    )
    parser.add_argument('source', help='Path to data files or directory')
    parser.add_argument('--type', default='auto', 
                       choices=['auto', 'parquet', 'csv'],
                       help='File type (default: auto-detect)')
    parser.add_argument('--start-date', help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', help='End date (YYYY-MM-DD)')
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Import data
    loader = HistoricalDataLoader()
    count = loader.import_historical_data(
        args.source,
        file_type=args.type,
        start_date=args.start_date,
        end_date=args.end_date
    )
    
    if count > 0:
        print(f"\n✅ Success! Imported {count} files")
        print("\nNext steps:")
        print("1. Run parameter discovery:")
        print("   python ML_System/parameter_discovery.py")
        print("2. Train models:")
        print("   python ML_System/model_trainer.py")
    else:
        print("\n❌ Import failed")


if __name__ == '__main__':
    main()
