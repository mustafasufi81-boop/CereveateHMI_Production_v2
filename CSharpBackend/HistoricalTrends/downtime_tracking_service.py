"""
Downtime Tracking Service with MTBF/MTTR Calculation
Monitors production load, detects downtimes, tracks failures, and calculates reliability metrics
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
import json
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class DowntimeTrackingService:
    """
    Service for tracking plant downtimes, analyzing failures, and calculating MTBF/MTTR
    """
    
    def __init__(self, config_path: str = 'baseline_config.json'):
        """Initialize downtime tracking service with configuration"""
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        self.downtime_config = self.config.get('downtime_tracking', {})
        self.mtbf_config = self.config.get('mtbf_mttr_config', {})
        self.abnormal_config = self.config.get('abnormal_parameter_detection', {})
        
        # Thresholds
        self.zero_load_threshold = self.downtime_config.get('zero_load_threshold_mw', 1.0)
        self.min_downtime_minutes = self.downtime_config.get('min_downtime_duration_minutes', 5)
        self.max_gap_minutes = self.downtime_config.get('max_gap_minutes', 10)
        
        # Storage
        self.storage_dir = Path(self.downtime_config.get('storage_directory', 'D:/OpcLogs/Downtime'))
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Downtime Tracking Service initialized")
        logger.info(f"  Zero load threshold: {self.zero_load_threshold} MW")
        logger.info(f"  Min downtime: {self.min_downtime_minutes} minutes")
        logger.info(f"  Storage: {self.storage_dir}")
    
    def detect_downtimes(self, df: pd.DataFrame, production_tag: str) -> List[Dict]:
        """
        Detect downtime periods from production data
        
        Args:
            df: DataFrame with Timestamp and production tag columns
            production_tag: Name of production column (e.g., 'TURBINE_LOADMW')
            
        Returns:
            List of downtime events with start, end, duration
        """
        logger.info(f"🔍 Detecting downtimes for {production_tag}")
        
        if production_tag not in df.columns:
            logger.error(f"Production tag {production_tag} not found in data")
            return []
        
        # Ensure timestamp is datetime
        if not pd.api.types.is_datetime64_any_dtype(df['Timestamp']):
            df['Timestamp'] = pd.to_datetime(df['Timestamp'])
        
        df = df.sort_values('Timestamp').reset_index(drop=True)
        
        # Convert to numeric, treating errors as NaN
        values = pd.to_numeric(df[production_tag], errors='coerce')
        
        # Mark as down if: null, zero, or below threshold
        is_down = (values.isna()) | (values < self.zero_load_threshold)
        
        # Find downtime periods
        downtimes = []
        in_downtime = False
        downtime_start = None
        downtime_start_idx = None
        
        for idx, row in df.iterrows():
            current_down = is_down.iloc[idx]
            timestamp = row['Timestamp']
            
            if current_down and not in_downtime:
                # Start of downtime
                in_downtime = True
                downtime_start = timestamp
                downtime_start_idx = idx
                
            elif not current_down and in_downtime:
                # End of downtime
                downtime_end = timestamp
                duration_minutes = (downtime_end - downtime_start).total_seconds() / 60
                
                # Only record if meets minimum duration
                if duration_minutes >= self.min_downtime_minutes:
                    load_before = df[production_tag].iloc[downtime_start_idx - 1] if downtime_start_idx > 0 else None
                    load_after = df[production_tag].iloc[idx] if idx < len(df) else None
                    
                    downtimes.append({
                        'downtime_id': f"DT_{downtime_start.strftime('%Y%m%d%H%M%S')}",
                        'start_timestamp': downtime_start,
                        'end_timestamp': downtime_end,
                        'duration_minutes': duration_minutes,
                        'duration_hours': duration_minutes / 60,
                        'production_tag': production_tag,
                        'load_before_shutdown': float(load_before) if load_before is not None and not pd.isna(load_before) else 0.0,
                        'load_after_startup': float(load_after) if load_after is not None and not pd.isna(load_after) else 0.0,
                        'failure_category': None,
                        'failure_reason': None,
                        'root_cause': None,
                        'corrective_action': None,
                        'abnormal_parameters': None,
                        'created_at': datetime.now(),
                        'updated_at': datetime.now()
                    })
                
                in_downtime = False
                downtime_start = None
        
        # Handle ongoing downtime at end of data
        if in_downtime and downtime_start is not None:
            last_timestamp = df['Timestamp'].iloc[-1]
            duration_minutes = (last_timestamp - downtime_start).total_seconds() / 60
            
            if duration_minutes >= self.min_downtime_minutes:
                downtimes.append({
                    'downtime_id': f"DT_{downtime_start.strftime('%Y%m%d%H%M%S')}_ONGOING",
                    'start_timestamp': downtime_start,
                    'end_timestamp': None,
                    'duration_minutes': duration_minutes,
                    'duration_hours': duration_minutes / 60,
                    'production_tag': production_tag,
                    'load_before_shutdown': float(df[production_tag].iloc[downtime_start_idx - 1]) if downtime_start_idx > 0 else 0.0,
                    'load_after_startup': None,
                    'failure_category': 'Ongoing',
                    'failure_reason': 'System currently down',
                    'root_cause': None,
                    'corrective_action': None,
                    'abnormal_parameters': None,
                    'created_at': datetime.now(),
                    'updated_at': datetime.now()
                })
        
        logger.info(f"  ✓ Detected {len(downtimes)} downtime events")
        return downtimes
    
    def detect_abnormal_parameters(self, df: pd.DataFrame, downtime_start: datetime, 
                                   window_minutes: int = 30) -> List[str]:
        """
        Detect which parameters behaved abnormally before downtime
        
        Args:
            df: DataFrame with all parameters
            downtime_start: When downtime started
            window_minutes: Time window before downtime to analyze
            
        Returns:
            List of parameter names that behaved abnormally
        """
        if not self.abnormal_config.get('enabled', True):
            return []
        
        abnormal_params = []
        window_start = downtime_start - timedelta(minutes=window_minutes)
        
        # Filter data to window before downtime
        df_window = df[(df['Timestamp'] >= window_start) & (df['Timestamp'] < downtime_start)]
        
        if len(df_window) < 2:
            return []
        
        # Check each monitored parameter
        params_to_check = self.abnormal_config.get('parameters_to_monitor', [])
        
        for param in params_to_check:
            if param not in df.columns:
                continue
            
            values = pd.to_numeric(df_window[param], errors='coerce').dropna()
            
            if len(values) < 2:
                continue
            
            # Check for abnormal conditions
            is_abnormal = False
            
            # 1. Sudden drop
            sudden_drop_threshold = self.abnormal_config.get('abnormal_conditions', {}).get('sudden_drop_percentage', 30)
            pct_changes = values.pct_change() * 100
            if (pct_changes < -sudden_drop_threshold).any():
                is_abnormal = True
            
            # 2. Sudden spike
            sudden_spike_threshold = self.abnormal_config.get('abnormal_conditions', {}).get('sudden_spike_percentage', 30)
            if (pct_changes > sudden_spike_threshold).any():
                is_abnormal = True
            
            # 3. Out of range (check tag config)
            tag_config = self.config.get('tags', {}).get(param, {})
            thresholds = tag_config.get('thresholds', {})
            if thresholds:
                critical_low = thresholds.get('critical_low')
                critical_high = thresholds.get('critical_high')
                if critical_low and (values < critical_low).any():
                    is_abnormal = True
                if critical_high and (values > critical_high).any():
                    is_abnormal = True
            
            # 4. Erratic behavior (high std dev)
            std_multiplier = self.abnormal_config.get('abnormal_conditions', {}).get('std_dev_multiplier', 3.0)
            mean_val = values.mean()
            std_val = values.std()
            if std_val > 0 and ((values - mean_val).abs() > std_multiplier * std_val).any():
                is_abnormal = True
            
            if is_abnormal:
                abnormal_params.append(param)
        
        return abnormal_params
    
    def calculate_mtbf_mttr(self, start_date: datetime, end_date: datetime, 
                           production_tag: str) -> Dict:
        """
        Calculate MTBF (Mean Time Between Failures) and MTTR (Mean Time To Repair)
        
        Args:
            start_date: Start of analysis period
            end_date: End of analysis period
            production_tag: Production tag name
            
        Returns:
            Dictionary with MTBF, MTTR, and related metrics
        """
        logger.info(f"📊 Calculating MTBF/MTTR for {start_date.date()} to {end_date.date()}")
        
        # Load downtime records for period
        downtimes = self.load_downtime_records(start_date, end_date, production_tag)
        
        if len(downtimes) == 0:
            total_hours = (end_date - start_date).total_seconds() / 3600
            return {
                'period_start': start_date,
                'period_end': end_date,
                'total_period_hours': total_hours,
                'total_uptime_hours': total_hours,
                'total_downtime_hours': 0.0,
                'number_of_failures': 0,
                'mtbf_hours': total_hours,
                'mttr_hours': 0.0,
                'availability_percentage': 100.0,
                'reliability_percentage': 100.0,
                'downtime_events': []
            }
        
        # Convert to DataFrame
        df_downtimes = pd.DataFrame(downtimes)
        
        # Exclude planned maintenance if configured
        if self.mtbf_config.get('exclude_planned_maintenance_from_mtbf', True):
            failures = df_downtimes[df_downtimes['failure_category'] != 'Planned Maintenance']
        else:
            failures = df_downtimes
        
        # Calculate metrics
        total_period_hours = (end_date - start_date).total_seconds() / 3600
        total_downtime_hours = df_downtimes['duration_hours'].sum()
        total_uptime_hours = total_period_hours - total_downtime_hours
        
        number_of_failures = len(failures)
        
        # MTBF = Total Uptime / Number of Failures
        mtbf_hours = total_uptime_hours / number_of_failures if number_of_failures > 0 else total_uptime_hours
        
        # MTTR = Total Downtime / Number of Failures
        mttr_hours = failures['duration_hours'].sum() / number_of_failures if number_of_failures > 0 else 0.0
        
        # Availability = Uptime / (Uptime + Downtime)
        availability = (total_uptime_hours / total_period_hours * 100) if total_period_hours > 0 else 0.0
        
        # Reliability = 1 - (Failures / Expected Failures)
        # Simplified: based on MTBF target (e.g., 720 hours = 30 days)
        mtbf_target = 720  # hours (30 days)
        reliability = min(100.0, (mtbf_hours / mtbf_target * 100)) if mtbf_target > 0 else 100.0
        
        result = {
            'period_start': start_date,
            'period_end': end_date,
            'total_period_hours': total_period_hours,
            'total_uptime_hours': total_uptime_hours,
            'total_downtime_hours': total_downtime_hours,
            'number_of_failures': number_of_failures,
            'number_of_planned_maintenance': len(df_downtimes[df_downtimes['failure_category'] == 'Planned Maintenance']),
            'mtbf_hours': mtbf_hours,
            'mtbf_days': mtbf_hours / 24,
            'mttr_hours': mttr_hours,
            'mttr_minutes': mttr_hours * 60,
            'availability_percentage': availability,
            'reliability_percentage': reliability,
            'downtime_events': downtimes,
            'failure_breakdown': df_downtimes.groupby('failure_category')['duration_hours'].agg(['count', 'sum']).to_dict()
        }
        
        logger.info(f"  ✓ MTBF: {mtbf_hours:.2f} hours ({mtbf_hours/24:.1f} days)")
        logger.info(f"  ✓ MTTR: {mttr_hours:.2f} hours ({mttr_hours*60:.1f} minutes)")
        logger.info(f"  ✓ Availability: {availability:.2f}%")
        
        return result
    
    def save_downtime_event(self, downtime: Dict):
        """Save downtime event to parquet file"""
        # Create year-month partition
        start_time = downtime['start_timestamp']
        partition = start_time.strftime('%Y_%m')
        
        file_path = self.storage_dir / f"downtimes_{partition}.parquet"
        
        # Convert to DataFrame
        df_new = pd.DataFrame([downtime])
        
        # Append to existing file or create new
        if file_path.exists():
            df_existing = pd.read_parquet(file_path)
            df_combined = pd.concat([df_existing, df_new], ignore_index=True)
            df_combined = df_combined.drop_duplicates(subset=['downtime_id'], keep='last')
        else:
            df_combined = df_new
        
        # Save
        df_combined.to_parquet(file_path, index=False)
        logger.info(f"  ✓ Saved downtime event to {file_path}")
    
    def load_downtime_records(self, start_date: datetime, end_date: datetime, 
                             production_tag: str = None) -> List[Dict]:
        """Load downtime records for a date range"""
        all_records = []
        
        # Get list of parquet files in date range
        for file_path in self.storage_dir.glob("downtimes_*.parquet"):
            try:
                df = pd.read_parquet(file_path)
                
                # Filter by date range
                df = df[(df['start_timestamp'] >= start_date) & (df['start_timestamp'] <= end_date)]
                
                # Filter by production tag if specified
                if production_tag:
                    df = df[df['production_tag'] == production_tag]
                
                if len(df) > 0:
                    all_records.extend(df.to_dict('records'))
            except Exception as e:
                logger.error(f"Error loading {file_path}: {e}")
        
        return all_records
    
    def update_failure_reason(self, downtime_id: str, failure_category: str, 
                             failure_reason: str, root_cause: str = None, 
                             corrective_action: str = None, created_by: str = None):
        """Update failure reason for a downtime event"""
        # Find the downtime record
        for file_path in self.storage_dir.glob("downtimes_*.parquet"):
            try:
                df = pd.read_parquet(file_path)
                
                if downtime_id in df['downtime_id'].values:
                    # Update the record
                    idx = df[df['downtime_id'] == downtime_id].index[0]
                    df.loc[idx, 'failure_category'] = failure_category
                    df.loc[idx, 'failure_reason'] = failure_reason
                    df.loc[idx, 'root_cause'] = root_cause
                    df.loc[idx, 'corrective_action'] = corrective_action
                    df.loc[idx, 'updated_at'] = datetime.now()
                    
                    if created_by:
                        df.loc[idx, 'created_by'] = created_by
                    
                    # Save back
                    df.to_parquet(file_path, index=False)
                    logger.info(f"  ✓ Updated downtime {downtime_id}")
                    return True
                    
            except Exception as e:
                logger.error(f"Error updating {file_path}: {e}")
        
        logger.warning(f"Downtime {downtime_id} not found")
        return False
