"""
Test baseline API with historical date range
Date Range: December 8, 2024 to February 9, 2025
"""

import requests
import json
from datetime import datetime, timedelta
import pandas as pd

# API endpoint
API_URL = "http://localhost:5002/api/v1/baseline/calculate"
DATA_URL = "http://localhost:5002/api/data"

# Date range
START_DATE = "2024-12-08"
END_DATE = "2025-02-09"

print("=" * 60)
print("BASELINE API TEST - HISTORICAL DATA")
print("=" * 60)
print(f"Date Range: {START_DATE} to {END_DATE}")
print()

# Step 1: Fetch data from the main API
print("Step 1: Fetching data from main API...")
params = {
    'start_date': f"{START_DATE}T00:00:00.000Z",
    'end_date': f"{END_DATE}T23:59:59.000Z",
    'tags': json.dumps(["TURBINE_LOADMW", "TOTAL_COAL_FLOW", "MS_TEMPERATURE"])
}

try:
    response = requests.get(DATA_URL, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()
    print(f"✓ Received {len(data)} data points")
    
    if len(data) == 0:
        print("❌ ERROR: No data returned from API")
        exit(1)
    
    # Show first and last timestamps
    df = pd.DataFrame(data)
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])
    print(f"✓ First timestamp: {df['Timestamp'].min()}")
    print(f"✓ Last timestamp: {df['Timestamp'].max()}")
    print(f"✓ Columns: {list(df.columns)}")
    print()
    
except Exception as e:
    print(f"❌ ERROR fetching data: {e}")
    exit(1)

# Step 2: Test baseline calculation
print("Step 2: Testing baseline calculation API...")
payload = {
    "data": data,
    "tag": "TURBINE_LOADMW"
}

try:
    headers = {'Content-Type': 'application/json'}
    response = requests.post(API_URL, json=payload, headers=headers, timeout=30)
    
    print(f"Response Status: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print("✓ SUCCESS - Baseline calculated!")
        print()
        print("Baseline Results:")
        print("-" * 60)
        baseline = result.get('baseline', {})
        print(f"  Value: {baseline.get('value', 0):.3f} MW")
        print(f"  Min: {baseline.get('min', 0):.3f} MW")
        print(f"  Max: {baseline.get('max', 0):.3f} MW")
        print(f"  Sample Size: {baseline.get('sample_size', 0)}")
        print(f"  Confidence: {baseline.get('confidence', 0):.1f}%")
        print(f"  Window Days: {baseline.get('window_days', 30)}")
        print(f"  Calculated At: {baseline.get('calculated_at', 'N/A')}")
        print()
    else:
        error_detail = response.json() if response.headers.get('content-type') == 'application/json' else response.text
        print(f"❌ ERROR: {error_detail}")
        
except Exception as e:
    print(f"❌ ERROR calling baseline API: {e}")
    exit(1)

print("=" * 60)
print("TEST COMPLETE")
print("=" * 60)
