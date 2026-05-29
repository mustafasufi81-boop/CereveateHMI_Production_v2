"""
Test CSV download to verify full file is converted
"""
import requests
import pandas as pd
import glob

# Get the latest parquet file
files = sorted(glob.glob('D:/OpcLogs/Data/*.parquet'))
if not files:
    print("No parquet files found")
    exit(1)

latest_file = files[-1]
filename = latest_file.split('\\')[-1]

print(f"Testing CSV download for: {filename}")

# Read original parquet file to get row count
df_original = pd.read_parquet(latest_file)
original_rows = len(df_original)
print(f"Original parquet file has {original_rows} rows")

# Test the API endpoint
url = "http://localhost:5003/api/parquet/convert_to_csv"
payload = {
    "filename": filename
}

print(f"\nCalling API: {url}")
response = requests.post(url, json=payload, stream=True)

if response.status_code == 200:
    # Save the downloaded CSV
    csv_filename = f"test_download_{filename.replace('.parquet', '.csv')}"
    with open(csv_filename, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    
    print(f"✓ CSV downloaded: {csv_filename}")
    
    # Read the CSV and check row count
    df_csv = pd.read_csv(csv_filename)
    csv_rows = len(df_csv)
    
    print(f"\n=== COMPARISON ===")
    print(f"Parquet rows: {original_rows}")
    print(f"CSV rows:     {csv_rows}")
    
    if csv_rows == original_rows:
        print("✓ SUCCESS: All rows converted!")
    else:
        print(f"✗ MISMATCH: {original_rows - csv_rows} rows missing")
else:
    print(f"✗ API Error: {response.status_code}")
    print(response.text)
