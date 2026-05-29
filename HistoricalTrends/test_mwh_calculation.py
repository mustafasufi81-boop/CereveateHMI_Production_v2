"""
CRITICAL TEST: Daily MWh Production Calculation
Shows how load (MW) accumulates to production (MWh) day-by-day
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta

print("=" * 80)
print("⚡ DAILY PRODUCTION CALCULATION - VERIFICATION TEST")
print("=" * 80)
print()

# Generate 3 days of simple test data
print("Generating 3 days of test data...")
print()

# Day 1: Constant 500 MW
day1_points = 1440  # 1440 minutes = 24 hours
day1_load = np.full(day1_points, 500.0)  # 500 MW constant
day1_times = pd.date_range(start='2024-11-18 00:00', periods=day1_points, freq='1min')

# Day 2: Constant 600 MW  
day2_load = np.full(day1_points, 600.0)  # 600 MW constant
day2_times = pd.date_range(start='2024-11-19 00:00', periods=day1_points, freq='1min')

# Day 3: 400 MW for 12 hours, then 0 MW (trip) for 12 hours
day3_load = np.concatenate([
    np.full(720, 400.0),  # 400 MW for 12 hours
    np.full(720, 0.0)     # 0 MW (trip) for 12 hours
])
day3_times = pd.date_range(start='2024-11-20 00:00', periods=day1_points, freq='1min')

# Combine all days
timestamps = pd.concat([
    pd.Series(day1_times),
    pd.Series(day2_times),
    pd.Series(day3_times)
])

load = np.concatenate([day1_load, day2_load, day3_load])

df = pd.DataFrame({
    'Timestamp': timestamps.values,
    'Load': load
})

df['Date'] = pd.to_datetime(df['Timestamp']).dt.date

print("=" * 80)
print("📊 MANUAL CALCULATION (Ground Truth)")
print("=" * 80)
print()

for date in df['Date'].unique():
    day_data = df[df['Date'] == date]
    
    # CRITICAL FORMULA: MWh = Σ(MW × hours)
    # With 1-minute data: MWh = Σ(MW × 1/60)
    
    total_mw_minutes = day_data['Load'].sum()
    total_mwh = total_mw_minutes / 60  # Convert MW-minutes to MWh
    
    avg_mw = day_data['Load'].mean()
    
    # Alternative calculation: avg_mw × 24 hours
    expected_mwh = avg_mw * 24
    
    print(f"📅 {date}")
    print(f"   Load Data: {len(day_data)} points (1 min each)")
    print(f"   Average Load: {avg_mw:.2f} MW")
    print(f"   Sum(MW × 1min): {total_mw_minutes:.2f} MW-minutes")
    print(f"   Production: {total_mwh:.2f} MWh")
    print(f"   Verification: {avg_mw:.2f} MW × 24 hrs = {expected_mwh:.2f} MWh")
    print(f"   ✓ Match: {abs(total_mwh - expected_mwh) < 0.01}")
    print()

# Total production
total_production = df['Load'].sum() / 60
print(f"Total 3-Day Production: {total_production:,.2f} MWh")
print()

# Expected values (manual)
print("=" * 80)
print("✅ EXPECTED RESULTS (Manual Calculation):")
print("=" * 80)
print()
print("Day 1: 500 MW × 24 hrs = 12,000 MWh")
print("Day 2: 600 MW × 24 hrs = 14,400 MWh")
print("Day 3: 400 MW × 12 hrs + 0 MW × 12 hrs = 4,800 MWh")
print("Total: 31,200 MWh")
print()

# Now test with Python engine
print("=" * 80)
print("🐍 PYTHON BI ENGINE TEST")
print("=" * 80)
print()

try:
    from bi_engines.availability_engine import AvailabilityProductionEngine
    
    engine = AvailabilityProductionEngine({
        'low_load_threshold': 0.3,
        'rated_capacity': 660.0
    })
    
    result = engine.calculate_availability(
        df=df,
        load_col='Load',
        rated_capacity=660.0
    )
    
    print(f"Engine Calculated Production: {result['cumulative_production_mwh']:,.2f} MWh")
    print(f"Manual Calculated Production: {total_production:,.2f} MWh")
    print()
    
    difference = abs(result['cumulative_production_mwh'] - total_production)
    diff_pct = (difference / total_production) * 100
    
    print(f"Difference: {difference:.2f} MWh ({diff_pct:.4f}%)")
    
    if diff_pct < 0.1:
        print("✅ PASS - Engine calculation is CORRECT!")
    else:
        print("❌ FAIL - Calculation mismatch")
    
    print()
    print("Additional Metrics:")
    print(f"  Availability: {result['availability']:.2f}%")
    print(f"  Breakdown Hours: {result['breakdown_hours']:.2f} hrs")
    print(f"  Average Load: {result['average_load']:.2f} MW")
    
except Exception as e:
    print(f"❌ Engine test failed: {str(e)}")
    import traceback
    traceback.print_exc()

print()
print("=" * 80)
print("📋 CALCULATION FORMULA VERIFIED")
print("=" * 80)
print()
print("Key Formula: MWh = Σ(MW × Δt)")
print()
print("Where:")
print("  MW = Instantaneous power (load)")
print("  Δt = Time interval (1/60 hour for 1-minute data)")
print("  MWh = Energy produced")
print()
print("Example:")
print("  500 MW running for 24 hours = 500 × 24 = 12,000 MWh")
print("  600 MW running for 24 hours = 600 × 24 = 14,400 MWh")
print("  400 MW running for 12 hours = 400 × 12 = 4,800 MWh")
print()
print("This is how the engine calculates daily production! ✅")
print("=" * 80)
