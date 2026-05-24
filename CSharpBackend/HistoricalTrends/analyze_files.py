import pandas as pd
import glob
from datetime import datetime

files = sorted(glob.glob('D:/Logs/Data/OPC/*.parquet'))
print(f'Total files: {len(files)}')
print('\nFirst 5 files:')
for f in files[:5]:
    print(f'  {f}')
print('\nLast 5 files:')
for f in files[-5:]:
    print(f'  {f}')

print('\n--- Analyzing file structures ---')
sample_indices = [0, len(files)//2, -1]
for idx in sample_indices:
    f = files[idx]
    df = pd.read_parquet(f)
    print(f'\nFile: {f.split("/")[-1]}')
    print(f'  Rows: {len(df)}')
    print(f'  Columns: {list(df.columns)}')
    if 'TagId' in df.columns:
        unique_tags = df['TagId'].unique()
        print(f'  Unique tags: {len(unique_tags)}')
        print(f'  Sample tags: {list(unique_tags[:5])}')
    if 'Timestamp' in df.columns:
        print(f'  Time range: {df["Timestamp"].min()} to {df["Timestamp"].max()}')
