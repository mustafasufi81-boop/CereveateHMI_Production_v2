"""
Tag Cache Manager - Builds and maintains cache of all tags across parquet files
"""
import pandas as pd
import glob
import os
from datetime import datetime
from typing import Dict, List, Set, Tuple
import json

class TagCache:
    def __init__(self, data_directory: str):
        self.data_directory = data_directory
        self.cache = {}  # {tag_name: [file_path1, file_path2, ...]}
        self.file_metadata = {}  # {file_path: {'tags': [], 'time_range': (start, end), 'rows': count}}
        self.cache_file = os.path.join(os.path.dirname(__file__), 'tag_cache.json')
        self.last_scan = None
        
    def build_cache(self) -> Dict[str, List[str]]:
        """Build complete tag cache by scanning all parquet files"""
        print("Building tag cache...")
        files = sorted(glob.glob(os.path.join(self.data_directory, '*.parquet')))
        
        if not files:
            print(f"No parquet files found in {self.data_directory}")
            return {}
        
        self.cache = {}
        self.file_metadata = {}
        
        for idx, file_path in enumerate(files):
            try:
                # Read only metadata first (no data loading)
                df = pd.read_parquet(file_path, columns=['TagId', 'Timestamp'])
                
                # Get unique tags in this file
                unique_tags = df['TagId'].unique().tolist()
                
                # Get time range
                time_min = df['Timestamp'].min()
                time_max = df['Timestamp'].max()
                
                # Store file metadata
                self.file_metadata[file_path] = {
                    'tags': unique_tags,
                    'time_range': (str(time_min), str(time_max)),
                    'rows': len(df)
                }
                
                # Index tags -> files
                for tag in unique_tags:
                    if tag not in self.cache:
                        self.cache[tag] = []
                    self.cache[tag].append(file_path)
                
                if (idx + 1) % 20 == 0:
                    print(f"  Processed {idx + 1}/{len(files)} files...")
                    
            except Exception as e:
                print(f"  Error processing {file_path}: {e}")
                continue
        
        self.last_scan = datetime.now().isoformat()
        print(f"Cache built: {len(self.cache)} unique tags across {len(files)} files")
        
        # Save cache to disk
        self._save_cache()
        
        return self.cache
    
    def _save_cache(self):
        """Save cache to disk for fast reload"""
        cache_data = {
            'cache': self.cache,
            'file_metadata': self.file_metadata,
            'last_scan': self.last_scan
        }
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2)
            print(f"Cache saved to {self.cache_file}")
        except Exception as e:
            print(f"Failed to save cache: {e}")
    
    def _load_cache(self) -> bool:
        """Load cache from disk if available"""
        if not os.path.exists(self.cache_file):
            return False
        
        try:
            with open(self.cache_file, 'r') as f:
                cache_data = json.load(f)
            
            self.cache = cache_data.get('cache', {})
            self.file_metadata = cache_data.get('file_metadata', {})
            self.last_scan = cache_data.get('last_scan')
            
            print(f"Cache loaded from disk: {len(self.cache)} tags")
            return True
        except Exception as e:
            print(f"Failed to load cache: {e}")
            return False
    
    def get_tags(self) -> List[str]:
        """Get all available tags (sorted)"""
        if not self.cache:
            if not self._load_cache():
                self.build_cache()
        
        return sorted(self.cache.keys())
    
    def get_files_for_tags(self, tags: List[str]) -> Set[str]:
        """Get all files that contain any of the requested tags"""
        if not self.cache:
            if not self._load_cache():
                self.build_cache()
        
        files = set()
        for tag in tags:
            if tag in self.cache:
                files.update(self.cache[tag])
        
        return files
    
    def get_files_for_time_range(self, start_date: datetime, end_date: datetime, tags: List[str] = None) -> Set[str]:
        """Get files that overlap with the time range and contain requested tags"""
        if not self.cache:
            if not self._load_cache():
                self.build_cache()
        
        # First filter by tags if provided
        if tags:
            candidate_files = self.get_files_for_tags(tags)
        else:
            candidate_files = set(self.file_metadata.keys())
        
        # Then filter by time range
        relevant_files = set()
        for file_path in candidate_files:
            if file_path not in self.file_metadata:
                continue
            
            file_start = pd.to_datetime(self.file_metadata[file_path]['time_range'][0])
            file_end = pd.to_datetime(self.file_metadata[file_path]['time_range'][1])
            
            # Check if file time range overlaps with requested range
            if file_start <= end_date and file_end >= start_date:
                relevant_files.add(file_path)
        
        return relevant_files
    
    def refresh_if_needed(self):
        """Rebuild cache if new files detected"""
        current_files = set(glob.glob(os.path.join(self.data_directory, '*.parquet')))
        cached_files = set(self.file_metadata.keys())
        
        if current_files != cached_files:
            print("New files detected, rebuilding cache...")
            self.build_cache()
