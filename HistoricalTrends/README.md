# Historical Trends Viewer - Python Analytics Module

A completely independent historical data viewer and advanced BI analytics engine for OPC parquet files with integrated simulation support.

## 🎯 System Overview

**Multi-Service Architecture**:
- **Historical Trends UI** (Port 5001) - Main analytics dashboard
- **BI API Service** (Port 8000) - Advanced BI calculations (FastAPI)
- **ParquetDataGenerator** (Port 5004) - Simulation engine for testing/development

## Features

### 📊 Historical Trends Viewer (Port 5001)
- **Rich SCADA-Style Interface** - Professional gradient UI with interactive charts
- **Date/Time Range Selection** - Browse historical data by custom date ranges
- **Multi-Tag Support** - Select and view multiple tags simultaneously (21 tags supported)
- **Combined & Separate Views** - View trends together or in individual charts
- **Export Capabilities** - Export to CSV or Excel format
- **Interactive Charts** - Powered by Plotly.js with zoom, pan, and hover features

### 🤖 Advanced BI Analytics (Port 8000)
- **Adaptive Baseline Engine** - Dynamic baseline calculations with outlier detection
- **Efficiency Analysis** - Weighted efficiency metrics for plant performance
- **Influence Correlation** - Pearson/Spearman correlation analysis
- **Stability Scoring** - Performance stability assessments
- **Production Loss Attribution** - Identify root causes of production losses
- **Multi-User Sessions** - Isolated per-user calculation contexts

### 🔄 Data Integration
- **Real-Time OPC DA Data** - Live data from C# backend (Port 6100)
- **Simulated Data** - Test data from ParquetDataGenerator (Port 5004)
- **Unified Analytics** - Processes both real and simulated data seamlessly
- **Parquet File Format** - Efficient columnar storage with Snappy compression

## Installation

### Quick Start (Historical Trends)
1. Make sure Python 3.8+ is installed
2. Run `start.bat` to install dependencies and start the service
3. Service will run on `http://localhost:5001`

### Manual Installation

```bash
# Install historical trends dependencies
pip install -r requirements.txt

# Start Historical Trends UI
python app.py

# (Optional) Start BI API Service
python bi_api.py

# (Optional) Start ParquetDataGenerator
cd ..\ParquetDataGenerator
python app.py
```

## Integration with Main OPC DA Application

### ASP.NET Core Integration
Add a new tab to your ASP.NET application that loads:
```html
<iframe src="http://localhost:5001" width="100%" height="100%"></iframe>
```

### Production Data Flow Architecture (Real Plant)
```
OPC DA Servers (Plant Equipment)
          ↓ OPC DA Protocol
C# ASP.NET Core Backend (Port 6100)
    ├── OpcDaService: Multi-server connection management
    ├── DataLoggingService: Reads tags every 5 seconds
    ├── SignalR: Real-time broadcasting to web UI
    └── Parquet Writer: Creates .parquet files directly
          ↓ Direct Write (2MB rotation)
D:\OpcLogs\Data\ALL_SENSORS_COMPLETE_FORWARDFILL.parquet
          ↓ Read
    ┌─────────────────────────────────┐
    │                                 │
    ↓                                 ↓
Historical Trends (5001)      BI Analytics Engine (8000)
    ├── Trend charts                  ├── Baseline analysis
    ├── Data export                   ├── Efficiency metrics
    └── Tag selection                 └── Correlations
```

### Testing Data Flow (Development Only)
```
ParquetDataGenerator (Port 5004) ⚠️ TESTING ONLY
    ├── Simulates 21 plant tags
    ├── Generates realistic data ranges
    └── Creates test parquet files
          ↓ Write to D:\Simulation\Parquet\
File Transfer Service (Optional)
          ↓ Merge for testing
D:\OpcLogs\Data\ALL_SENSORS_COMPLETE_FORWARDFILL.parquet
          ↓ Same as production
Historical Trends (5001) + BI Analytics (8000)
```

## Configuration

### Main Configuration File
The service automatically reads `logging-config.json` to determine:
- `DataLogDirectory` - Primary parquet file location (e.g., `D:\OpcLogs\Data`)
- `BackupDirectory` - Backup parquet file location
- `ApplicationLogDirectory` - Application logs (Serilog)

Example `logging-config.json`:
```json
{
  "LoggingPaths": {
    "DataLogDirectory": "D:\\OpcLogs\\Data",
    "BackupDirectory": "D:\\OpcLogs\\Backup",
    "ApplicationLogDirectory": "D:\\OpcLogs\\AppLogs"
  },
  "DataLogging": {
    "IntervalSeconds": 5,
    "Enabled": true
  },
  "SelectedTags": [
    "Random.Real4",
    "Random.Real8",
    "Random.Int1",
    // ... 21 tags total
  ]
}
```

### BI Analytics Configuration
`derived_analytics_config.json` - Controls BI engine calculations
`bi_config.yaml` - Plant-specific thresholds and parameters

### Simulation Configuration
See `../ParquetDataGenerator/config.json` for simulation settings

## API Endpoints

### Historical Trends Service (Port 5001)
- `GET /` - Main UI dashboard
- `GET /api/files` - List available parquet files
- `GET /api/tags` - Get all available tags (21 tags)
- `GET /api/data` - Get trend data (params: start_date, end_date, tags)
- `GET /api/export/csv` - Export selected data to CSV
- `GET /api/export/excel` - Export selected data to Excel

### BI Analytics Service (Port 8000)
- `POST /api/bi/analyze` - Run BI analysis on dataset
- `GET /api/bi/baseline` - Calculate adaptive baseline
- `GET /api/bi/efficiency` - Compute efficiency metrics
- `GET /api/bi/correlations` - Analyze tag correlations
- `GET /api/bi/stability` - Performance stability scoring

### ParquetDataGenerator Service (Port 5004)
- `GET /` - Simulation control dashboard
- `GET /api/status` - System and service status
- `POST /api/simulation/start` - Start data generation
- `POST /api/simulation/stop` - Stop data generation
- `POST /api/transfer/start` - Start file transfer service
- `POST /api/transfer/stop` - Stop file transfer service

## Data Sources

### Primary Data Source
**File**: `D:\OpcLogs\Data\ALL_SENSORS_COMPLETE_FORWARDFILL.parquet`

**Schema**:
```
Timestamp (timestamp[us])  - Microsecond precision UTC
TagId (string)            - Tag identifier (21 unique tags)
Value (float64)           - Sensor reading value
```

**21 Supported Tags**:
- Random.Real4, Random.Real8
- Random.Int1, Random.Int2, Random.Int4
- Random.Money, Random.Boolean
- Random.String
- Triangle Waves, Sawtooth Waves, Square Waves
- Bucket Brigade (various)
- SimulatedData.Random (various)
- And more...

### Simulation Data Source
**Location**: `D:\Simulation\Parquet\simulation_YYYYMMDD.parquet`

**Purpose**: 
- Testing without live OPC DA servers
- Development data generation
- Performance testing with realistic ranges
- Downtime event simulation

**Integration**: File Transfer Service automatically merges simulation data into main data file

## Technology Stack

### Backend Services
- **Flask** (Historical Trends) - Web framework for UI service
- **FastAPI** (BI Analytics) - High-performance async API
- **Pandas** - Data manipulation and analysis
- **PyArrow** - Parquet file I/O (10x-50x faster than pure Python)
- **NumPy** - Numerical computations
- **SciPy** - Statistical analysis
- **Scikit-learn** - Machine learning algorithms

### Frontend
- **HTML5 + CSS3** - Modern responsive design
- **JavaScript** - Interactive functionality
- **Plotly.js** - Professional charting library
- **Flatpickr** - Date/time picker
- **Modular Architecture** - ES6 modules for code organization

### Data Storage
- **Apache Parquet** - Columnar storage format
- **Snappy Compression** - Fast compression/decompression
- **Microsecond Timestamps** - High-precision time series

### C# Integration
- **ASP.NET Core 8.0** - Main application framework
- **SignalR** - Real-time data broadcasting
- **OpcRcw Libraries** - OPC DA COM interop
- **Serilog** - Structured logging

## Advanced Features

### Multi-Scale Visualization
Automatically handles different value ranges:
- Temperature (0-100°C) → Left Y-axis
- Pressure (0-150 PSI) → Right Y-axis
- Speed (1000-2000 RPM) → Left Y-axis (scaled)

### Downtime Tracking
- Automatic downtime event detection
- Duration tracking (30-300 seconds typical)
- Visual indicators in charts
- Statistical analysis of downtime patterns

### Performance Optimization
- Parquet row group optimization (2MB chunks)
- Memory-mapped file operations
- Batch processing for large datasets
- Client-side data caching
- Async I/O for file transfers

### Derived Analytics
- **Daily Production Metrics** - Calculated parquet files
- **Cache Invalidation** - Based on input data checksums
- **6 Metric Types**: Baseline, Deltas, Influence, Loss, Stability, Condition
- **Partition Strategy**: Daily parquet partitioning

## File Monitoring

### Check Parquet Files
```powershell
# List data files
Get-ChildItem "D:\OpcLogs\Data\*.parquet" | Select-Object Name, Length, LastWriteTime

# List simulation files
Get-ChildItem "D:\Simulation\Parquet\*.parquet" | Select-Object Name, Length, LastWriteTime

# Count records in main file
python -c "import pyarrow.parquet as pq; print(f'Records: {pq.read_table(\"D:\\OpcLogs\\Data\\ALL_SENSORS_COMPLETE_FORWARDFILL.parquet\").num_rows}')"
```

### Verify Data Integrity
```python
import pyarrow.parquet as pq
import pandas as pd

# Read parquet file
table = pq.read_table('D:\\OpcLogs\\Data\\ALL_SENSORS_COMPLETE_FORWARDFILL.parquet')
df = table.to_pandas()

# Check schema
print(table.schema)

# Verify timestamp range
print(f"First: {df['Timestamp'].min()}")
print(f"Last: {df['Timestamp'].max()}")

# Check tag counts
print(df['TagId'].value_counts())
```

## Troubleshooting

### Service Won't Start
```bash
# Check if port is already in use
netstat -ano | findstr :5001
netstat -ano | findstr :8000
netstat -ano | findstr :5004

# Kill process if needed
taskkill /PID <process_id> /F
```

### Parquet File Errors
- **Error**: "Could not convert 'string' to double"
  - **Fix**: Delete corrupted simulation files, restart ParquetDataGenerator
  
- **Error**: "File not found: ALL_SENSORS_COMPLETE_FORWARDFILL.parquet"
  - **Fix**: Check `logging-config.json` paths, ensure C# backend has logged data

### Performance Issues
- Check file sizes (2MB rotation recommended)
- Verify Snappy compression is enabled
- Monitor memory usage (should be <100MB per service)
- Use date range filtering to reduce data volume

## Related Documentation

- **Main System**: `README_WORKING_VERSION.md` (C# OPC DA application)
- **Simulation**: `../ParquetDataGenerator/PARQUET_GENERATOR_IMPLEMENTATION_SUMMARY.md`
- **BI Architecture**: `BI_ENGINE_PYTHON_BACKEND_README.md`
- **Modular Frontend**: `MODULAR_ARCHITECTURE.md`
- **API Chain**: `API_CHAIN_VERIFICATION.md`
- **Deployment**: `DEPLOYMENT_README.md`

## System Architecture Summary

### 🏭 PRODUCTION ARCHITECTURE (Real Plant)

**Complete OPC DA SCADA System**:
1. **OPC DA Servers** (Remote/Local) - Industrial plant data sources
   - Temperature, Pressure, Flow, Speed sensors
   - 21 tags monitored continuously

2. **C# ASP.NET Core Backend** (Port 6100) - **PRIMARY DATA SOURCE**
   - **OpcDaService**: Connects to OPC DA servers via COM
   - **DataLoggingService**: Polls tags every 5 seconds
   - **Parquet Writer**: Creates parquet files directly (2MB rotation)
   - **SignalR**: Real-time broadcasting to web UI
   - **Background Services**: DataLogging, LogBackup
   - **Output**: `D:\OpcLogs\Data\ALL_SENSORS_COMPLETE_FORWARDFILL.parquet`

3. **Historical Trends Analytics** (Port 5001) - **THIS MODULE**
   - Reads parquet files created by C# module
   - Trend visualization (multi-scale charts)
   - Data export (CSV/Excel)
   - Multi-tag analysis
   - Date range selection

4. **BI Analytics Engine** (Port 8000) - Advanced calculations
   - Reads same parquet files
   - Baseline analysis
   - Efficiency metrics
   - Correlation studies
   - Production loss attribution

### 🧪 TESTING ARCHITECTURE (Development Only)

5. **ParquetDataGenerator** (Port 5004) - ⚠️ **TESTING ONLY - NOT PRODUCTION**
   - **Purpose**: Test analytics without live OPC servers
   - Simulates 21 plant tags
   - Generates realistic data (ranges from real data)
   - Downtime simulation
   - **Output**: `D:\Simulation\Parquet\simulation_*.parquet`
   - **Optional**: File transfer to merge with main data for testing

## Note

This module is **completely independent** and does not interfere with any existing functionality of the OPC DA Web Browser application. All services can run simultaneously and share data through parquet files.

**Production Deployment** (Real Plant):
- ✅ **C# OPC Module (Port 6100)**: ALWAYS RUNNING - Creates parquet files from OPC DA servers
- ✅ **Historical Trends (Port 5001)**: ALWAYS RUNNING - Reads parquet files for analytics
- ✅ **BI API (Port 8000)**: START AS NEEDED - Advanced calculations when required
- ❌ **ParquetDataGenerator (Port 5004)**: NOT RUNNING - Testing/development only

**Development/Testing Deployment** (No Live Plant):
- ❌ **C# OPC Module (Port 6100)**: NOT NEEDED - No OPC servers to connect to
- ✅ **Historical Trends (Port 5001)**: RUNNING - Test analytics interface
- ✅ **BI API (Port 8000)**: RUNNING - Test BI calculations
- ✅ **ParquetDataGenerator (Port 5004)**: RUNNING - Creates test data

**Key Points**:
- **Production**: C# OPC Module creates ALL parquet files (no simulation needed)
- **Testing**: ParquetDataGenerator replaces C# OPC Module for testing
- **Historical Trends**: Always reads from `D:\OpcLogs\Data\*.parquet` regardless of source
