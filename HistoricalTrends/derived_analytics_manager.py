# =====================================================
# DERIVED ANALYTICS DATA MANAGER
# Manages daily calculation results and caching
# =====================================================

import pandas as pd
import os
import json
from datetime import datetime, timedelta
from pathlib import Path
import hashlib

class DerivedAnalyticsManager:
    """
    Intelligent manager for derived analytics data
    
    Features:
    - Daily parquet files for derived metrics
    - Configuration-based cache management
    - Automatic recalculation detection
    - Input data change tracking
    - Folder structure management
    """
    
    def __init__(self, config_file='derived_analytics_config.json'):
        self.config_file = config_file
        self.config = self._load_or_create_config()
        self.derived_data_dir = self.config['paths']['derived_data_directory']
        self.cache_metadata_dir = self.config['paths']['cache_metadata_directory']
        
        # Create directory structure
        self._initialize_directories()
    
    def _load_or_create_config(self):
        """Load existing config or create default"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    print(f"✓ Loaded configuration from {self.config_file}")
                    return config
            except Exception as e:
                print(f"⚠️ Failed to load config: {e}, creating default")
        
        # Default configuration
        default_config = {
            "version": "1.0",
            "created": datetime.now().isoformat(),
            "paths": {
                "derived_data_directory": "D:/OpcLogs/DerivedData",
                "cache_metadata_directory": "D:/OpcLogs/DerivedData/Metadata",
                "input_data_directory": "D:/OpcLogs/Data"
            },
            "storage": {
                "file_naming": "YYYYMMDD_analytics.parquet",
                "retention_days": 365,
                "compression": "snappy",
                "daily_partitioning": True
            },
            "calculation_triggers": {
                "recalculate_on_new_data": True,
                "recalculate_on_config_change": True,
                "force_recalculation_after_days": 30,
                "checksum_validation": True
            },
            "derived_metrics": {
                "baseline_performance": {
                    "enabled": True,
                    "update_frequency_days": 30,
                    "file_pattern": "baseline_YYYYMMDD.parquet"
                },
                "production_deltas": {
                    "enabled": True,
                    "update_frequency_days": 1,
                    "file_pattern": "production_delta_YYYYMMDD.parquet"
                },
                "parameter_influence": {
                    "enabled": True,
                    "update_frequency_days": 7,
                    "file_pattern": "influence_map_YYYYMMDD.parquet"
                },
                "loss_attribution": {
                    "enabled": True,
                    "update_frequency_days": 1,
                    "file_pattern": "loss_attribution_YYYYMMDD.parquet"
                },
                "stability_scores": {
                    "enabled": True,
                    "update_frequency_days": 1,
                    "file_pattern": "stability_scores_YYYYMMDD.parquet"
                },
                "condition_scores": {
                    "enabled": True,
                    "update_frequency_days": 1,
                    "file_pattern": "condition_scores_YYYYMMDD.parquet"
                }
            },
            "performance": {
                "cache_results_in_memory": True,
                "max_memory_cache_mb": 500,
                "parallel_processing": True,
                "chunk_size_rows": 100000
            }
        }
        
        # Save default config
        with open(self.config_file, 'w') as f:
            json.dump(default_config, f, indent=2)
        
        print(f"✓ Created default configuration: {self.config_file}")
        return default_config
    
    def _initialize_directories(self):
        """Create directory structure for derived data"""
        directories = [
            self.derived_data_dir,
            self.cache_metadata_dir,
            os.path.join(self.derived_data_dir, 'Baselines'),
            os.path.join(self.derived_data_dir, 'ProductionDeltas'),
            os.path.join(self.derived_data_dir, 'InfluenceMaps'),
            os.path.join(self.derived_data_dir, 'LossAttribution'),
            os.path.join(self.derived_data_dir, 'StabilityScores'),
            os.path.join(self.derived_data_dir, 'ConditionScores')
        ]
        
        for directory in directories:
            os.makedirs(directory, exist_ok=True)
        
        print(f"✓ Directory structure initialized at {self.derived_data_dir}")
    
    def _calculate_input_checksum(self, input_file_path):
        """Calculate checksum of input file to detect changes"""
        if not os.path.exists(input_file_path):
            return None
        
        # Use file modification time + size as quick checksum
        stat = os.stat(input_file_path)
        checksum_string = f"{stat.st_mtime}_{stat.st_size}"
        return hashlib.md5(checksum_string.encode()).hexdigest()
    
    def _get_cache_metadata_path(self, metric_type, date):
        """Get path to cache metadata file"""
        date_str = date.strftime('%Y%m%d')
        return os.path.join(
            self.cache_metadata_dir,
            f"{metric_type}_{date_str}_metadata.json"
        )
    
    def _load_cache_metadata(self, metric_type, date):
        """Load cache metadata for specific metric and date"""
        metadata_path = self._get_cache_metadata_path(metric_type, date)
        
        if os.path.exists(metadata_path):
            try:
                with open(metadata_path, 'r') as f:
                    return json.load(f)
            except:
                return None
        return None
    
    def _save_cache_metadata(self, metric_type, date, metadata):
        """Save cache metadata"""
        metadata_path = self._get_cache_metadata_path(metric_type, date)
        
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
    
    def should_recalculate(self, metric_type, date, input_files):
        """
        Determine if metric should be recalculated
        
        Returns: (should_recalculate: bool, reason: str)
        """
        # Get derived file path
        derived_file = self.get_derived_file_path(metric_type, date)
        
        # If derived file doesn't exist, must calculate
        if not os.path.exists(derived_file):
            return True, "Derived file does not exist"
        
        # Load cache metadata
        cache_metadata = self._load_cache_metadata(metric_type, date)
        
        if not cache_metadata:
            return True, "No cache metadata found"
        
        # Check if input files changed
        if self.config['calculation_triggers']['checksum_validation']:
            for input_file in input_files:
                current_checksum = self._calculate_input_checksum(input_file)
                cached_checksum = cache_metadata.get('input_checksums', {}).get(input_file)
                
                if current_checksum != cached_checksum:
                    return True, f"Input file changed: {os.path.basename(input_file)}"
        
        # Check if forced recalculation period expired
        calculation_date = datetime.fromisoformat(cache_metadata.get('calculated_at', '2000-01-01'))
        days_since_calculation = (datetime.now() - calculation_date).days
        force_after_days = self.config['calculation_triggers']['force_recalculation_after_days']
        
        if days_since_calculation > force_after_days:
            return True, f"Recalculation period expired ({days_since_calculation} > {force_after_days} days)"
        
        # Check metric-specific update frequency
        metric_config = self.config['derived_metrics'].get(metric_type, {})
        update_freq = metric_config.get('update_frequency_days', 1)
        
        if days_since_calculation >= update_freq:
            return True, f"Update frequency reached ({days_since_calculation} >= {update_freq} days)"
        
        return False, "Cache is valid"
    
    def get_derived_file_path(self, metric_type, date):
        """Get file path for derived metric"""
        date_str = date.strftime('%Y%m%d')
        
        # Map metric types to subdirectories
        subdir_map = {
            'baseline_performance': 'Baselines',
            'production_deltas': 'ProductionDeltas',
            'parameter_influence': 'InfluenceMaps',
            'loss_attribution': 'LossAttribution',
            'stability_scores': 'StabilityScores',
            'condition_scores': 'ConditionScores'
        }
        
        subdir = subdir_map.get(metric_type, '')
        
        # Get file pattern from config
        metric_config = self.config['derived_metrics'].get(metric_type, {})
        file_pattern = metric_config.get('file_pattern', f'{metric_type}_YYYYMMDD.parquet')
        filename = file_pattern.replace('YYYYMMDD', date_str)
        
        return os.path.join(self.derived_data_dir, subdir, filename)
    
    def save_derived_data(self, metric_type, date, dataframe, input_files, calculation_params=None):
        """
        Save derived analytics data with metadata
        
        Args:
            metric_type: Type of metric (baseline_performance, production_deltas, etc.)
            date: Date for this data
            dataframe: Calculated results
            input_files: List of input files used for calculation
            calculation_params: Optional dict of calculation parameters
        """
        # Get output path
        output_path = self.get_derived_file_path(metric_type, date)
        
        # Save parquet file
        dataframe.to_parquet(
            output_path,
            compression=self.config['storage']['compression'],
            index=False
        )
        
        # Create metadata
        input_checksums = {
            f: self._calculate_input_checksum(f) for f in input_files
        }
        
        metadata = {
            'metric_type': metric_type,
            'date': date.strftime('%Y-%m-%d'),
            'calculated_at': datetime.now().isoformat(),
            'row_count': len(dataframe),
            'columns': list(dataframe.columns),
            'input_files': input_files,
            'input_checksums': input_checksums,
            'calculation_params': calculation_params or {},
            'file_size_mb': os.path.getsize(output_path) / (1024 * 1024)
        }
        
        # Save metadata
        self._save_cache_metadata(metric_type, date, metadata)
        
        print(f"✓ Saved {metric_type} for {date.strftime('%Y-%m-%d')}")
        print(f"  - File: {output_path}")
        print(f"  - Rows: {len(dataframe)}")
        print(f"  - Size: {metadata['file_size_mb']:.2f} MB")
        
        return output_path
    
    def load_derived_data(self, metric_type, date):
        """
        Load derived data for specific metric and date
        
        Returns: DataFrame or None if not found
        """
        file_path = self.get_derived_file_path(metric_type, date)
        
        if not os.path.exists(file_path):
            print(f"⚠️ Derived data not found: {file_path}")
            return None
        
        try:
            df = pd.read_parquet(file_path)
            print(f"✓ Loaded {metric_type} for {date.strftime('%Y-%m-%d')} ({len(df)} rows)")
            return df
        except Exception as e:
            print(f"❌ Failed to load {file_path}: {e}")
            return None
    
    def load_or_calculate(self, metric_type, date, input_files, calculation_function, calculation_params=None):
        """
        Load cached data or calculate if needed
        
        Args:
            metric_type: Type of metric
            date: Date for data
            input_files: List of input file paths
            calculation_function: Function to call if recalculation needed
                                 Should accept (input_files, date, params) and return DataFrame
            calculation_params: Optional parameters for calculation
        
        Returns: DataFrame
        """
        # Check if recalculation needed
        should_recalc, reason = self.should_recalculate(metric_type, date, input_files)
        
        if should_recalc:
            print(f"🔄 Recalculating {metric_type} for {date.strftime('%Y-%m-%d')}")
            print(f"   Reason: {reason}")
            
            # Call calculation function
            result_df = calculation_function(input_files, date, calculation_params)
            
            # Save results
            self.save_derived_data(metric_type, date, result_df, input_files, calculation_params)
            
            return result_df
        else:
            print(f"📦 Using cached {metric_type} for {date.strftime('%Y-%m-%d')}")
            return self.load_derived_data(metric_type, date)
    
    def get_date_range_data(self, metric_type, start_date, end_date):
        """
        Load derived data for date range
        
        Returns: Combined DataFrame
        """
        all_data = []
        current_date = start_date
        
        while current_date <= end_date:
            df = self.load_derived_data(metric_type, current_date)
            if df is not None:
                all_data.append(df)
            current_date += timedelta(days=1)
        
        if not all_data:
            return None
        
        combined = pd.concat(all_data, ignore_index=True)
        print(f"✓ Combined {len(all_data)} files: {len(combined)} total rows")
        return combined
    
    def cleanup_old_data(self, retention_days=None):
        """Remove derived data older than retention period"""
        if retention_days is None:
            retention_days = self.config['storage']['retention_days']
        
        cutoff_date = datetime.now() - timedelta(days=retention_days)
        removed_count = 0
        
        # Scan all derived data directories
        for metric_type in self.config['derived_metrics'].keys():
            metric_config = self.config['derived_metrics'][metric_type]
            if not metric_config.get('enabled', True):
                continue
            
            # Check files for this metric
            current_date = cutoff_date - timedelta(days=365)  # Check last year
            while current_date < datetime.now():
                file_path = self.get_derived_file_path(metric_type, current_date)
                
                if os.path.exists(file_path):
                    file_date = datetime.fromtimestamp(os.path.getmtime(file_path))
                    
                    if file_date < cutoff_date:
                        os.remove(file_path)
                        removed_count += 1
                        
                        # Remove metadata too
                        metadata_path = self._get_cache_metadata_path(metric_type, current_date)
                        if os.path.exists(metadata_path):
                            os.remove(metadata_path)
                
                current_date += timedelta(days=1)
        
        if removed_count > 0:
            print(f"✓ Cleaned up {removed_count} old derived data files")
        
        return removed_count
    
    def get_storage_statistics(self):
        """Get statistics about derived data storage"""
        stats = {
            'total_files': 0,
            'total_size_mb': 0,
            'by_metric': {},
            'oldest_file': None,
            'newest_file': None
        }
        
        for metric_type in self.config['derived_metrics'].keys():
            metric_stats = {
                'file_count': 0,
                'total_size_mb': 0,
                'date_range': {'start': None, 'end': None}
            }
            
            # Scan directory
            subdir_map = {
                'baseline_performance': 'Baselines',
                'production_deltas': 'ProductionDeltas',
                'parameter_influence': 'InfluenceMaps',
                'loss_attribution': 'LossAttribution',
                'stability_scores': 'StabilityScores',
                'condition_scores': 'ConditionScores'
            }
            
            subdir = os.path.join(self.derived_data_dir, subdir_map.get(metric_type, ''))
            
            if os.path.exists(subdir):
                for filename in os.listdir(subdir):
                    if filename.endswith('.parquet'):
                        file_path = os.path.join(subdir, filename)
                        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
                        
                        metric_stats['file_count'] += 1
                        metric_stats['total_size_mb'] += file_size_mb
                        stats['total_files'] += 1
                        stats['total_size_mb'] += file_size_mb
            
            stats['by_metric'][metric_type] = metric_stats
        
        return stats
    
    def export_configuration_report(self, output_file='derived_analytics_report.json'):
        """Export comprehensive configuration and statistics report"""
        report = {
            'configuration': self.config,
            'storage_statistics': self.get_storage_statistics(),
            'directory_structure': {
                'derived_data': self.derived_data_dir,
                'metadata': self.cache_metadata_dir
            },
            'generated_at': datetime.now().isoformat()
        }
        
        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"✓ Configuration report exported to {output_file}")
        return report
