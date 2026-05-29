# ML Model Deployment Package
**Purpose**: Deploy trained ML models to production EXE without code access

## 📦 Deployment Files Structure

```
ModelDeployment/
├── trained_models/           # Final trained model files (.pkl)
│   ├── RandomForestModel_v1.pkl
│   ├── XGBoostModel_v1.pkl
│   ├── LightGBMModel_v1.pkl
│   ├── ProphetModel_v1.pkl
│   ├── NeuralNetworkModel_v1.pkl
│   └── EnsembleModel_v1.pkl
│
├── parameter_config/         # Which parameters to use
│   ├── parameter_importance_scores.csv
│   ├── top_parameters.json
│   └── parameter_mapping.json
│
├── model_metadata/          # Model performance and selection
│   ├── model_performance.csv
│   ├── best_model_config.json
│   └── model_weights.json (for ensemble)
│
├── scaler_files/            # Data normalization parameters
│   ├── feature_scaler.pkl
│   └── target_scaler.pkl
│
└── deployment_config.json   # Complete deployment configuration
```

---

## 🔄 Training → Deployment Workflow

### Step 1: Add Historical Data (Anytime)
```powershell
# Add new historical parquet files
python ML_System/historical_data_loader.py "D:/OpcLogs/Data/" --type parquet

# Or add CSV files
python ML_System/historical_data_loader.py "D:/HistoricalData/2024/" --type csv --start-date 2024-01-01

# Or specific date range
python ML_System/historical_data_loader.py "D:/OpcLogs/Data/" --start-date 2024-11-01 --end-date 2025-06-30
```

### Step 2: Train All Models
```powershell
# Full training cycle
python train_ml_with_historical_data.py

# This generates:
# - ML_System/Models/*.pkl (trained model files)
# - ML_System/Data/02_DiscoveredParameters/ (parameter rankings)
# - ML_System/Data/08_ModelComparison/ (performance metrics)
```

### Step 3: Generate Deployment Package
```powershell
python ML_System/create_deployment_package.py

# Creates ModelDeployment/ folder with everything needed
```

### Step 4: Copy to Production
```
Copy ModelDeployment/ folder → Plant computer
Production EXE loads:
  - best_model_config.json (which model to use)
  - trained_models/XGBoostModel_v1.pkl (the actual model)
  - parameter_mapping.json (which sensor tags to use)
  - feature_scaler.pkl (how to normalize inputs)
```

---

## 📋 Key Deployment Files Explained

### 1. `deployment_config.json`
**Purpose**: Complete configuration for production EXE
```json
{
  "version": "1.0.0",
  "training_date": "2025-11-21",
  "data_period": "2024-11-01 to 2025-06-30",
  "total_samples": 40853,
  "best_model": "XGBoostModel",
  "best_model_accuracy": 99.91,
  "target_column": "TURBINE_LOADMW",
  "model_file": "trained_models/XGBoostModel_v1.pkl",
  "scaler_file": "scaler_files/feature_scaler.pkl",
  "parameters_used": 18,
  "prediction_interval_seconds": 60,
  "retrain_recommended_days": 30
}
```

### 2. `top_parameters.json`
**Purpose**: Which OPC tags to read for predictions
```json
{
  "parameters": [
    {
      "rank": 1,
      "tag_name": "COOLING_WATER_TEMP_CT_FAN",
      "importance": 0.7482,
      "required": true
    },
    {
      "rank": 2,
      "tag_name": "SHAFT_VIB._IP_REAR-X",
      "importance": 0.6669,
      "required": true
    },
    ...
  ],
  "minimum_required": 15,
  "total_available": 18
}
```

### 3. `best_model_config.json`
**Purpose**: Which model to use and fallback options
```json
{
  "primary_model": {
    "name": "XGBoostModel",
    "file": "trained_models/XGBoostModel_v1.pkl",
    "accuracy": 99.91,
    "mae": 0.074,
    "confidence_threshold": 0.85
  },
  "fallback_models": [
    {
      "name": "RandomForestModel",
      "file": "trained_models/RandomForestModel_v1.pkl",
      "accuracy": 99.83,
      "use_if": "primary_model_fails"
    },
    {
      "name": "EnsembleModel",
      "file": "trained_models/EnsembleModel_v1.pkl",
      "accuracy": 99.87,
      "use_if": "low_confidence"
    }
  ]
}
```

### 4. `model_weights.json` (for Ensemble)
**Purpose**: How to combine multiple models
```json
{
  "RandomForest": 0.35,
  "XGBoost": 0.40,
  "LightGBM": 0.15,
  "NeuralNetwork": 0.10
}
```

---

## 🔧 Production EXE Integration

### How EXE Uses Deployment Files

```csharp
// C# Production Code (in EXE)
public class MLPredictionService
{
    private DeploymentConfig _config;
    private List<string> _requiredTags;
    
    public void Initialize()
    {
        // 1. Load deployment config
        _config = LoadJson("ModelDeployment/deployment_config.json");
        
        // 2. Load which parameters to use
        var parameters = LoadJson("ModelDeployment/parameter_config/top_parameters.json");
        _requiredTags = parameters.Select(p => p.tag_name).ToList();
        
        // 3. Python service loads actual model
        // (EXE calls Python API endpoint)
        var pythonApi = new HttpClient();
        pythonApi.PostAsync("http://localhost:5001/api/ml/load-model", 
            new { model_file = _config.model_file });
    }
    
    public double PredictLoad(Dictionary<string, double> currentReadings)
    {
        // 1. Extract only required parameters
        var features = _requiredTags
            .Select(tag => currentReadings[tag])
            .ToArray();
        
        // 2. Call Python ML service for prediction
        var prediction = pythonApi.Post("http://localhost:5001/api/ml/predict",
            new { features = features });
        
        return prediction.predicted_load;
    }
}
```

---

## 🔄 Continuous Learning Workflow

### Automatic Retraining Schedule

```
Plant Operation:
  - C# EXE collects data every 5 seconds → Parquet files
  - Python ML service monitors file count
  
Every 24 Hours:
  1. Check if 1 day of new data collected
  2. Add to ML_System/Data/01_RawData/
  3. Continue predictions with current model
  
Every 7 Days:
  1. Run parameter discovery (check if patterns changed)
  2. Train all models with ALL data (including new week)
  3. Compare new models vs current production model
  4. If accuracy improved > 0.1%:
     - Generate new deployment package
     - Alert: "New model ready: XGBoost v2 (99.95% accuracy)"
     - Manual approval to deploy
  
Every 30 Days:
  1. Full retraining with all historical data
  2. Re-discover parameters (may find new important ones)
  3. Generate deployment package v2
  4. Replace production models
```

---

## 📊 Files Generated During Training

### Training Process Output

```
ML_System/
├── Data/
│   ├── 01_RawData/              # Historical data (CSV/Parquet)
│   │   ├── raw_data_20241103.csv
│   │   ├── raw_data_20241104.csv
│   │   └── ... (36 files)
│   │
│   ├── 02_DiscoveredParameters/  # ✅ USED IN DEPLOYMENT
│   │   └── parameter_importance_scores.csv
│   │
│   ├── 08_ModelComparison/       # ✅ USED IN DEPLOYMENT
│   │   └── model_performance_log.csv
│   │
│   └── 09_FeedbackLoop/          # Continuous learning data
│       └── prediction_accuracy_log.csv
│
└── Models/                       # ✅ USED IN DEPLOYMENT
    ├── RandomForestModel_v1.pkl
    ├── XGBoostModel_v1.pkl
    ├── LightGBMModel_v1.pkl
    └── EnsembleModel_v1.pkl
```

### What Goes to Production

**Only These Files** → Copied to Plant Computer:
```
ModelDeployment/
├── deployment_config.json        ← Master config
├── trained_models/
│   └── XGBoostModel_v1.pkl      ← Best model only
├── parameter_config/
│   └── top_parameters.json      ← Which tags to read
└── best_model_config.json       ← Model selection
```

**EXE Reads**:
- `deployment_config.json` → Knows which model to use
- `top_parameters.json` → Knows which OPC tags to read
- Calls Python API → Python loads `XGBoostModel_v1.pkl`

---

## 🎯 Adding New Historical Data

### Scenario: Plant sends you 2 months of new data

```powershell
# Step 1: Copy new parquet files to server
# Example: Received July-August 2025 data

# Step 2: Import to ML system
python ML_System/historical_data_loader.py "D:/NewData/July_Aug_2025/" --type parquet

# Output:
# Loaded 60,000 rows from 61 files
# Saved 61 daily files to 01_RawData/
# IMPORT COMPLETE: 61 files created

# Step 3: Retrain models with ALL data (Nov 2024 - Aug 2025)
python train_ml_with_historical_data.py

# Output:
# Loaded 100,853 rows (was 40,853, now +60,000 more!)
# Discovered 20 parameters (was 18, found 2 new!)
# XGBoost: 99.94% accuracy (was 99.91%, improved!)
# New best predictor: NEW_SENSOR_X (0.82 importance)

# Step 4: Generate new deployment package
python ML_System/create_deployment_package.py

# Output:
# Created ModelDeployment_v2/
# Best model: XGBoostModel_v2.pkl (99.94% accuracy)
# Parameters changed: +2 new, -1 removed
# Ready for deployment

# Step 5: Deploy to production
# Copy ModelDeployment_v2/ → Plant computer
# Restart EXE (auto-loads new model)
```

---

## 💡 Key Benefits

### 1. **No Code Changes Needed**
- EXE reads JSON config files
- Model files are binary (.pkl)
- Just copy new `ModelDeployment/` folder

### 2. **Parameter Evolution**
- Models discover which parameters matter
- Week 1: Uses 18 parameters
- Month 6: May use different 20 parameters
- System auto-adapts

### 3. **Model Version Control**
```
ModelDeployment_v1/  (Nov 2024 data, XGBoost 99.91%)
ModelDeployment_v2/  (Jan 2025 data, XGBoost 99.94%)
ModelDeployment_v3/  (Jun 2025 data, Ensemble 99.97%)
```

### 4. **Easy Rollback**
If new model performs poorly:
```powershell
# Rollback to previous version
rm -r ModelDeployment/
cp -r ModelDeployment_v2_backup/ ModelDeployment/
# Restart EXE
```

---

## 📝 Summary

**You can add historical data anytime**:
```powershell
python ML_System/historical_data_loader.py [path/to/data]
```

**Models retrain with ALL data**:
- Includes old + new historical data
- Re-discovers best parameters
- Generates new trained model files

**Deploy to production**:
- Copy `ModelDeployment/` folder
- EXE loads JSON configs + .pkl files
- No code changes required

**Continuous improvement**:
- Every week: Check if retraining helps
- Every month: Generate new deployment package
- Models keep learning from live + historical data
