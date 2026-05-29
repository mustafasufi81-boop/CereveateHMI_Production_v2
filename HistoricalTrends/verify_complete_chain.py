"""
Comprehensive verification of BI API chain
Tests all 8 endpoints with proper field naming
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from bi_engines.baseline_engine import AdaptiveBaselineEngine
from bi_engines.efficiency_engine import EfficiencyAdjustmentEngine
from bi_engines.delta_scorer import WeightedDeltaScorer
from bi_engines.availability_engine import AvailabilityProductionEngine
from bi_engines.influence_engine import InfluenceMapEngine
from bi_engines.stability_engine import StabilityIndexEngine
from bi_engines.condition_engine import ConditionScoringEngine
from bi_engines.loss_engine import LossAttributionEngine

print("\n" + "="*80)
print("COMPREHENSIVE BI API CHAIN VERIFICATION")
print("="*80)

# Sample data
sample_data = [
    {'Timestamp': '2025-11-20T10:00:00', 'TURBINE_LOADMW': 105.5, 'TOTAL_COAL_FLOW': 120.3},
    {'Timestamp': '2025-11-20T11:00:00', 'TURBINE_LOADMW': 108.2, 'TOTAL_COAL_FLOW': 122.1},
    {'Timestamp': '2025-11-20T12:00:00', 'TURBINE_LOADMW': 106.8, 'TOTAL_COAL_FLOW': 121.5},
]

print("\n1️⃣  BASELINE ENGINE")
print("-" * 80)
baseline_engine = AdaptiveBaselineEngine()
baseline = baseline_engine.calculate_adaptive_baseline(sample_data, 'TURBINE_LOADMW')
print(f"✓ Baseline calculated")
print(f"  Fields: {list(baseline.keys())}")
print(f"  Value: {baseline['value']:.2f}")
print(f"  std_dev: {baseline['std_dev']:.2f}")
print(f"  sample_size: {baseline['sample_size']}")
assert 'value' in baseline
assert 'std_dev' in baseline
assert 'sample_size' in baseline
assert 'valid_until' in baseline

print("\n2️⃣  EFFICIENCY ENGINE")
print("-" * 80)
efficiency_engine = EfficiencyAdjustmentEngine()
efficiency = efficiency_engine.calculate_adjusted_expected(
    baseline_production=baseline['value'],
    current_conditions={'Vibration': 2.5, 'CondenserVacuum': -700}
)
print(f"✓ Efficiency calculated")
print(f"  Fields: {list(efficiency.keys())}")
print(f"  adjusted_expected: {efficiency['adjusted_expected']:.2f}")
print(f"  total_loss_factor: {efficiency['total_loss_factor']:.4f}")
print(f"  loss_breakdown: {efficiency.get('loss_breakdown', {})}")
assert 'adjusted_expected' in efficiency
assert 'total_loss_factor' in efficiency
assert 'loss_breakdown' in efficiency

print("\n3️⃣  DELTA SCORER")
print("-" * 80)
delta_scorer = WeightedDeltaScorer()
delta = delta_scorer.calculate_weighted_delta(
    actual=105.5,
    expected=efficiency['adjusted_expected'],
    metadata={'period': 'test'},
    timestamp='2025-11-20T12:00:00'
)
print(f"✓ Delta calculated")
print(f"  Fields: {list(delta.keys())}")
print(f"  weighted_delta: {delta['weighted_delta']:.2f}")
print(f"  performance_score: {delta['performance_score']:.2f}")
assert 'weighted_delta' in delta
assert 'performance_score' in delta
assert 'condition' in delta

print("\n4️⃣  AVAILABILITY ENGINE")
print("-" * 80)
availability_engine = AvailabilityProductionEngine()
availability = availability_engine.calculate_availability_production(
    data=sample_data,
    rated_capacity=250,
    time_range={'start': '2025-11-20T10:00:00', 'end': '2025-11-20T12:00:00'}
)
print(f"✓ Availability calculated")
print(f"  Fields: {list(availability.keys())}")
print(f"  cumulative_production: {availability['cumulative_production']:.2f}")
print(f"  utilization_factor: {availability['utilization_factor']:.2f}")
print(f"  total_seconds: {availability['total_seconds']}")
assert 'cumulative_production' in availability
assert 'utilization_factor' in availability
assert 'total_seconds' in availability

print("\n5️⃣  INFLUENCE ENGINE")
print("-" * 80)
influence_engine = InfluenceMapEngine()
influence = influence_engine.compute_influence_map(
    primary_tag='TURBINE_LOADMW',
    influencing_tags=['TOTAL_COAL_FLOW'],
    data=sample_data
)
print(f"✓ Influence map calculated")
print(f"  Fields: {list(influence.keys())}")
for tag, corr in influence.items():
    print(f"  {tag}: impact_percentage={corr['impact_percentage']:.2f}, lag_minutes={corr['lag_minutes']}")
    assert 'impact_percentage' in corr
    assert 'lag_minutes' in corr
    assert 'pearson' in corr

print("\n6️⃣  STABILITY ENGINE")
print("-" * 80)
stability_engine = StabilityIndexEngine()
stability = stability_engine.calculate_stability_index(
    values=[105.5, 108.2, 106.8],
    value_tag='TURBINE_LOADMW'
)
print(f"✓ Stability calculated")
print(f"  Fields: {list(stability.keys())}")
print(f"  std_dev: {stability['std_dev']:.2f}")
print(f"  coefficient_of_variation: {stability['coefficient_of_variation']:.4f}")
assert 'std_dev' in stability
assert 'coefficient_of_variation' in stability

print("\n7️⃣  CONDITION ENGINE")
print("-" * 80)
condition_engine = ConditionScoringEngine()
condition = condition_engine.score_condition(
    parameter='TURBINE_LOADMW',
    value=105.5
)
print(f"✓ Condition scored")
print(f"  Fields: {list(condition.keys())}")
print(f"  score: {condition['score']}")
print(f"  status: {condition['status']}")
assert 'score' in condition
assert 'status' in condition
assert 'color' in condition

print("\n8️⃣  LOSS ATTRIBUTION ENGINE")
print("-" * 80)
loss_engine = LossAttributionEngine()
loss = loss_engine.attribute_loss(
    actual_production=availability['cumulative_production'],
    expected_production=efficiency['adjusted_expected'] * (availability['total_seconds'] / 3600),
    influence_map={
        'TOTAL_COAL_FLOW': {
            'pearson': influence['TOTAL_COAL_FLOW']['pearson'],
            'impact_percentage': influence['TOTAL_COAL_FLOW']['impact_percentage']
        }
    },
    current_conditions={'TOTAL_COAL_FLOW': 121.3}
)
print(f"✓ Loss attributed")
print(f"  Fields: {list(loss.keys())}")
print(f"  total_loss: {loss['total_loss']:.2f}")
if loss['attribution']:
    for param, data in loss['attribution'].items():
        print(f"  {param}: loss_amount={data['loss_amount']:.2f}, loss_percentage={data['loss_percentage']:.2f}")
        assert 'loss_amount' in data
        assert 'loss_percentage' in data
assert 'total_loss' in loss
assert 'attribution' in loss

print("\n" + "="*80)
print("✅ ALL TESTS PASSED - CHAIN VERIFIED")
print("="*80)
print("\nField Naming Summary:")
print("  Python (snake_case):")
print("    - adjusted_expected, total_loss_factor, loss_breakdown")
print("    - cumulative_production, utilization_factor, total_seconds")
print("    - impact_percentage, lag_minutes")
print("    - std_dev, coefficient_of_variation, sample_size, valid_until")
print("    - loss_amount, loss_percentage, total_loss")
print("    - weighted_delta, performance_score")
print("\n  JavaScript transformations (step returns):")
print("    - adjustedExpected, totalLossFactor, lossBreakdown (from step3)")
print("    - baselineValue (from step1)")
print("    - All Python snake_case preserved in API responses")
print("="*80 + "\n")
