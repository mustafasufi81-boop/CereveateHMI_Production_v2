import pandas as pd
import pyarrow.dataset as ds
import os
import json
from datetime import datetime, timedelta
from pathlib import Path
import io
import glob
import numpy as np

class ParquetDataService:
    """Service to read and process parquet files with intelligent caching"""
    
    def __init__(self, data_directory, backup_directory=None):
        self.data_directory = data_directory
        self.backup_directory = backup_directory
        self.cache_file = os.path.join(os.path.dirname(__file__), 'file_index_cache.json')
        self.file_index = {}  # {filename: {tags: [], start: "", end: "", path: ""}}
        self.tag_index = {}   # {tag_name: [filenames]}
        self.cache_loaded = False
        
        # Load or build cache
        self._init_cache()
    
    
    def _init_cache(self):
        """Initialize cache - load from disk or build new"""
        if self._load_cache_from_disk():
            if self._is_cache_valid():
                print(f"✓ Cache loaded: {len(self.tag_index)} tags, {len(self.file_index)} files")
                self.cache_loaded = True
                return
        
        print("Building file index cache...")
        self._build_cache()
    
    def _build_cache(self):
        """Scan all parquet files and build index"""
        self.file_index = {}
        self.tag_index = {}
        
        files = glob.glob(os.path.join(self.data_directory, '*.parquet'))
        
        for idx, file_path in enumerate(files):
            try:
                # Read only metadata columns (fast, no data loading)
                df = pd.read_parquet(file_path, columns=['TagId', 'Timestamp'])
                
                if df.empty:
                    continue
                
                filename = os.path.basename(file_path)
                unique_tags = df['TagId'].unique().tolist()
                time_start = df['Timestamp'].min().isoformat()
                time_end = df['Timestamp'].max().isoformat()
                
                # Store in file_index
                self.file_index[filename] = {
                    'tags': unique_tags,
                    'start': time_start,
                    'end': time_end,
                    'path': file_path
                }
                
                # Store in tag_index (reverse mapping)
                for tag in unique_tags:
                    if tag not in self.tag_index:
                        self.tag_index[tag] = []
                    self.tag_index[tag].append(filename)
                
                if (idx + 1) % 25 == 0:
                    print(f"  Indexed {idx + 1}/{len(files)} files...")
                    
            except Exception as e:
                print(f"  Error indexing {file_path}: {e}")
                continue
        
        print(f"✓ Cache built: {len(self.tag_index)} tags, {len(self.file_index)} files")
        self._save_cache_to_disk()
        self.cache_loaded = True
    
    def _save_cache_to_disk(self):
        """Save cache to JSON file"""
        cache_data = {
            'file_index': self.file_index,
            'tag_index': self.tag_index,
            'data_directory': self.data_directory,
            'last_updated': datetime.now().isoformat()
        }
        
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2)
            print(f"✓ Cache saved to {self.cache_file}")
        except Exception as e:
            print(f"⚠ Failed to save cache: {e}")
    
    def _load_cache_from_disk(self):
        """Load cache from JSON file"""
        if not os.path.exists(self.cache_file):
            return False
        
        try:
            with open(self.cache_file, 'r') as f:
                cache_data = json.load(f)
            
            if cache_data.get('data_directory') != self.data_directory:
                return False
            
            self.file_index = cache_data.get('file_index', {})
            self.tag_index = cache_data.get('tag_index', {})
            return True
        except Exception as e:
            print(f"⚠ Failed to load cache: {e}")
            return False
    
    def _is_cache_valid(self):
        """Check if cache matches current files"""
        current_files = set(os.path.basename(f) for f in glob.glob(os.path.join(self.data_directory, '*.parquet')))
        cached_files = set(self.file_index.keys())
        return current_files == cached_files
    
    def get_available_tags(self):
        """Get list of all available tags from cache"""
        if not self.cache_loaded:
            self._init_cache()
        
        return sorted(self.tag_index.keys())

    def get_available_files(self):
        """Get list of all available parquet files with metadata"""
        files = []
        if os.path.exists(self.data_directory):
            files.extend(self._scan_directory(self.data_directory, 'primary'))
        if self.backup_directory and os.path.exists(self.backup_directory):
            files.extend(self._scan_directory(self.backup_directory, 'backup'))
        files.sort(key=lambda x: x['timestamp'], reverse=True)
        return files
    
    def _get_relevant_files(self, start_date, end_date, tags):
        """Get list of files that contain requested tags and overlap with time range"""
        if not self.cache_loaded:
            self._init_cache()
        
        # Step 1: Find files containing requested tags
        candidate_files = set()
        for tag in tags:
            if tag in self.tag_index:
                candidate_files.update(self.tag_index[tag])
        
        if not candidate_files:
            return []
        
        # Step 2: Filter by time range
        start_dt = pd.to_datetime(start_date.replace('Z', ''))
        end_dt = pd.to_datetime(end_date.replace('Z', ''))
        
        relevant_files = []
        for filename in candidate_files:
            file_meta = self.file_index.get(filename)
            if not file_meta:
                continue
            
            file_start = pd.to_datetime(file_meta['start'])
            file_end = pd.to_datetime(file_meta['end'])
            
            # Check time overlap
            if file_start <= end_dt and file_end >= start_dt:
                relevant_files.append(file_meta['path'])
        
        print(f"✓ Optimized query: {len(relevant_files)}/{len(self.file_index)} files needed for {len(tags)} tags")
        return relevant_files
    
    def _scan_directory(self, directory, source):
        """Scan directory for parquet files"""
        files = []
        try:
            for file in Path(directory).glob('*.parquet'):
                try:
                    stat = file.stat()
                    # Try to extract date from filename (OpcData_YYYYMMDD_HHMMSS.parquet)
                    filename = file.stem
                    file_date = None
                    
                    if '_' in filename:
                        parts = filename.split('_')
                        if len(parts) >= 2:
                            try:
                                date_str = parts[1]
                                time_str = parts[2] if len(parts) > 2 else '000000'
                                file_date = datetime.strptime(f"{date_str}_{time_str}", "%Y%m%d_%H%M%S")
                            except:
                                file_date = datetime.fromtimestamp(stat.st_mtime)
                    
                    if not file_date:
                        file_date = datetime.fromtimestamp(stat.st_mtime)
                    
                    files.append({
                        'filename': file.name,
                        'path': str(file),
                        'size': stat.st_size,
                        'timestamp': file_date.isoformat(),
                        'source': source,
                        'size_mb': round(stat.st_size / (1024 * 1024), 2)
                    })
                except Exception as e:
                    print(f"Error processing file {file}: {e}")
                    continue
        except Exception as e:
            print(f"Error scanning directory {directory}: {e}")
        
        return files
    
    def read_parquet_data(self, start_date=None, end_date=None, tags=None, max_points=None):
        """Read parquet files within date range and filter by tags with predicate pushdown"""
        import time
        start_time = time.time()

        if not start_date or not end_date:
            print("⚠ Start/end date missing; returning empty set")
            return pd.DataFrame()

        if not tags:
            tags = self.get_available_tags()

        file_paths = self._get_relevant_files(start_date, end_date, tags)
        if not file_paths:
            print("⚠ No relevant files found for query")
            return pd.DataFrame()

        start_dt = pd.to_datetime(start_date.replace('Z', ''))
        end_dt = pd.to_datetime(end_date.replace('Z', ''))

        # Use pyarrow dataset to push filters to row groups and avoid full file reads
        filter_expr = (
            (ds.field('Timestamp') >= start_dt) &
            (ds.field('Timestamp') <= end_dt) &
            (ds.field('TagId').isin(tags))
        )

        try:
            dataset = ds.dataset(file_paths, format='parquet')
            table = dataset.to_table(columns=['Timestamp', 'TagId', 'Value'], filter=filter_expr, use_threads=True)
            df = table.to_pandas()
        except Exception as e:
            print(f"⚠ Dataset read failed, falling back to pandas: {e}")
            df = self._fallback_read(file_paths, tags, start_dt, end_dt)

        if df.empty:
            print("⚠ No data found in files")
            return pd.DataFrame()

        df['Timestamp'] = pd.to_datetime(df['Timestamp'])

        # Pivot for charting
        print(f"🔄 Pivoting {len(df)} rows...")
        result_df = df.pivot_table(index='Timestamp', columns='TagId', values='Value', aggfunc='first').reset_index()
        result_df = result_df.sort_values('Timestamp')

        if max_points and len(result_df) > max_points:
            # Remove rows where all selected tags are NaN to avoid empty traces after sampling
            original_len = len(result_df)
            pruned_df = result_df.dropna(how='all', subset=tags)

            if pruned_df.empty:
                # Fallback: keep one non-NaN row per tag if available, else keep head
                fallback_rows = []
                for tag in tags:
                    non_na_idx = result_df.index[result_df[tag].notna()].to_numpy()
                    if non_na_idx.size > 0:
                        fallback_rows.append(result_df.loc[non_na_idx[0]])
                if fallback_rows:
                    pruned_df = pd.DataFrame(fallback_rows).drop_duplicates().reset_index(drop=True)
                else:
                    pruned_df = result_df.head(max_points).reset_index(drop=True)

            result_df = pruned_df

            if len(result_df) > max_points:
                keep_indices = set()

                # Base even spread sample
                base_idx = np.linspace(0, len(result_df) - 1, num=max_points // 2, dtype=int)
                keep_indices.update(base_idx.tolist())

                # Ensure each tag contributes non-NaN points if available
                per_tag_quota = max(3, max_points // max(len(tags), 1))
                for tag in tags:
                    non_na_idx = result_df.index[result_df[tag].notna()].to_numpy()
                    if non_na_idx.size == 0:
                        continue
                    sample_count = min(per_tag_quota, non_na_idx.size)
                    sample_positions = np.linspace(0, non_na_idx.size - 1, num=sample_count, dtype=int)
                    keep_indices.update(non_na_idx[sample_positions].tolist())

                # Trim to max_points and sort
                keep_indices = sorted(list(keep_indices))[:max_points]
                result_df = result_df.iloc[keep_indices].reset_index(drop=True)

            print(f"🔻 Downsampled to {len(result_df)} points (pruned {original_len - len(result_df)} rows, limit {max_points})")

        elapsed = time.time() - start_time
        print(f"✅ Data loaded: {len(result_df)} rows × {len(tags)} tags in {elapsed:.2f}s")
        return result_df

    def _fallback_read(self, file_paths, tags, start_dt, end_dt):
        """Fallback reader using pandas if dataset scan fails"""
        all_dataframes = []
        for file_path in file_paths:
            try:
                df = pd.read_parquet(file_path, columns=['TagId', 'Timestamp', 'Value'])
                if df.empty:
                    continue
                df = df[df['TagId'].isin(tags)]
                if df.empty:
                    continue
                df['Timestamp'] = pd.to_datetime(df['Timestamp'])
                df = df[(df['Timestamp'] >= start_dt) & (df['Timestamp'] <= end_dt)]
                if not df.empty:
                    all_dataframes.append(df)
                    print(f"  ✓ {os.path.basename(file_path)}: {len(df)} rows (fallback)")
            except Exception as e:
                print(f"❌ Error reading {os.path.basename(file_path)}: {e}")
                continue

        if not all_dataframes:
            return pd.DataFrame()

        return pd.concat(all_dataframes, ignore_index=True)
    
    def export_to_csv(self, start_date=None, end_date=None, tags=None):
        """Export data to CSV format"""
        df = self.read_parquet_data(start_date, end_date, tags)
        
        if df.empty:
            return None
        
        # Convert to CSV
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False)
        return csv_buffer.getvalue()
    
    def export_to_excel(self, start_date=None, end_date=None, tags=None):
        """Export data to Excel format"""
        df = self.read_parquet_data(start_date, end_date, tags)
        
        if df.empty:
            return None
        
        # Convert to Excel
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Historical Data', index=False)
        
        excel_buffer.seek(0)
        return excel_buffer.getvalue()
    
    def get_data_summary(self, start_date=None, end_date=None):
        """Get summary statistics for data in date range"""
        df = self.read_parquet_data(start_date, end_date)
        
        if df.empty:
            return {}
        
        summary = {
            'total_records': len(df),
            'date_range': {
                'start': df['Timestamp'].min().isoformat() if 'Timestamp' in df.columns else None,
                'end': df['Timestamp'].max().isoformat() if 'Timestamp' in df.columns else None
            },
            'tags': []
        }
        
        # Get statistics for each tag
        for col in df.columns:
            if col != 'Timestamp':
                try:
                    col_data = pd.to_numeric(df[col], errors='coerce')
                    summary['tags'].append({
                        'name': col,
                        'min': float(col_data.min()) if not col_data.isna().all() else None,
                        'max': float(col_data.max()) if not col_data.isna().all() else None,
                        'avg': float(col_data.mean()) if not col_data.isna().all() else None,
                        'count': int(col_data.count())
                    })
                except:
                    continue
        
        return summary
    
    def get_files_for_date_range(self, start_date, end_date):
        """Get list of parquet files that contain data in date range"""
        if not self.cache_loaded:
            self._build_cache()
        
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)
        
        matching_files = []
        
        for filename, file_info in self.file_index.items():
            file_start = pd.to_datetime(file_info['start'])
            file_end = pd.to_datetime(file_info['end'])
            
            # Check if file overlaps with requested range
            if file_end >= start_dt and file_start <= end_dt:
                matching_files.append(file_info['path'])
        
        return matching_files
