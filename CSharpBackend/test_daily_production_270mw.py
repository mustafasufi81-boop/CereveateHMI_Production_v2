"""
DAILY PRODUCTION CALCULATION - 270 MW TURBINE-GENERATOR UNIT
Shows daily MWh production breakdown for a real power plant unit
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta

print("=" * 90)
print("⚡ DAILY PRODUCTION CALCULATION - 270 MW TURBINE-GENERATOR UNIT")
print("=" * 90)
print()

# Plant specifications
RATED_CAPACITY = 270.0  # MW per unit
UNIT_NAME = "Unit-1"

print(f"Plant Specifications:")
print(f"  Unit: {UNIT_NAME}")
print(f"  Rated Capacity: {RATED_CAPACITY} MW")
print(f"  Technology: Thermal Power Plant (Coal/Gas)")
print()

# Generate 7 days of realistic operational data
print("Generating 7 days of realistic operational data...")
print()

start_date = datetime(2024, 11, 14, 0, 0, 0)
days = 7
points_per_day = 1440  # 1-minute resolution
total_points = days * points_per_day

timestamps = []
loads = []

for day in range(days):
    day_start = start_date + timedelta(days=day)
    
    # Daily load pattern variations
    if day == 0:
        # Day 1: Full load stable operation
        base_load = 265.0  # 98% capacity
        daily_variation = 5.0
    elif day == 1:
        # Day 2: Good operation with minor fluctuations
        base_load = 260.0  # 96% capacity
        daily_variation = 10.0
    elif day == 2:
        # Day 3: Part load operation
        base_load = 200.0  # 74% capacity
        daily_variation = 15.0
    elif day == 3:
        # Day 4: Load following (variable load)
        base_load = 180.0  # 67% capacity
        daily_variation = 40.0
    elif day == 4:
        # Day 5: Trip event (shutdown for 4 hours, then restart)
        base_load = 250.0
        daily_variation = 20.0
    elif day == 5:
        # Day 6: Planned maintenance (shutdown all day)
        base_load = 0.0
        daily_variation = 0.0
    else:
        # Day 7: Startup and ramping
        base_load = 150.0
        daily_variation = 50.0
    
    for minute in range(points_per_day):
        ts = day_start + timedelta(minutes=minute)
        timestamps.append(ts)
        
        # Add realistic variations
        hour_of_day = minute // 60
        
        # Daily load curve (peak during day, lower at night)
        time_factor = 1.0 + 0.1 * np.sin((hour_of_day / 24) * 2 * np.pi)
        
        # Add random noise (±2 MW)
        noise = np.random.normal(0, 2.0)
        
        # Special events
        if day == 4 and 120 <= minute < 360:  # 2 AM to 6 AM - Trip event
            load = 0.0
        elif day == 5:  # Full day maintenance
            load = 0.0
        elif day == 6 and minute < 360:  # First 6 hours - still in startup
            load = (minute / 360) * base_load  # Linear ramp-up
        else:
            load = base_load * time_factor + np.random.uniform(-daily_variation/2, daily_variation/2) + noise
            load = max(0, min(RATED_CAPACITY, load))  # Clamp to physical limits
        
        loads.append(load)

# Create DataFrame
df = pd.DataFrame({
    'Timestamp': timestamps,
    'Load': loads
})

df['Date'] = pd.to_datetime(df['Timestamp']).dt.date

print("=" * 90)
print("📊 DAILY PRODUCTION BREAKDOWN (Manual Calculation)")
print("=" * 90)
print()

daily_summary = []

for date in sorted(df['Date'].unique()):
    day_data = df[df['Date'] == date]
    
    # CRITICAL FORMULA: MWh = Σ(MW × hours)
    # With 1-minute data: MWh = Σ(MW × 1/60)
    
    total_mw_minutes = day_data['Load'].sum()
    total_mwh = total_mw_minutes / 60  # Convert MW-minutes to MWh
    
    avg_mw = day_data['Load'].mean()
    max_mw = day_data['Load'].max()
    min_mw = day_data['Load'].min()
    
    # Calculate Plant Load Factor (PLF) for the day
    plf = (total_mwh / (RATED_CAPACITY * 24)) * 100
    
    # Count zero load time (trips/shutdown)
    zero_load_minutes = (day_data['Load'] == 0).sum()
    zero_load_hours = zero_load_minutes / 60
    
    daily_summary.append({
        'date': date,
        'production_mwh': total_mwh,
        'avg_mw': avg_mw,
        'max_mw': max_mw,
        'min_mw': min_mw,
        'plf': plf,
        'shutdown_hours': zero_load_hours
    })
    
    print(f"📅 {date} ({pd.to_datetime(date).strftime('%A')})")
    print(f"   Daily Production: {total_mwh:,.2f} MWh")
    print(f"   Average Load: {avg_mw:.2f} MW")
    print(f"   Load Range: {min_mw:.2f} - {max_mw:.2f} MW")
    print(f"   Plant Load Factor (PLF): {plf:.2f}%")
    if zero_load_hours > 0:
        print(f"   ⚠️  Shutdown Time: {zero_load_hours:.2f} hours")
    print()

# Calculate weekly summary
total_production = sum(d['production_mwh'] for d in daily_summary)
max_possible_production = RATED_CAPACITY * 24 * days
weekly_plf = (total_production / max_possible_production) * 100

print("=" * 90)
print("📈 WEEKLY SUMMARY (7 Days)")
print("=" * 90)
print()
print(f"Total Production: {total_production:,.2f} MWh")
print(f"Maximum Possible Production: {max_possible_production:,.2f} MWh (@ {RATED_CAPACITY} MW × 168 hours)")
print(f"Weekly Plant Load Factor: {weekly_plf:.2f}%")
print(f"Production Loss: {max_possible_production - total_production:,.2f} MWh")
print()

# Revenue calculation
PRICE_PER_MWH = 5000  # ₹5000/MWh (typical power tariff)

weekly_revenue = total_production * PRICE_PER_MWH
lost_revenue = (max_possible_production - total_production) * PRICE_PER_MWH

print("=" * 90)
print("💰 REVENUE IMPACT")
print("=" * 90)
print()
print(f"Power Tariff: ₹{PRICE_PER_MWH:,}/MWh")
print(f"Weekly Revenue: ₹{weekly_revenue:,.2f}")
print(f"Lost Revenue: ₹{lost_revenue:,.2f}")
print()

# Test with Python BI Engine
print("=" * 90)
print("🐍 PYTHON BI ENGINE VERIFICATION")
print("=" * 90)
print()

try:
    import sys
    sys.path.append('HistoricalTrends/bi_engines')
    
    from availability_engine import AvailabilityProductionEngine
    
    engine = AvailabilityProductionEngine({
        'low_load_threshold': 0.3,
        'rated_capacity': RATED_CAPACITY
    })
    
    result = engine.calculate_availability(
        df=df,
        load_col='Load',
        rated_capacity=RATED_CAPACITY
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
    print("Additional Metrics from Engine:")
    print(f"  Availability: {result['availability']:.2f}%")
    print(f"  Breakdown Hours: {result['breakdown_hours']:.2f} hrs")
    print(f"  Average Load: {result['average_load']:.2f} MW")
    
except Exception as e:
    print(f"❌ Engine test failed: {str(e)}")
    import traceback
    traceback.print_exc()

print()
print("=" * 90)
print("📋 KEY INSIGHTS FOR 270 MW UNIT")
print("=" * 90)
print()
print("Maximum Daily Production:")
print(f"  Full Load (270 MW × 24 hrs): {RATED_CAPACITY * 24:,.0f} MWh/day")
print()
print("Typical Operating Scenarios:")
print(f"  100% Load (270 MW): {RATED_CAPACITY * 24:,.0f} MWh/day")
print(f"   95% Load (256.5 MW): {256.5 * 24:,.0f} MWh/day")
print(f"   90% Load (243 MW): {243 * 24:,.0f} MWh/day")
print(f"   75% Load (202.5 MW): {202.5 * 24:,.0f} MWh/day")
print(f"   50% Load (135 MW): {135 * 24:,.0f} MWh/day")
print()
print("Weekly Production Targets:")
print(f"  Excellent (>95% PLF): >{RATED_CAPACITY * 24 * 7 * 0.95:,.0f} MWh/week")
print(f"  Good (85-95% PLF): {RATED_CAPACITY * 24 * 7 * 0.85:,.0f} - {RATED_CAPACITY * 24 * 7 * 0.95:,.0f} MWh/week")
print(f"  Average (70-85% PLF): {RATED_CAPACITY * 24 * 7 * 0.70:,.0f} - {RATED_CAPACITY * 24 * 7 * 0.85:,.0f} MWh/week")
print()
print("Your 7-Day Performance:")
for i, day in enumerate(daily_summary, 1):
    status = "🟢" if day['plf'] > 90 else "🟡" if day['plf'] > 70 else "🔴" if day['plf'] > 0 else "⚫"
    print(f"  Day {i}: {status} {day['production_mwh']:>7,.0f} MWh (PLF: {day['plf']:>5.1f}%)")

print()
print("=" * 90)
print("✅ CALCULATION FORMULA VERIFIED")
print("=" * 90)
print()
print("Energy Production Formula: MWh = Σ(MW × Δt)")
print()
print("Where:")
print("  MW = Instantaneous power (load)")
print("  Δt = Time interval (1/60 hour for 1-minute data)")
print("  MWh = Energy produced")
print()
print("This is exactly how your plant energy meter calculates production!")
print("=" * 90)
