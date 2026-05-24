# =====================================================
# INTERPOLATION CACHE SERVICE
# Manages filled data separately from original parquet
# =====================================================

import pandas as pd
import os
import json
from datetime import datetime
from pathlib import Path

class InterpolationCacheService:
    """
    Manages interpolated data in SEPARATE parquet file
    NEVER modifies original data files
    """
    
    def __init__(self, cache_directory):
        self.cache_directory = cache_directory
        self.cache_file = os.path.join(cache_directory, 'interpolation_cache.parquet')
        self.metadata_file = os.path.join(cache_directory, 'interpolation_metadata.json')
        
        # Ensure cache directory exists
        os.makedirs(cache_directory, exist_ok=True)
        
        self.metadata = self._load_metadata()
    
    def _load_metadata(self):
        """Load interpolation metadata"""
        if os.path.exists(self.metadata_file):
            try:
                with open(self.metadata_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        
        return {
            'version': '1.0',
            'created': datetime.now().isoformat(),
            'last_updated': None,
            'interpolation_runs': [],
            'statistics': {
                'total_interpolated_points': 0,
                'tags_affected': []
            }
        }
    
    def _save_metadata(self):
        """Save interpolation metadata"""
        self.metadata['last_updated'] = datetime.now().isoformat()
        with open(self.metadata_file, 'w') as f:
            json.dump(self.metadata, f, indent=2)
    
    def create_interpolated_dataset(self, original_data, tags, method='linear', config=None):
        """
        Create interpolated dataset WITHOUT modifying original
        
        Args:
            original_data: DataFrame from original parquet (READ-ONLY)
            tags: List of tags to process
            method: Interpolation method
            config: Data quality configuration
            
        Returns:
            Dictionary with original and interpolated data
        """
        print("🔄 Creating interpolation cache (original data untouched)...")
        
        # CRITICAL: Work on COPY, never modify original
        data_copy = original_data.copy()
        
        interpolated_records = []
        interpolation_log = []
        
        for tag in tags:
            print(f"  Processing {tag}...")
            
            # Extract tag data
            tag_data = data_copy[data_copy['TagId'] == tag].copy()
            
            if tag_data.empty:
                continue
            
            # Identify missing values
            missing_mask = tag_data['Value'].isna() | (tag_data['Value'] == None)
            missing_count = missing_mask.sum()
            
            if missing_count == 0:
                print(f"    ✓ No missing values")
                continue
            
            print(f"    Found {missing_count} missing values")
            
            # Apply interpolation
            if method == 'linear':
                tag_data['Value_Interpolated'] = tag_data['Value'].interpolate(method='linear')
            elif method == 'forward':
                tag_data['Value_Interpolated'] = tag_data['Value'].ffill()
            elif method == 'backward':
                tag_data['Value_Interpolated'] = tag_data['Value'].bfill()
            elif method == 'mean':
                mean_val = tag_data['Value'].mean()
                tag_data['Value_Interpolated'] = tag_data['Value'].fillna(mean_val)
            else:
                tag_data['Value_Interpolated'] = tag_data['Value'].interpolate(method='linear')
            
            # Mark which values were interpolated
            tag_data['IsInterpolated'] = missing_mask
            tag_data['InterpolationMethod'] = method
            tag_data['InterpolationTimestamp'] = datetime.now().isoformat()
            
            # Store only INTERPOLATED points (not entire dataset)
            interpolated_points = tag_data[tag_data['IsInterpolated']]
            
            if len(interpolated_points) > 0:
                # Create records for cache
                for _, row in interpolated_points.iterrows():
                    interpolated_records.append({
                        'RowId': row['RowId'],
                        'TagId': row['TagId'],
                        'Timestamp': row['Timestamp'],
                        'OriginalValue': None,  # Was missing
                        'InterpolatedValue': row['Value_Interpolated'],
                        'Method': method,
                        'CreatedAt': datetime.now().isoformat()
                    })
                
                # Log interpolation
                interpolation_log.append({
                    'tag': tag,
                    'method': method,
                    'points_interpolated': len(interpolated_points),
                    'timestamp': datetime.now().isoformat()
                })
                
                print(f"    ✓ Interpolated {len(interpolated_points)} points")
        
        # Save interpolation cache
        if interpolated_records:
            cache_df = pd.DataFrame(interpolated_records)
            
            # Append to existing cache or create new
            if os.path.exists(self.cache_file):
                existing_cache = pd.read_parquet(self.cache_file)
                # Remove old entries for same tags/timestamps
                existing_cache = existing_cache[~(
                    (existing_cache['TagId'].isin(tags)) & 
                    (existing_cache['Timestamp'].isin(cache_df['Timestamp']))
                )]
                cache_df = pd.concat([existing_cache, cache_df], ignore_index=True)
            
            cache_df.to_parquet(self.cache_file, index=False)
            print(f"✓ Saved {len(interpolated_records)} interpolated points to cache")
            
            # Update metadata
            self.metadata['interpolation_runs'].append({
                'timestamp': datetime.now().isoformat(),
                'method': method,
                'tags': tags,
                'points_interpolated': len(interpolated_records),
                'log': interpolation_log
            })
            self.metadata['statistics']['total_interpolated_points'] += len(interpolated_records)
            self.metadata['statistics']['tags_affected'] = list(set(
                self.metadata['statistics']['tags_affected'] + tags
            ))
            self._save_metadata()
        
        return {
            'interpolated_count': len(interpolated_records),
            'log': interpolation_log,
            'cache_file': self.cache_file
        }
    
    def get_merged_data(self, original_data, use_interpolated=True):
        """
        Merge original data with interpolation cache
        
        Args:
            original_data: DataFrame from original parquet (READ-ONLY)
            use_interpolated: If True, use interpolated values; if False, use original
            
        Returns:
            DataFrame with merged data (COPY, original untouched)
        """
        # CRITICAL: Always work on copy
        result = original_data.copy()
        
        if not use_interpolated or not os.path.exists(self.cache_file):
            # Return original data as-is
            return result
        
        # Load interpolation cache
        cache_df = pd.read_parquet(self.cache_file)
        
        # Create lookup dictionary for fast merging
        # Key: (TagId, Timestamp) -> InterpolatedValue
        interpolation_map = {}
        for _, row in cache_df.iterrows():
            key = (row['TagId'], pd.to_datetime(row['Timestamp']))
            interpolation_map[key] = row['InterpolatedValue']
        
        # Apply interpolated values
        def apply_interpolation(row):
            key = (row['TagId'], pd.to_datetime(row['Timestamp']))
            if key in interpolation_map:
                return interpolation_map[key]
            return row['Value']
        
        result['Value'] = result.apply(apply_interpolation, axis=1)
        
        print(f"✓ Applied {len(interpolation_map)} interpolated values")
        return result
    
    def get_cache_statistics(self):
        """Get interpolation cache statistics"""
        stats = {
            'cache_exists': os.path.exists(self.cache_file),
            'cache_size_mb': 0,
            'total_cached_points': 0,
            'metadata': self.metadata
        }
        
        if os.path.exists(self.cache_file):
            stats['cache_size_mb'] = os.path.getsize(self.cache_file) / (1024 * 1024)
            cache_df = pd.read_parquet(self.cache_file)
            stats['total_cached_points'] = len(cache_df)
            stats['tags_in_cache'] = cache_df['TagId'].unique().tolist()
            stats['date_range'] = {
                'start': cache_df['Timestamp'].min().isoformat(),
                'end': cache_df['Timestamp'].max().isoformat()
            }
        
        return stats
    
    def clear_cache(self, tags=None):
        """
        Clear interpolation cache
        
        Args:
            tags: If specified, clear only these tags; if None, clear all
        """
        if not os.path.exists(self.cache_file):
            return
        
        if tags is None:
            # Clear entire cache
            os.remove(self.cache_file)
            print("✓ Cleared entire interpolation cache")
        else:
            # Clear specific tags
            cache_df = pd.read_parquet(self.cache_file)
            cache_df = cache_df[~cache_df['TagId'].isin(tags)]
            
            if len(cache_df) > 0:
                cache_df.to_parquet(self.cache_file, index=False)
                print(f"✓ Cleared cache for tags: {', '.join(tags)}")
            else:
                os.remove(self.cache_file)
                print("✓ Cleared entire cache (no data remaining)")
        
        # Update metadata
        self.metadata['statistics']['total_interpolated_points'] = 0
        self.metadata['statistics']['tags_affected'] = []
        self._save_metadata()
    
    def export_interpolation_report(self, output_file):
        """Export detailed interpolation report"""
        if not os.path.exists(self.cache_file):
            return None
        
        cache_df = pd.read_parquet(self.cache_file)
        
        # Create detailed report
        report = {
            'summary': self.get_cache_statistics(),
            'by_tag': {},
            'by_method': {}
        }
        
        # Group by tag
        for tag in cache_df['TagId'].unique():
            tag_data = cache_df[cache_df['TagId'] == tag]
            report['by_tag'][tag] = {
                'total_interpolated': len(tag_data),
                'methods_used': tag_data['Method'].unique().tolist(),
                'date_range': {
                    'start': tag_data['Timestamp'].min().isoformat(),
                    'end': tag_data['Timestamp'].max().isoformat()
                }
            }
        
        # Group by method
        for method in cache_df['Method'].unique():
            method_data = cache_df[cache_df['Method'] == method]
            report['by_method'][method] = {
                'total_points': len(method_data),
                'tags_affected': method_data['TagId'].unique().tolist()
            }
        
        # Save report
        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"✓ Interpolation report saved to {output_file}")
        return report
