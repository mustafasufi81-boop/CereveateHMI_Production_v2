"""
Test script to verify Grouped Bar chart data structure
"""
import pandas as pd
import os
from parquet_service import ParquetDataService

# Initialize service
data_dir = "D:\\OpcLogs\\Data"
service = ParquetDataService(data_dir)

# Get sample data
from datetime import datetime, timedelta
end_date = datetime.now()
start_date = end_date - timedelta(hours=24)

print("=" * 60)
print("Testing Grouped Bar Data Structure")
print("=" * 60)

try:
    # Load data
    df = service.read_parquet_files(
        start_date.strftime('%Y-%m-%d %H:%M:%S'),
        end_date.strftime('%Y-%m-%d %H:%M:%S')
    )
    
    print(f"\n✅ Loaded {len(df)} rows")
    print(f"✅ Columns: {list(df.columns)[:10]}...")  # Show first 10 columns
    
    # Convert to JSON-like structure (what JavaScript receives)
    data_json = df.to_dict('records')
    
    print(f"\n✅ Converted to {len(data_json)} records")
    
    if len(data_json) > 0:
        first_row = data_json[0]
        print(f"\n📊 First row keys: {list(first_row.keys())[:10]}")
        print(f"\n🔍 First row sample:")
        for i, (key, value) in enumerate(list(first_row.items())[:5]):
            print(f"   {key}: {type(value).__name__} = {value}")
        
        # Check numeric fields
        numeric_fields = []
        for key, value in first_row.items():
            if key.lower() != 'timestamp' and isinstance(value, (int, float)) and not pd.isna(value):
                numeric_fields.append(key)
        
        print(f"\n✅ Found {len(numeric_fields)} numeric fields:")
        for field in numeric_fields[:6]:
            values = [row.get(field) for row in data_json if field in row and not pd.isna(row.get(field))]
            if values:
                print(f"   {field}: min={min(values):.2f}, max={max(values):.2f}, count={len(values)}")
    
    print("\n" + "=" * 60)
    print("✅ Test Complete - Data structure looks good!")
    print("=" * 60)
    
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
