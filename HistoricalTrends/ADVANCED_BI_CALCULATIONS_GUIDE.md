# Advanced BI Calculations Guide
## Power Plant Performance Analytics - Technical Reference

---

## Table of Contents
1. [Weighted Production Delta Scoring](#1-weighted-production-delta-scoring)
2. [Adaptive Baseline Calculation](#2-adaptive-baseline-calculation)
3. [Availability-Based Production](#3-availability-based-production)
4. [Multi-Parameter Influence Analysis](#4-multi-parameter-influence-analysis)
5. [Efficiency Adjustment Engine](#5-efficiency-adjustment-engine)
6. [Stability Index Calculation](#6-stability-index-calculation)
7. [Condition Scoring System](#7-condition-scoring-system)
8. [Production Loss Attribution](#8-production-loss-attribution)

---

## 1. Weighted Production Delta Scoring

### Purpose
Measures actual vs expected production performance with **weighted penalties** based on operating conditions to accurately reflect plant state during deviations.

### Formula
```
weighted_delta = (actual_MW - expected_MW) × condition_weight
```

### Condition Weights
| Operating Condition | Weight | Penalty Impact | Description |
|---------------------|--------|----------------|-------------|
| **Trip** | 10.0 | Severe | Emergency shutdown event |
| **Startup** | 5.0 | High | Plant coming online |
| **Shutdown** | 5.0 | High | Planned/unplanned shutdown |
| **Load Ramp** | 3.0 | Medium | Active load change >20% |
| **Low Load** | 2.0 | Medium | Operating <30% capacity |
| **Part Load** | 1.5 | Low | Operating 30-70% capacity |
| **Stable Run** | 1.0 | None | Normal operation baseline |

### Condition Detection Logic
```python
# Priority Order:
1. Check metadata flags: trip=True, startup=True, shutdown=True
2. If no flags, calculate: load_factor = actual / expected
   
   if load_factor < 0.3:
       condition = "low_load"
   elif load_factor < 0.7:
       condition = "part_load"
   elif abs(actual - expected) > expected × 0.20:  # 20% threshold
       condition = "load_ramp"
   else:
       condition = "stable_run"
```

### Performance Score (0-100)
```
efficiency = (actual / expected) × 100
weight_penalty = (weight - 1) × 10
performance_score = clamp(0, 100, efficiency - weight_penalty)
```

### Example Calculation

**Scenario: Trip Event**
```
Inputs:
  actual_production = 100 MW
  expected_production = 120 MW
  metadata = {trip: true}

Step 1 - Raw Delta:
  raw_delta = 100 - 120 = -20 MW

Step 2 - Identify Condition:
  condition = "trip" (from metadata flag)
  weight = 10.0

Step 3 - Weighted Delta:
  weighted_delta = -20 × 10.0 = -200 MW-equivalent

Step 4 - Performance Score:
  efficiency = (100/120) × 100 = 83.3%
  weight_penalty = (10.0 - 1) × 10 = 90
  score = max(0, min(100, 83.3 - 90)) = 0

Output:
  {
    "raw_delta": -20.0,
    "weighted_delta": -200.0,
    "condition": "trip",
    "weight": 10.0,
    "performance_score": 0.0,
    "actual": 100.0,
    "expected": 120.0
  }
```

**Scenario: Stable Operation**
```
Inputs:
  actual_production = 118 MW
  expected_production = 120 MW
  metadata = {}

Step 1 - Raw Delta:
  raw_delta = 118 - 120 = -2 MW

Step 2 - Identify Condition:
  load_factor = 118/120 = 0.983 (98.3%)
  deviation = |118-120| = 2 MW (1.7% < 20% threshold)
  condition = "stable_run"
  weight = 1.0

Step 3 - Weighted Delta:
  weighted_delta = -2 × 1.0 = -2 MW

Step 4 - Performance Score:
  efficiency = (118/120) × 100 = 98.3%
  weight_penalty = (1.0 - 1) × 10 = 0
  score = 98.3

Output:
  {
    "raw_delta": -2.0,
    "weighted_delta": -2.0,
    "condition": "stable_run",
    "weight": 1.0,
    "performance_score": 98.3,
    "actual": 118.0,
    "expected": 120.0
  }
```

---

## 2. Adaptive Baseline Calculation

### Purpose
Establishes **dynamic performance baseline** using historical data with **outlier removal** to represent "normal" operating conditions without anomalies.

### Algorithm Steps

**Step 1: Data Collection**
```
baseline_window = 30 days (configurable)
top_percentile = 75% (use top quartile of production)
```

**Step 2: Percentile Filtering**
```python
# Remove low-performance outliers
production_values = historical_data['load_column']
threshold = percentile(production_values, top_percentile)
filtered_data = production_values[production_values >= threshold]
```

**Step 3: Outlier Detection Methods**
Choose one method:

| Method | Formula | Description |
|--------|---------|-------------|
| **Sigma (3σ)** | Remove if \|value - mean\| > 3×std | Standard statistical outliers |
| **IQR** | Remove if < Q1-1.5×IQR or > Q3+1.5×IQR | Interquartile range method |
| **MAD** | Remove if \|value - median\| > 3×MAD | Median absolute deviation |
| **Percentile** | Keep only [5th, 95th] percentile | Fixed percentile bounds |

**Step 4: Baseline Calculation**
```
adaptive_baseline = mean(cleaned_data_after_outlier_removal)
```

### Configuration Options
```json
{
  "baselineWindow": 30,           // Days of historical data
  "topPercentile": 75,            // Use top 75% of data
  "outlierMethod": "sigma",       // sigma|IQR|MAD|percentile
  "outlierThreshold": 3.0,        // 3 standard deviations
  "minDataPoints": 100            // Minimum required samples
}
```

### Example Calculation
```
Input: 30 days of load data (8,640 hourly samples)

Step 1 - Percentile Filter:
  75th percentile = 115 MW
  Filtered data: all values >= 115 MW (2,160 samples remain)

Step 2 - Outlier Removal (3-Sigma):
  mean = 118 MW
  std = 5 MW
  lower_bound = 118 - (3 × 5) = 103 MW
  upper_bound = 118 + (3 × 5) = 133 MW
  Remove 12 samples outside bounds (2,148 remain)

Step 3 - Final Baseline:
  adaptive_baseline = mean(2,148 cleaned samples) = 118.2 MW

Output:
  {
    "baseline": 118.2,
    "samples_used": 2148,
    "outliers_removed": 12,
    "method": "sigma",
    "percentile_threshold": 115.0
  }
```

---

## 3. Availability-Based Production

### Purpose
Calculates **cumulative production** considering plant availability, accounting for downtime and partial load operation.

### Formula
```
cumulative_production_MWh = Σ(load_MW × time_interval_hours)
availability_factor = (actual_MWh / rated_capacity_MWh) × 100
capacity_factor = (actual_MWh / potential_MWh) × 100
```

### Calculation Steps

**Step 1: Time-Series Integration**
```python
for each_hour in dataset:
    load_MW = current_load_value
    time_delta_hours = (next_timestamp - current_timestamp) / 3600
    energy_MWh = load_MW × time_delta_hours
    cumulative_production += energy_MWh
```

**Step 2: Availability Metrics**
```
rated_capacity_MWh = rated_MW × total_hours
availability_% = (cumulative_production_MWh / rated_capacity_MWh) × 100
```

**Step 3: Capacity Factor**
```
potential_production_MWh = max_observed_MW × total_hours
capacity_factor_% = (cumulative_production_MWh / potential_production_MWh) × 100
```

### Example Calculation

**Scenario: 270 MW Plant - 24 Hours**
```
Inputs:
  rated_capacity = 270 MW
  time_period = 24 hours
  hourly_load_data = [250, 260, 270, 255, ..., 240] MW (24 samples)

Step 1 - Cumulative Production:
  hour_1: 250 MW × 1 hr = 250 MWh
  hour_2: 260 MW × 1 hr = 260 MWh
  hour_3: 270 MW × 1 hr = 270 MWh
  ...
  hour_24: 240 MW × 1 hr = 240 MWh
  
  total_production = 6,120 MWh

Step 2 - Availability:
  rated_capacity_MWh = 270 MW × 24 hr = 6,480 MWh
  availability = (6,120 / 6,480) × 100 = 94.4%

Step 3 - Capacity Factor:
  max_observed_load = 270 MW
  potential_MWh = 270 × 24 = 6,480 MWh
  capacity_factor = (6,120 / 6,480) × 100 = 94.4%

Output:
  {
    "cumulativeProduction": 6120.0,
    "totalSeconds": 86400,
    "avgLoad": 255.0,
    "availability": 94.4,
    "capacityFactor": 94.4,
    "ratedCapacity": 270.0
  }
```

---

## 4. Multi-Parameter Influence Analysis

### Purpose
Identifies **correlation strength** between primary production parameter and influencing operational parameters using multiple statistical methods.

### Correlation Metrics

**1. Pearson Correlation (Linear Relationship)**
```
r = Σ((x - x̄)(y - ȳ)) / √(Σ(x - x̄)² × Σ(y - ȳ)²)

Range: -1 to +1
  +1: Perfect positive correlation
   0: No correlation
  -1: Perfect negative correlation
```

**2. Spearman Rank Correlation (Monotonic Relationship)**
```
ρ = 1 - (6 × Σd²) / (n(n² - 1))
where d = difference in ranks

Range: -1 to +1 (same interpretation as Pearson)
```

**3. Rolling Correlation (Time-Varying)**
```
window_size = 24 hours (configurable)
r_rolling(t) = pearson(window[t-24:t])
```

**4. Lag Correlation (Delayed Effect)**
```
max_lag = 10 time steps
r_lag(k) = correlation(x[0:n-k], y[k:n])
optimal_lag = argmax(|r_lag(k)|)
```

**5. Impact Percentage**
```
impact_% = |correlation| × 100
```

### Interpretation Guidelines

| Correlation | Strength | Interpretation |
|-------------|----------|----------------|
| 0.9 to 1.0 | Very Strong | Highly predictive |
| 0.7 to 0.9 | Strong | Significant influence |
| 0.5 to 0.7 | Moderate | Meaningful relationship |
| 0.3 to 0.5 | Weak | Minor influence |
| 0.0 to 0.3 | Very Weak | Negligible |

### Example Calculation

**Scenario: Load vs Vibration Analysis**
```
Input:
  primary_tag = "TURBINE_LOAD.MW"
  influencing_tags = ["Vibration", "NOx", "MSPressure"]
  data = 1000 samples over 24 hours

Analysis for "Vibration":

Step 1 - Pearson Correlation:
  load = [250, 255, 260, ..., 245] (1000 values)
  vibration = [3.2, 3.5, 4.1, ..., 3.0] (1000 values)
  
  pearson_r = -0.67  (negative correlation)
  interpretation = "Moderate negative" (higher vibration → lower load)

Step 2 - Spearman Correlation:
  rank(load) = [1, 2, 3, ..., 998]
  rank(vibration) = [500, 502, 750, ..., 450]
  
  spearman_ρ = -0.71  (stronger monotonic relationship)

Step 3 - Rolling Correlation (24-hour window):
  rolling_mean = -0.65
  rolling_std = 0.08
  rolling_min = -0.82
  rolling_max = -0.45

Step 4 - Lag Analysis:
  lag_0: -0.67
  lag_1: -0.69
  lag_2: -0.72  ← optimal lag (strongest correlation)
  lag_3: -0.68
  
  optimal_lag = 2 hours

Step 5 - Impact Percentage:
  impact = |-0.67| × 100 = 67%

Output:
  {
    "parameter": "Vibration",
    "correlation": -0.67,
    "correlation_type": "negative_moderate",
    "spearman": -0.71,
    "rolling_avg": -0.65,
    "rolling_std": 0.08,
    "optimal_lag": 2,
    "lag_correlation": -0.72,
    "impact_percentage": 67.0,
    "significance": "Moderate influence - Higher vibration correlates with reduced load"
  }
```

---

## 5. Efficiency Adjustment Engine

### Purpose
Calculates **adjusted expected production** by applying efficiency coefficients based on current operating conditions (temperature, pressure, humidity, load factor).

### Formula
```
adjusted_expected = baseline_production × Π(efficiency_factors)

where:
  efficiency_factors = [temp_factor, pressure_factor, humidity_factor, load_factor]
```

### Efficiency Factor Calculations

**1. Temperature Correction**
```python
temp_deviation = (current_temp - design_temp) / design_temp
temp_factor = 1 - (temp_deviation × temp_coefficient)

# Typical: -0.5% per °C above design
temp_coefficient = 0.005 per °C
```

**2. Pressure Correction**
```python
pressure_deviation = (current_pressure - design_pressure) / design_pressure
pressure_factor = 1 + (pressure_deviation × pressure_coefficient)

# Typical: +0.3% per % increase in pressure
pressure_coefficient = 0.003 per %
```

**3. Humidity Correction**
```python
humidity_deviation = (current_humidity - design_humidity) / design_humidity
humidity_factor = 1 - (humidity_deviation × humidity_coefficient)

# Typical: -0.2% per % increase in humidity
humidity_coefficient = 0.002 per %
```

**4. Load Factor Correction**
```python
load_factor = current_load / rated_capacity

if load_factor > 0.95:
    load_factor_correction = 1.0  # Full load efficiency
elif load_factor > 0.70:
    load_factor_correction = 0.98  # Part load penalty 2%
elif load_factor > 0.50:
    load_factor_correction = 0.95  # Part load penalty 5%
else:
    load_factor_correction = 0.90  # Low load penalty 10%
```

### Example Calculation

**Scenario: 270 MW Plant with Current Conditions**
```
Inputs:
  baseline_production = 270 MW (from adaptive baseline)
  
  current_conditions = {
    "ambient_temp": 35°C,
    "ms_pressure": 165 bar,
    "humidity": 75%,
    "current_load": 255 MW
  }
  
  design_conditions = {
    "design_temp": 30°C,
    "design_pressure": 160 bar,
    "design_humidity": 60%,
    "rated_capacity": 270 MW
  }

Step 1 - Temperature Factor:
  temp_deviation = (35 - 30) / 30 = 0.167 (16.7% increase)
  temp_factor = 1 - (0.167 × 0.005) = 0.999  (99.9%)
  impact = -0.1% (slight reduction due to higher temp)

Step 2 - Pressure Factor:
  pressure_deviation = (165 - 160) / 160 = 0.031 (3.1% increase)
  pressure_factor = 1 + (0.031 × 0.003) = 1.000  (100.0%)
  impact = +0.0% (negligible improvement)

Step 3 - Humidity Factor:
  humidity_deviation = (75 - 60) / 60 = 0.25 (25% increase)
  humidity_factor = 1 - (0.25 × 0.002) = 0.999  (99.9%)
  impact = -0.1% (slight reduction due to higher humidity)

Step 4 - Load Factor:
  load_factor = 255 / 270 = 0.944 (94.4%)
  load_factor_correction = 1.0  (no penalty, >95% threshold)

Step 5 - Combined Adjustment:
  adjusted_expected = 270 × 0.999 × 1.000 × 0.999 × 1.0
  adjusted_expected = 269.5 MW

Output:
  {
    "baseline_production": 270.0,
    "adjusted_expected": 269.5,
    "efficiency_factors": {
      "temperature": 0.999,
      "pressure": 1.000,
      "humidity": 0.999,
      "load_factor": 1.000
    },
    "total_efficiency": 0.998,
    "net_adjustment": -0.5 MW (-0.2%)
  }
```

---

## 6. Stability Index Calculation

### Purpose
Measures **operational stability** using coefficient of variation (CV) to quantify consistency of production/parameters over time.

### Formula
```
CV = (standard_deviation / mean) × 100

Stability Index = 1 / (1 + CV)
```

### Stability Ratings

| CV Range | Stability Index | Rating | Description |
|----------|----------------|--------|-------------|
| 0-5% | 0.95-1.00 | Excellent | Very stable operation |
| 5-10% | 0.91-0.95 | Good | Stable with minor variations |
| 10-20% | 0.83-0.91 | Fair | Moderate variability |
| 20-30% | 0.77-0.83 | Poor | High variability |
| >30% | <0.77 | Very Poor | Unstable operation |

### Example Calculation

**Scenario: Load Stability Analysis**
```
Input:
  load_data = [250, 255, 252, 258, 251, 254, 256, 253, 255, 250] MW

Step 1 - Statistical Measures:
  mean = 253.4 MW
  std_deviation = 2.6 MW

Step 2 - Coefficient of Variation:
  CV = (2.6 / 253.4) × 100 = 1.03%

Step 3 - Stability Index:
  stability_index = 1 / (1 + 0.0103) = 0.990

Step 4 - Rating:
  CV = 1.03% → Rating: "Excellent"

Output:
  {
    "mean": 253.4,
    "std": 2.6,
    "cv": 1.03,
    "index": 0.990,
    "rating": "Excellent",
    "interpretation": "Very stable operation with minimal load variation"
  }
```

---

## 7. Condition Scoring System

### Purpose
Assigns **health scores (0-100)** to operating parameters based on configurable threshold zones (Green/Yellow/Red).

### Threshold Zones

```
Green Zone (Good):    min_threshold ≤ value ≤ max_threshold
Yellow Zone (Caution): threshold ± warning_margin
Red Zone (Critical):   value outside warning_margin
```

### Scoring Logic

```python
if min_threshold <= value <= max_threshold:
    score = 100  # Green
    status = "Good"
    color = "green"
    
elif (min_threshold - warning_margin) <= value <= (max_threshold + warning_margin):
    # Yellow zone - linear interpolation
    distance_from_optimal = min(
        abs(value - min_threshold),
        abs(value - max_threshold)
    )
    score = 100 - (distance_from_optimal / warning_margin) × 50
    status = "Caution"
    color = "yellow"
    
else:
    # Red zone - critical
    score = 0
    status = "Critical"
    color = "red"
```

### Default Thresholds (Power Plant)

| Parameter | Min | Max | Warning Margin | Unit |
|-----------|-----|-----|----------------|------|
| Vibration | 0.0 | 3.0 | ±1.0 | mm/s |
| NOx | 0 | 50 | ±20 | ppm |
| MS Pressure | 140 | 170 | ±10 | bar |
| Vacuum | -0.9 | -0.7 | ±0.1 | bar |
| Load | 0 | 270 | ±30 | MW |

### Example Calculations

**Example 1: Vibration = 2.5 mm/s (Good)**
```
Thresholds:
  min = 0.0, max = 3.0, warning_margin = 1.0

Check:
  0.0 ≤ 2.5 ≤ 3.0 → Inside green zone

Result:
  score = 100
  status = "Good"
  color = "green"
```

**Example 2: Vibration = 3.7 mm/s (Caution)**
```
Thresholds:
  min = 0.0, max = 3.0, warning_margin = 1.0
  yellow_max = 3.0 + 1.0 = 4.0

Check:
  3.0 < 3.7 ≤ 4.0 → Inside yellow zone

Calculation:
  distance_from_optimal = 3.7 - 3.0 = 0.7
  score = 100 - (0.7 / 1.0) × 50 = 65

Result:
  score = 65
  status = "Caution"
  color = "yellow"
```

**Example 3: Vibration = 5.2 mm/s (Critical)**
```
Thresholds:
  max = 3.0, warning_margin = 1.0
  yellow_max = 4.0

Check:
  5.2 > 4.0 → Outside warning margin (red zone)

Result:
  score = 0
  status = "Critical"
  color = "red"
```

**Example 4: NOx = 45 ppm (Good)**
```
Thresholds:
  min = 0, max = 50, warning_margin = 20

Check:
  0 ≤ 45 ≤ 50 → Inside green zone

Result:
  score = 100
  status = "Good"
  color = "green"
```

---

## 8. Production Loss Attribution

### Purpose
Attributes **production losses** to specific influencing parameters based on correlation strength and current operating deviations.

### Formula
```
total_loss = expected_production - actual_production

For each parameter:
  influence_weight = correlation_strength × impact_percentage
  attributed_loss = total_loss × (influence_weight / Σ(all_weights))
```

### Attribution Steps

**Step 1: Calculate Total Loss**
```
total_loss_MW = expected_MW - actual_MW
```

**Step 2: Weight Each Parameter**
```python
for each_parameter in influencing_parameters:
    # Get correlation from influence analysis
    correlation = abs(influence_map[parameter].pearson)
    impact = influence_map[parameter].impact_percentage
    
    # Get current deviation from normal
    current_value = current_conditions[parameter]
    normal_value = baseline_conditions[parameter]
    deviation = abs(current_value - normal_value) / normal_value
    
    # Combined weight
    weight = correlation × impact × deviation
```

**Step 3: Normalize and Attribute**
```python
total_weight = sum(all_weights)

for each_parameter:
    attributed_loss[parameter] = total_loss × (weight / total_weight)
    percentage_contribution = (attributed_loss / total_loss) × 100
```

**Step 4: Unattributed Loss**
```
unattributed_loss = total_loss - sum(attributed_losses)
```

### Example Calculation

**Scenario: 50 MW Production Loss**
```
Inputs:
  expected_production = 270 MW
  actual_production = 220 MW
  total_loss = 50 MW
  
  influence_map = {
    "Vibration": {correlation: -0.67, impact: 67%},
    "NOx": {correlation: -0.45, impact: 45%},
    "MSPressure": {correlation: 0.52, impact: 52%}
  }
  
  current_conditions = {
    "Vibration": 4.5 mm/s,
    "NOx": 75 ppm,
    "MSPressure": 145 bar
  }
  
  baseline_conditions = {
    "Vibration": 2.0 mm/s,
    "NOx": 40 ppm,
    "MSPressure": 160 bar
  }

Step 1 - Parameter Deviations:
  vibration_deviation = |4.5 - 2.0| / 2.0 = 1.25 (125% increase)
  nox_deviation = |75 - 40| / 40 = 0.875 (87.5% increase)
  pressure_deviation = |145 - 160| / 160 = 0.094 (9.4% decrease)

Step 2 - Influence Weights:
  vibration_weight = 0.67 × 0.67 × 1.25 = 0.561
  nox_weight = 0.45 × 0.45 × 0.875 = 0.177
  pressure_weight = 0.52 × 0.52 × 0.094 = 0.025
  
  total_weight = 0.561 + 0.177 + 0.025 = 0.763

Step 3 - Loss Attribution:
  vibration_loss = 50 × (0.561 / 0.763) = 36.8 MW (73.5%)
  nox_loss = 50 × (0.177 / 0.763) = 11.6 MW (23.2%)
  pressure_loss = 50 × (0.025 / 0.763) = 1.6 MW (3.3%)
  
  attributed_total = 36.8 + 11.6 + 1.6 = 50.0 MW

Step 4 - Unattributed Loss:
  unattributed = 50.0 - 50.0 = 0.0 MW (all loss explained)

Output:
  {
    "total_loss": 50.0,
    "attributed_loss": 50.0,
    "unattributed_loss": 0.0,
    "attribution": {
      "Vibration": {
        "loss_MW": 36.8,
        "percentage": 73.5,
        "correlation": -0.67,
        "deviation": 125.0,
        "severity": "Critical"
      },
      "NOx": {
        "loss_MW": 11.6,
        "percentage": 23.2,
        "correlation": -0.45,
        "deviation": 87.5,
        "severity": "High"
      },
      "MSPressure": {
        "loss_MW": 1.6,
        "percentage": 3.3,
        "correlation": 0.52,
        "deviation": 9.4,
        "severity": "Low"
      }
    },
    "primary_cause": "Vibration",
    "recommendation": "Investigate high vibration (4.5 mm/s) - 125% above baseline causing 73.5% of production loss"
  }
```

---

## Workflow Integration

### Complete BI Analysis Sequence

```javascript
// Step 1: Load historical data
data = loadParquetData(date_range, selected_tags);

// Step 2: Calculate adaptive baseline (30-day window)
baseline = calculateBaseline(data, {
  window: 30,
  percentile: 75,
  outlierMethod: 'sigma'
});

// Step 3: Calculate availability-based production
availability = calculateAvailability(data, {
  loadColumn: 'TURBINE_LOAD.MW',
  ratedCapacity: 270
});

// Step 4: Compute multi-parameter influence map
influenceMap = computeInfluenceMap(
  primaryTag: 'TURBINE_LOAD.MW',
  influencingTags: ['Vibration', 'NOx', 'MSPressure', 'Vacuum'],
  data: data
);

// Step 5: Calculate efficiency-adjusted expected production
efficiencyAdjustment = calculateEfficiency(
  baseline: baseline.value,
  currentConditions: extractConditions(data)
);

// Step 6: Calculate weighted production delta
delta = calculateWeightedDelta(
  actual: availability.avgLoad,
  expected: efficiencyAdjustment.adjustedExpected,
  metadata: extractMetadata(data)
);

// Step 7: Calculate stability index
stability = calculateStability(
  values: data['TURBINE_LOAD.MW']
);

// Step 8: Score parameter conditions
conditionScores = {};
for each parameter in ['Vibration', 'NOx', 'MSPressure', 'Vacuum']:
  conditionScores[parameter] = scoreCondition(
    parameter: parameter,
    value: avg(data[parameter])
  );

// Step 9: Attribute production loss
lossAttribution = attributeLoss(
  actual: availability.cumulativeProduction,
  expected: efficiencyAdjustment.adjustedExpected * availability.totalHours,
  influenceMap: influenceMap,
  currentConditions: extractConditions(data)
);

// Step 10: Generate comprehensive report
report = {
  baseline: baseline,
  availability: availability,
  influence: influenceMap,
  efficiency: efficiencyAdjustment,
  delta: delta,
  stability: stability,
  conditions: conditionScores,
  lossAttribution: lossAttribution
};
```

---

## API Endpoints Reference

### 1. Baseline Calculation
```http
POST /api/v1/baseline/calculate
Content-Type: application/json

{
  "data": [...],  // Array of {timestamp, load_value}
  "config": {
    "baselineWindow": 30,
    "topPercentile": 75,
    "outlierMethod": "sigma"
  }
}

Response:
{
  "baseline": 118.2,
  "samples_used": 2148,
  "outliers_removed": 12
}
```

### 2. Availability Calculation
```http
POST /api/v1/availability/calculate
Content-Type: application/json

{
  "data": [...],  // Array of {timestamp, load, ...}
  "load_column": "TURBINE_LOAD.MW",
  "rated_capacity": 270,
  "timestamp_column": "Timestamp"
}

Response:
{
  "cumulativeProduction": 6120.0,
  "availability": 94.4,
  "capacityFactor": 94.4
}
```

### 3. Influence Analysis
```http
POST /api/v1/influence/calculate
Content-Type: application/json

{
  "primary_tag": "TURBINE_LOAD.MW",
  "influencing_tags": ["Vibration", "NOx", "MSPressure"],
  "data": [...]  // Array of objects with all tags
}

Response:
{
  "influences": [
    {
      "parameter": "Vibration",
      "correlation": -0.67,
      "impact": 67.0,
      "lag": 2
    }
  ]
}
```

### 4. Weighted Delta
```http
POST /api/v1/delta/calculate
Content-Type: application/json

{
  "actual": 220.0,
  "expected": 270.0,
  "operating_condition": {"trip": false},
  "timestamp": "2025-11-21T00:00:00"
}

Response:
{
  "raw_delta": -50.0,
  "weighted_delta": -50.0,
  "condition": "stable_run",
  "weight": 1.0,
  "performance_score": 81.5
}
```

### 5. Efficiency Adjustment
```http
POST /api/v1/efficiency/calculate
Content-Type: application/json

{
  "baseline_production": 270.0,
  "current_conditions": {
    "ambient_temp": 35.0,
    "ms_pressure": 165.0,
    "humidity": 75.0
  }
}

Response:
{
  "adjusted_expected": 269.5,
  "efficiency_factors": {...},
  "total_efficiency": 0.998
}
```

### 6. Stability Index
```http
POST /api/v1/stability/calculate
Content-Type: application/json

{
  "values": [250, 255, 252, 258, ...]
}

Response:
{
  "index": 0.990,
  "cv": 1.03,
  "rating": "Excellent"
}
```

### 7. Condition Scoring
```http
POST /api/v1/condition/score
Content-Type: application/json

{
  "parameter": "Vibration",
  "value": 2.5,
  "custom_thresholds": {
    "min": 0.0,
    "max": 3.0,
    "warning_margin": 1.0
  }
}

Response:
{
  "score": 100,
  "status": "Good",
  "color": "green",
  "value": 2.5
}
```

### 8. Loss Attribution
```http
POST /api/v1/loss/attribute
Content-Type: application/json

{
  "actual_production": 220.0,
  "expected_production": 270.0,
  "influence_map": {...},
  "current_conditions": {...}
}

Response:
{
  "total_loss": 50.0,
  "attributed_loss": 50.0,
  "attribution": {
    "Vibration": {"loss_MW": 36.8, "percentage": 73.5}
  }
}
```

---

## Performance Optimization

### Data Volume Handling
- **11,196 data points**: ~0.5 seconds per calculation
- **43,000 data points**: ~2 seconds per calculation
- **100,000+ data points**: ~5-10 seconds (chunked processing)

### Browser Resource Management
- **Delta calculation**: 1 API call (not per-point iteration)
- **Condition scoring**: Sequential execution (4-6 parameters)
- **Influence analysis**: Batch processing in Python/NumPy
- **Total workflow**: 10-20 seconds for complete BI analysis

### Caching Strategy
- Baseline: Cached for 24 hours
- Influence map: Cached per tag combination
- File index: JSON-based cache for parquet files
- Derived analytics: Parquet-based persistent cache

---

## Error Handling

### Type Safety
- **Double-layer conversion**: Endpoint + Engine level
- **String to float**: `pd.to_numeric()` with coercion
- **None values**: Default responses (score=50, status='Unknown')
- **Missing keys**: Fallback parameter names

### Validation
- **Minimum data points**: 100 samples required
- **Zero protection**: Division by 0.001 instead of 0
- **NaN handling**: Filter before calculations
- **Outlier bounds**: Clamped to [0, 100] for scores

---

## Configuration Files

### bi_config.yaml (Engine Configuration)
```yaml
baseline:
  window_days: 30
  top_percentile: 75
  outlier_method: sigma
  outlier_threshold: 3.0

delta_scorer:
  event_weights:
    trip: 10.0
    startup: 5.0
    shutdown: 5.0
    load_ramp: 3.0
    low_load: 2.0
    part_load: 1.5
    stable_run: 1.0
  ramp_threshold: 0.20

efficiency:
  temp_coefficient: 0.005
  pressure_coefficient: 0.003
  humidity_coefficient: 0.002

condition_thresholds:
  Vibration: {min: 0.0, max: 3.0, warning: 1.0}
  NOx: {min: 0, max: 50, warning: 20}
  MSPressure: {min: 140, max: 170, warning: 10}
  Vacuum: {min: -0.9, max: -0.7, warning: 0.1}
```

---

## Troubleshooting

### Common Issues

**1. ERR_INSUFFICIENT_RESOURCES**
- **Cause**: Too many simultaneous API calls
- **Solution**: Use aggregated data (single call per metric)

**2. TypeError: Cannot read properties of undefined**
- **Cause**: Missing response fields (e.g., `weightedDelta`)
- **Solution**: Validate response before accessing properties

**3. String numeric errors**
- **Cause**: JSON payloads contain string numbers
- **Solution**: Double-layer `float()` conversion

**4. KeyError on payload fields**
- **Cause**: Frontend sends alternate field names
- **Solution**: Fallback key mapping (`actual_production` OR `actual`)

**5. Performance degradation**
- **Cause**: Large datasets (>100K points)
- **Solution**: Enable chunked processing or sampling

---

## Version History

**v1.0** - Initial implementation
- Basic BI engines
- Python backend integration
- 8 calculation modules

**v1.1** - Type Safety Enhancement
- Double-layer numeric conversion
- None value handling
- Missing key fallbacks

**v1.2** - Performance Optimization
- Reduced API calls from 11K+ to single calls
- Sequential condition scoring
- Resource exhaustion prevention

**v1.3** - Current Version
- Comprehensive error handling
- Full test coverage
- Production-ready state

---

## License & Support

**System**: OPC DA Industrial SCADA - Advanced BI Module
**Framework**: Python Flask + JavaScript ES6 Modules
**Documentation**: November 21, 2025
**Contact**: Technical Support Team

For issues or questions, refer to:
- `BI_ENGINE_PYTHON_BACKEND_README.md`
- `API_DOCUMENTATION.md`
- `MODULAR_ARCHITECTURE.md`
