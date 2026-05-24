"""
Test script to verify current_production calculation fix
Tests the master_orchestrator.py change for Dec 8, 2024 data
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
from bi_engines.master_orchestrator import MasterBIOrchestrator

# Test data for Dec 8, 2024 (single day with TURBINE_LOADMW = 238.29 average)
test_data = {
    'Timestamp': pd.date_range('2024-12-08 00:00', periods=100, freq='5min'),  # 100 points
    'TURBINE_LOADMW': [238.29] * 100,  # Constant 238.29
}

df = pd.DataFrame(test_data)

print("="*80)
print("TEST: Current Production Calculation")
print("="*80)
print(f"Test Data: {len(df)} rows")
print(f"Average TURBINE_LOADMW: {df['TURBINE_LOADMW'].mean():.3f} MW")
print(f"Expected: 238.29 MW")
print("="*80)

# Initialize orchestrator
orchestrator = MasterBIOrchestrator()

# Execute analysis
results = orchestrator.execute_full_analysis(
    df=df,
    production_tag='TURBINE_LOADMW',
    influencing_tags=[],  # Empty for simple test
    rated_capacity=270.0
)

print("\n" + "="*80)
print("RESULTS:")
print("="*80)

if 'summary' in results:
    summary = results['summary']
    current_prod = summary.get('current_production', 'NOT FOUND')
    baseline_prod = summary.get('baseline_production', 'NOT FOUND')
    
    print(f"✓ current_production: {current_prod} MW")
    print(f"✓ baseline_production: {baseline_prod} MW")
    
    if isinstance(current_prod, (int, float)):
        if abs(current_prod - 238.29) < 0.01:
            print("\n✅ SUCCESS: Current production matches expected value (238.29 MW)")
        else:
            print(f"\n❌ FAILED: Current production {current_prod:.3f} != 238.29 MW")
    else:
        print(f"\n❌ FAILED: current_production not found in summary")
else:
    print("❌ FAILED: No summary in results")

print("="*80)
