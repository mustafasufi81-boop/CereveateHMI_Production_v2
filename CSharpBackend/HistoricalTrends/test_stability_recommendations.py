"""
Test stability calculation and recommendations logic
"""
import numpy as np
from bi_engines.stability_engine import StabilityIndexEngine

# Test with flat data (like actual TURBINE_LOADMW)
values = np.array([105.58] * 934)

engine = StabilityIndexEngine()
result = engine.calculate_stability_index(values)

print("=" * 60)
print("STABILITY CALCULATION TEST")
print("=" * 60)
print(f"Input: {len(values)} values, all = 105.58 MW (perfectly flat)")
print()
print("RESULTS:")
print(f"  Coefficient of Variation: {result['coefficient_of_variation']:.10f}")
print(f"  Stability Index: {result['index']:.10f}")
print(f"  Rating: {result['rating']}")
print()
print("RECOMMENDATION LOGIC:")
print(f"  stabilityIndex < 0.7? {result['index'] < 0.7}")
print(f"  Should trigger recommendation? {'YES' if result['index'] < 0.7 else 'NO'}")
print()
print("EXPECTED BEHAVIOR:")
print(f"  With stability_index = {result['index']:.3f}, NO recommendation should appear")
print(f"  Data is perfectly stable, CV ≈ 0%")
print("=" * 60)
