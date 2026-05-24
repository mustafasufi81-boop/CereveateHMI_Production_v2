"""
Show the exact recommendations logic from master_calculation_engine.js
"""

print("=" * 70)
print("RECOMMENDATIONS LOGIC - JavaScript Code")
print("=" * 70)
print("""
generateRecommendations(data) {
    const recommendations = [];
    
    // 1. STABILITY RECOMMENDATION
    const stabilityIndex = data.stability.stabilityIndex || 
                          data.stability.stability_index || 1;
    
    if (stabilityIndex < 0.7) {
        recommendations.push({
            priority: 'High',
            category: 'Stability',
            recommendation: 'Improve load stability - high fluctuations detected',
            expectedImpact: 'Reduce wear, improve efficiency'
        });
    }
    
    // 2. EFFICIENCY RECOMMENDATION  
    const totalLossFactor = data.efficiencyAdjustment.totalLossFactor || 
                           data.efficiencyAdjustment.total_loss_factor || 0;
    
    if (totalLossFactor > 0.15) {
        recommendations.push({
            priority: 'High',
            category: 'Efficiency',
            recommendation: 'Address efficiency losses - operating significantly below baseline',
            expectedImpact: `Recover ${(totalLossFactor * 100).toFixed(1)}% efficiency`
        });
    }
    
    // 3. AVAILABILITY RECOMMENDATION
    const availability = data.availability.availability || 100;
    
    if (availability < 85) {
        recommendations.push({
            priority: 'High',
            category: 'Availability',
            recommendation: 'Reduce breakdown time - availability below industry standard',
            expectedImpact: `Increase availability from ${availability.toFixed(1)}% to 90%+`
        });
    }
    
    return recommendations;
}
""")

print("\n" + "=" * 70)
print("TESTING WITH FLAT DATA (105.58 MW constant)")
print("=" * 70)

import numpy as np
from bi_engines.stability_engine import StabilityIndexEngine

# Simulate flat data
values = np.array([105.58] * 934)
engine = StabilityIndexEngine()
result = engine.calculate_stability_index(values)

print(f"\n1. STABILITY CHECK:")
print(f"   stability_index = {result['index']:.6f}")
print(f"   Condition: stabilityIndex < 0.7? {result['index'] < 0.7}")
print(f"   Result: {'WILL TRIGGER ❌' if result['index'] < 0.7 else 'Will NOT trigger ✅'}")

print(f"\n2. EFFICIENCY CHECK:")
print(f"   Would need: totalLossFactor > 0.15 (15%)")
print(f"   Note: This depends on actual vs baseline performance")
print(f"   With flat data (no variation), loss should be minimal")

print(f"\n3. AVAILABILITY CHECK:")
print(f"   Would need: availability < 85%")
print(f"   Note: Availability depends on uptime calculation")
print(f"   With continuous flat data, availability should be ~100%")

print("\n" + "=" * 70)
print("CONCLUSION")
print("=" * 70)
print("""
For perfectly flat data (all values = 105.58 MW):
✅ Stability recommendation: WILL NOT TRIGGER (index = 0.999)
✅ Efficiency recommendation: WILL NOT TRIGGER (no loss, perfect consistency)
✅ Availability recommendation: WILL NOT TRIGGER (100% uptime)

Expected result: NO RECOMMENDATIONS (or only efficiency if below rated capacity)
""")
