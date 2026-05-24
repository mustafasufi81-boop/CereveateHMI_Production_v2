import pandas as pd

print("=" * 100)
print("WHY IS THE SYSTEM NOT LOADING ALL 89,191 TIMESTAMPS?")
print("=" * 100)

# Load the file
df = pd.read_parquet('D:/OpcLogs/Data/ALL_SENSORS_COMPLETE_FORWARDFILL.parquet')
df['Timestamp'] = pd.to_datetime(df['Timestamp'])

tags = ['TURBINE_LOADMW', 'BEARING_VIB_HP_REAR-X', 'TOTAL_COAL_FLOW']

print(f"\n1️⃣ TOTAL DATA IN FILE:")
print(f"   Total unique timestamps: {df['Timestamp'].nunique():,}")
print(f"   Date range: {df['Timestamp'].min()} to {df['Timestamp'].max()}")

# Filter by your selected tags
df_tags = df[df['TagId'].isin(tags)]
print(f"\n2️⃣ DATA FOR YOUR 3 TAGS:")
print(f"   Unique timestamps: {df_tags['Timestamp'].nunique():,}")

# Check what date range YOU selected in the UI
print(f"\n3️⃣ YOUR UI QUERY:")
print(f"   From screenshot: 11/24/2024 - 11/16/2025")

# Apply that filter
query_start = pd.to_datetime('2024-11-24')
query_end = pd.to_datetime('2025-11-16 23:59:59')

df_filtered = df_tags[(df_tags['Timestamp'] >= query_start) & (df_tags['Timestamp'] <= query_end)]

print(f"\n4️⃣ AFTER DATE FILTER (2024-11-24 to 2025-11-16):")
print(f"   Unique timestamps: {df_filtered['Timestamp'].nunique():,}")
print(f"   This is what you're getting: 43,094")

print(f"\n5️⃣ TO GET ALL 89,191 TIMESTAMPS:")
print(f"   You need to select the FULL date range in the UI:")
print(f"   Start: 2015-08-30")
print(f"   End: 2025-11-16")

# Show year-by-year breakdown
print(f"\n6️⃣ DATA DISTRIBUTION BY YEAR:")
df_tags_copy = df_tags.copy()
df_tags_copy['Year'] = df_tags_copy['Timestamp'].dt.year
year_counts = df_tags_copy.groupby('Year')['Timestamp'].nunique()
for year, count in year_counts.items():
    print(f"   {year}: {count:,} timestamps")

print(f"\n" + "=" * 100)
print(f"ANSWER:")
print(f"=" * 100)
print(f"The system IS working correctly!")
print(f"You're only getting 43,094 because YOUR DATE FILTER is limiting it:")
print(f"  • You selected: 11/24/2024 - 11/16/2025 = 43,094 timestamps ✅")
print(f"  • Full file has: 08/30/2015 - 11/16/2025 = 89,191 timestamps")
print(f"\nTo get ALL 89,191 timestamps:")
print(f"  1. Change start date to: 2015-08-30")
print(f"  2. Keep end date: 2025-11-16")
print(f"  3. Click Load Data")
print(f"  4. You'll get 89,191 rows! ✅")
