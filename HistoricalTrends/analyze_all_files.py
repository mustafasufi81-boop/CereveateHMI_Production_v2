import pandas as pd
import glob
from collections import defaultdict
import sys
import os

# Add parent directory to path to import config_reader
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config_reader import ConfigReader

# Get the correct path from config
config = ConfigReader()
data_dir = config.get_data_directory()
print(f'Using data directory from config: {data_dir}')

files = sorted(glob.glob(os.path.join(data_dir, '*.parquet')))
print(f'Total files: {len(files)}')

all_tags = set()
tags_per_file = []
file_details = []

print('\n--- Analyzing ALL files ---')
for idx, f in enumerate(files):
    df = pd.read_parquet(f)
    unique_tags = df['TagId'].unique()
    all_tags.update(unique_tags)
    tags_per_file.append(len(unique_tags))
    
    file_details.append({
        'file': f.split('\\')[-1],
        'rows': len(df),
        'tags': len(unique_tags),
        'tag_list': list(unique_tags),
        'time_range': (df['Timestamp'].min(), df['Timestamp'].max())
    })

print(f'\n=== SUMMARY ===')
print(f'Total unique tags across all files: {len(all_tags)}')
print(f'Min tags per file: {min(tags_per_file)}')
print(f'Max tags per file: {max(tags_per_file)}')
print(f'Avg tags per file: {sum(tags_per_file)/len(tags_per_file):.1f}')

print(f'\n=== ALL UNIQUE TAGS ===')
for tag in sorted(all_tags):
    print(f'  {tag}')

print(f'\n=== FILES WITH MOST TAGS ===')
sorted_details = sorted(file_details, key=lambda x: x['tags'], reverse=True)
for detail in sorted_details[:10]:
    print(f"\n{detail['file']}:")
    print(f"  Rows: {detail['rows']}, Tags: {detail['tags']}")
    print(f"  Tags: {detail['tag_list']}")

print(f'\n=== TAG DISTRIBUTION ACROSS FILES ===')
tag_file_count = defaultdict(int)
for detail in file_details:
    for tag in detail['tag_list']:
        tag_file_count[tag] += 1

for tag in sorted(tag_file_count.keys()):
    print(f'  {tag}: appears in {tag_file_count[tag]} files')
