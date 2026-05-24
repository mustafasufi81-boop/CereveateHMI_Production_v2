"""
Test simple baseline calculation with small dataset
"""
import pandas as pd
from datetime import datetime
from bi_engines.baseline_engine import AdaptiveBaselineEngine

# Create small test dataset - 10 data points
test_data = pd.DataFrame({
    'Timestamp': pd.date_range('2025-01-15 00:00', periods=10, freq='5min'),
    'TURBINE_LOADMW': [240.5, 242.1, 243.8, 241.2, 244.5, 243.1, 242.7, 240.8, 244.2, 243.5]
})

print("Test Data:")
print(test_data)
print(f"\nValues: {test_data['TURBINE_LOADMW'].tolist()}")

# Calculate baseline
engine = AdaptiveBaselineEngine({'min_data_points': 5})
result = engine.calculate_adaptive_baseline(test_data, 'TURBINE_LOADMW')

print("\n" + "="*60)
print("BASELINE CALCULATION RESULT")
print("="*60)
if result:
    print(f"Baseline (Average): {result['value']:.2f} MW")
    print(f"Min: {result['min']:.2f} MW")
    print(f"Max: {result['max']:.2f} MW")
    print(f"Std Dev: {result['std_dev']:.2f} MW")
    print(f"Sample Size: {result['sample_size']}")
    print(f"Method: {result['method']}")
    print(f"Period: {result['date_from']} to {result['date_to']}")
    
    # Verify manual calculation
    manual_avg = sum(test_data['TURBINE_LOADMW']) / len(test_data)
    print(f"\n✓ Manual verification: {manual_avg:.2f} MW")
    print(f"✓ Match: {abs(result['value'] - manual_avg) < 0.01}")
else:
    print("❌ Failed to calculate baseline")
