# ML MODELS - INPUT/OUTPUT SPECIFICATION

## 📊 DATA STRUCTURE EXPECTED

### Input Data Format (Raw Data Collection):
```csv
timestamp,TURBINE_LOADMW,TOTAL_COAL_FLOW,MAIN_STEAM_PRESSURE,MAIN_STEAM_TEMP,...
2024-11-01 00:00:00,105.58,45.2,165.3,540.5,...
2024-11-01 00:01:00,105.60,45.3,165.4,540.6,...
2024-11-01 00:02:00,105.55,45.1,165.2,540.4,...
```

**Required Columns:**
- `timestamp` - DateTime column
- At least 1 target column (e.g., TURBINE_LOADMW)
- At least 2 feature columns (any other numeric parameters)

**Data Requirements:**
- Minimum rows: 1000+ samples
- Data quality: 80%+ availability per column
- Variance: Non-constant values (variance > 0.001)
- Numeric only (non-numeric columns auto-dropped)

---

## 🎯 MODEL INPUT/OUTPUT FLOW

### Step 1: Parameter Discovery
```
INPUT:  Raw CSV/Parquet files with all available columns
↓
PROCESS: Analyze correlations, variance, availability
↓
OUTPUT: Ranked parameter importance list
```

**Output File:** `02_DiscoveredParameters/parameter_importance_scores.csv`
```csv
parameter,importance_score,correlation,variance,availability
MAIN_STEAM_PRESSURE,0.95,0.87,125.3,0.99
TOTAL_COAL_FLOW,0.92,0.85,45.2,0.98
MAIN_STEAM_TEMP,0.88,0.82,88.1,0.99
...
```

---

### Step 2: Feature Selection
```
INPUT:  Top 50 important parameters (from Step 1)
        + Target column (e.g., TURBINE_LOADMW)
↓
PROCESS: Build feature matrix X and target y
↓
OUTPUT: Training data ready
```

**Feature Matrix (X):**
```python
X = DataFrame with shape (samples, 50 features)
# Example: (100000 rows, 50 columns)
# Columns: MAIN_STEAM_PRESSURE, TOTAL_COAL_FLOW, ...
```

**Target Vector (y):**
```python
y = Series with shape (samples,)
# Example: (100000 rows,)
# Values: TURBINE_LOADMW actual values
```

---

### Step 3: Model Training
```
INPUT:  X_train (80% of data, 50 features)
        y_train (80% of data, target values)
        X_val   (20% of data, 50 features)
        y_val   (20% of data, target values)
↓
PROCESS: Each model trains independently
↓
OUTPUT: 6 trained model files (.pkl)
```

**Model Files Created:**
```
Models/RandomForestModel_v1.pkl
Models/XGBoostModel_v1.pkl
Models/LightGBMModel_v1.pkl
Models/ProphetModel_v1.pkl
Models/IsolationForestModel_v1.pkl
Models/EnsembleModel_v1.pkl
```

**Each .pkl contains:**
```python
{
    'model': <trained sklearn/xgboost/etc model>,
    'version': 1,
    'trained_at': datetime(2024, 11, 21),
    'config': {...}
}
```

---

### Step 4: Model Evaluation
```
INPUT:  X_test (new unseen data, 50 features)
        y_test (actual target values)
↓
PROCESS: model.predict(X_test) → predictions
        Compare predictions vs y_test
↓
OUTPUT: Performance metrics
```

**Metrics Calculated:**
```python
{
    'MAE': 2.45,          # Mean Absolute Error (MW)
    'RMSE': 3.78,         # Root Mean Squared Error (MW)
    'R2': 0.94,           # R² Score (0-1, higher better)
    'MAPE': 2.3,          # Mean Absolute % Error
    'samples': 20000      # Test set size
}
```

**Saved to:** `08_ModelComparison/performance_log.csv`

---

### Step 5: Predictions (Production Use)
```
INPUT:  Current sensor readings (50 features)
        Example: {
            'MAIN_STEAM_PRESSURE': 165.3,
            'TOTAL_COAL_FLOW': 45.2,
            ...
        }
↓
PROCESS: Best model predicts future load
↓
OUTPUT: Predicted TURBINE_LOADMW
```

**Prediction Output:**
```python
{
    'predicted_load': 106.2,      # MW
    'confidence': 0.95,           # 0-1
    'model_used': 'XGBoostModel',
    'timestamp': '2024-11-21 15:30:00'
}
```

---

## 🔍 SPECIFIC MODEL INPUTS/OUTPUTS

### 1. RandomForest
```python
INPUT:  X_train: (80000, 50)  # 80k samples, 50 features
        y_train: (80000,)      # 80k target values

HYPERPARAMETERS:
    n_estimators: 100          # Number of trees
    max_depth: None            # Unlimited depth
    
OUTPUT: predictions: (20000,)  # Same length as X_test
        
PERFORMANCE:
    MAE: ~2-4 MW
    RMSE: ~3-5 MW
    R2: ~0.92-0.95
```

---

### 2. XGBoost
```python
INPUT:  X_train: (80000, 50)
        y_train: (80000,)

HYPERPARAMETERS:
    max_depth: 6
    learning_rate: 0.1
    n_estimators: 100
    
OUTPUT: predictions: (20000,)
        
PERFORMANCE:
    MAE: ~1.5-3 MW         # Usually best
    RMSE: ~2-4 MW
    R2: ~0.94-0.97
```

---

### 3. LightGBM
```python
INPUT:  X_train: (80000, 50)
        y_train: (80000,)

HYPERPARAMETERS:
    num_leaves: 31
    learning_rate: 0.1
    
OUTPUT: predictions: (20000,)
        
PERFORMANCE:
    MAE: ~1.8-3.5 MW       # Fast + accurate
    RMSE: ~2.5-4.5 MW
    R2: ~0.93-0.96
```

---

### 4. Prophet (Time Series)
```python
INPUT:  DataFrame with 'ds' (timestamp) and 'y' (target)
        df: (80000, 2)
        
SPECIAL: Doesn't use 50 features, only time patterns
        
OUTPUT: predictions with trend + seasonality
        
PERFORMANCE:
    MAE: ~3-6 MW           # Good for trends
    RMSE: ~4-8 MW
    R2: ~0.85-0.92
```

---

### 5. IsolationForest (Anomaly)
```python
INPUT:  X: (80000, 50)     # No y_train needed

PURPOSE: Detect anomalies, not predict values
        
OUTPUT: 
    anomaly_scores: (20000,)   # -1 to 1
    -1 = anomaly, 1 = normal
        
PERFORMANCE:
    Not measured in MAE/RMSE
    Measured in anomaly detection rate
```

---

### 6. Ensemble (Combination)
```python
INPUT:  X_test: (20000, 50)

PROCESS:
    RandomForest predicts → pred_rf
    XGBoost predicts      → pred_xgb
    LightGBM predicts     → pred_lgb
    Prophet predicts      → pred_prophet
    
    weighted_avg = (w1*pred_rf + w2*pred_xgb + w3*pred_lgb + w4*pred_prophet)
    
WEIGHTS: Adjusted daily based on recent performance
    
OUTPUT: predictions: (20000,)
        
PERFORMANCE:
    MAE: ~1.2-2.5 MW       # Usually best overall
    RMSE: ~2-3.5 MW
    R2: ~0.95-0.98
```

---

## 📈 EXAMPLE WORKFLOW WITH YOUR DATA

### Your Data Structure:
```
D:/OpcLogs/Data/
├── OpcData_20241101.parquet  → 1440 rows (1 min intervals)
├── OpcData_20241102.parquet  → 1440 rows
├── ...
└── OpcData_20250630.parquet  → 1440 rows

Total: ~241 days × 1440 rows = ~347,000 samples
Columns: 21 tags (TURBINE_LOADMW, TOTAL_COAL_FLOW, ...)
```

### Step-by-Step Processing:

**1. Load Historical Data (Nov 2024 - Jun 2025)**
```python
Input:  347,000 rows × 21 columns
Output: Combined DataFrame ready for analysis
```

**2. Parameter Discovery**
```python
Input:  All 21 columns analyzed
Output: Ranked importance:
    1. MAIN_STEAM_PRESSURE (score: 0.95)
    2. TOTAL_COAL_FLOW (score: 0.92)
    3. MAIN_STEAM_TEMP (score: 0.88)
    ...
    20. AUXILIARY_LOAD (score: 0.12)
```

**3. Feature Selection**
```python
Input:  Top 20 features (all 21 if all important)
Output: X = (347000, 20)
        y = (347000,)  # TURBINE_LOADMW
```

**4. Train/Test Split**
```python
X_train: (277600, 20)  # 80% = 277,600 samples
y_train: (277600,)
X_test:  (69400, 20)   # 20% = 69,400 samples
y_test:  (69400,)
```

**5. Train All 6 Models**
```python
Each model gets same X_train, y_train
Trains in parallel (3-10 minutes total)
Saves 6 .pkl files
```

**6. Evaluate on Test Set**
```python
Each model predicts on X_test (69,400 samples)
Compare predictions vs actual y_test
Log performance metrics
```

**7. Expected Results**
```
RandomForest:  MAE=2.8 MW, R2=0.94
XGBoost:       MAE=1.9 MW, R2=0.96  ← Best
LightGBM:      MAE=2.1 MW, R2=0.95
Prophet:       MAE=4.2 MW, R2=0.89
IsolationF:    (anomaly scores)
Ensemble:      MAE=1.7 MW, R2=0.97  ← Best overall
```

---

## ✅ VALIDATION CHECKLIST

Before running models, verify:

1. **Data exists**: D:/OpcLogs/Data/*.parquet files present
2. **Date range**: Nov 2024 - Jun 2025 files available
3. **Columns**: At least TURBINE_LOADMW + 2 other numeric columns
4. **Rows**: Minimum 1000 rows total (you have 347,000 ✓)
5. **Quality**: No all-null columns, variance > 0
6. **Format**: Parquet readable by pandas

---

## 🎯 FINAL OUTPUT YOU'LL SEE

```
08_ModelComparison/performance_comparison.csv:

model_name,MAE,RMSE,R2,MAPE,training_time,prediction_time
RandomForestModel,2.8,3.9,0.94,2.6,45.2,0.12
XGBoostModel,1.9,2.7,0.96,1.8,38.5,0.08
LightGBMModel,2.1,3.0,0.95,2.0,22.1,0.05
ProphetModel,4.2,5.8,0.89,3.9,128.3,1.45
EnsembleModel,1.7,2.4,0.97,1.6,0.0,0.25
```

**Best Model**: XGBoost or Ensemble (lowest MAE)
**Fastest**: LightGBM (22 seconds training)
**Most Accurate**: Ensemble (highest R²)
