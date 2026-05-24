# ML BACKGROUND LEARNING SYSTEM - QUICK START

## Installation

### 1. Install Dependencies
```bash
cd HistoricalTrends/ML_System
pip install -r ml_requirements.txt
```

### 2. Configure System
Edit `config.yaml`:
```yaml
# For testing with CSV files
storage:
  testing_mode: true
  testing_format: "csv"

# Data source
data_collection:
  parameter_source: "csv_files"  # or "opc_server"
```

## Running the System

### Option 1: Run in Console (For Testing)
```bash
python background_process_manager.py
```

Press Ctrl+C to stop.

### Option 2: Run as Windows Service (Production)
```bash
# Install service
python ml_background_service.py install

# Start service
python ml_background_service.py start

# Stop service
python ml_background_service.py stop

# Remove service
python ml_background_service.py remove
```

## What Happens

### Immediately:
- ✅ Data collection starts (every 1 minute)
- ✅ Parameters auto-discovered from data
- ✅ All data stored in CSV (testing mode)

### After 6 Hours:
- ✅ Parameter importance ranking starts
- ✅ Discovers which parameters matter most

### After 30 Days:
- ✅ First model training begins
- ✅ All 5+ models train simultaneously
- ✅ Performance logged separately for each

### After 31 Days:
- ✅ First predictions made
- ✅ System waits 24 hours for actual results

### After 32 Days:
- ✅ Prediction validation starts
- ✅ Errors calculated for each model
- ✅ Weights adjusted based on feedback

### After 37 Days (1 Week):
- ✅ Best model selected automatically
- ✅ Model performance comparison complete

### Continuous Operation:
- 🔄 Models retrain every 12 hours
- 🔄 Predictions validated daily
- 🔄 Weights adjusted daily
- 🔄 Best model updated weekly
- 🔄 Old data cleaned up automatically

## Monitoring

### Check System Status
All data in: `ML_System/Data/`

```bash
# View CSV files during testing
ML_System/Data/01_RawData/          # Raw sensor data
ML_System/Data/08_ModelComparison/  # Model performance logs
ML_System/Data/06_PredictionErrors/ # Prediction accuracy

# View model files
ML_System/Models/                    # Trained model files
```

### Check Logs
```bash
ML_System/Logs/                      # System logs
```

## Switching to Production (Parquet)

After testing, edit `config.yaml`:
```yaml
storage:
  testing_mode: false
  production_format: "parquet"
```

All new data will use Parquet (10x smaller, 100x faster).

## Background Processes

| Process | Interval | Purpose |
|---------|----------|---------|
| Data Collector | 1 min | Collect all sensor data |
| Parameter Discovery | 6 hours | Find important parameters |
| Model Trainer | 12 hours | Train all models |
| Prediction Validator | 24 hours | Check accuracy |
| Weight Adjuster | 24 hours | Improve models |
| Model Selector | 7 days | Pick best model |
| Cleanup | 24 hours | Remove old data |
| Health Monitor | 1 hour | System status |

## Key Features

✅ **Fully Async** - Zero system load  
✅ **Zero Hardcoding** - All from config  
✅ **Auto Discovery** - Finds important parameters  
✅ **Multi-Model** - 5+ models compete  
✅ **Self-Learning** - Improves daily  
✅ **CSV Testing** - Easy to inspect  
✅ **Parquet Production** - High performance  
✅ **Separate Logging** - Each model tracked  
✅ **Graceful Shutdown** - Ctrl+C safe  

## Troubleshooting

### No data collected?
- Check `data_collection.parameter_source` in config
- Verify OPC connection or CSV files exist
- Check logs in `ML_System/Logs/`

### Models not training?
- Need 30 days of data first
- Check `ML_System/Data/01_RawData/` has files
- Verify sufficient data points

### Service won't start?
- Run `python background_process_manager.py` to see errors
- Check Windows Event Viewer
- Verify all dependencies installed

## Next Steps

1. **Week 1-4**: Let system collect data and learn
2. **Week 5-8**: Monitor model performance
3. **Week 9-12**: Validate predictions accuracy
4. **Week 13+**: Deploy best model to production

The system learns YOUR specific turbine patterns automatically!
