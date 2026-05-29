# How to Start HistoricalTrends Application

## Quick Start

### Method 1: Using Virtual Environment Python (RECOMMENDED)

```cmd
cd "d:\Development\MQTT_Implemented_OPC\BACKUP_BEFORE_HISTORICAL_20251117_225747 - Copy_backup_20251206\HistoricalTrends"
venv\Scripts\python.exe app.py
```

**Why this method?**
- ✅ Uses venv with **numpy 1.26.4** (compatible version)
- ✅ Avoids system Anaconda with **numpy 2.4.2** (incompatible)
- ✅ No activation issues (bypass PowerShell execution policy)

---

### Method 2: Using Batch File (Easiest)

```cmd
cd "d:\Development\MQTT_Implemented_OPC\BACKUP_BEFORE_HISTORICAL_20251117_225747 - Copy_backup_20251206\HistoricalTrends"
start.bat
```

---

### Method 3: Activate Virtual Environment First

**PowerShell:**
```powershell
cd "d:\Development\MQTT_Implemented_OPC\BACKUP_BEFORE_HISTORICAL_20251117_225747 - Copy_backup_20251206\HistoricalTrends"
.\venv\Scripts\Activate.ps1
python app.py
```

**CMD:**
```cmd
cd "d:\Development\MQTT_Implemented_OPC\BACKUP_BEFORE_HISTORICAL_20251117_225747 - Copy_backup_20251206\HistoricalTrends"
venv\Scripts\activate.bat
python app.py
```

**Note**: If activation fails due to execution policy, use Method 1 instead.

---

## Common Issues

### Issue 1: NumPy Compatibility Error
```
ValueError: numpy.dtype size changed, may indicate binary incompatibility
```

**Cause**: System Python (Anaconda) has numpy 2.4.2, but app needs numpy 1.x

**Solution**: Use Method 1 (venv\Scripts\python.exe directly)

---

### Issue 2: PowerShell Execution Policy Error
```
cannot be loaded because its operation is blocked by software restriction policies
```

**Solution**: Use Method 1 (bypass activation entirely)

---

### Issue 3: "ModuleNotFoundError"

**Check venv packages:**
```cmd
venv\Scripts\python.exe -m pip list
```

**Verify numpy version (should be 1.26.4):**
```cmd
venv\Scripts\python.exe -c "import numpy; print(numpy.__version__)"
```

---

## Application Info

**Port**: 5001 (default)
**URL**: http://localhost:5001
**Database**: PostgreSQL (config in `trends-config.json`)
**Data Source**: Parquet files + PostgreSQL TimescaleDB

---

## Virtual Environment Details

**Location**: `.\venv\`
**Python**: 3.12
**Key Packages**:
- numpy 1.26.4 ✅ (compatible)
- pandas 2.3.3
- pyarrow 22.0.0
- flask 3.1.2
- scikit-learn 1.7.2
- statsmodels 0.14.5
- prophet 1.2.1

**System Python** (Anaconda):
- numpy 2.4.2 ❌ (incompatible - DO NOT USE)

---

## Startup Success Check

When started successfully, you should see:
```
 * Serving Flask app 'app'
 * Debug mode: on
WARNING: This is a development server. Do not use it in a production deployment.
 * Running on http://127.0.0.1:5001
Press CTRL+C to quit
```

---

## Stop Application

Press `CTRL+C` in the terminal

---

## Related Applications

**DB Query Tool** (Port 7005):
```cmd
cd "..\DB_Query"
python historian_query_tool_v2.py
```
URL: http://localhost:7005

**PostgresLogger** (Port 6001):
```cmd
cd "..\PostgresLogger"
python -m api.main
```
URL: http://localhost:6001

---

## Troubleshooting Commands

**Check if port 5001 is in use:**
```cmd
netstat -ano | findstr :5001
```

**Kill process on port 5001:**
```cmd
taskkill /PID <PID> /F
```

**Test venv Python:**
```cmd
venv\Scripts\python.exe --version
```

**Check imports:**
```cmd
venv\Scripts\python.exe -c "import pandas; import numpy; import flask; print('All imports OK')"
```

---

## Best Practice

✅ **ALWAYS use**: `venv\Scripts\python.exe app.py`
❌ **NEVER use**: `python app.py` (uses system Python with incompatible numpy)
