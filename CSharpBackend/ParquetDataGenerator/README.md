# Parquet Data Generator - Turbine Plant Simulation

## Overview
Complete modular system for generating realistic turbine plant data with automatic file transfer and optional backup.

## Features
- ✅ **Simulation Engine**: Generates realistic data for 21 turbine parameters
- ✅ **Downtime Simulation**: Random shutdowns with Load=0, Speed=0, null sensor values
- ✅ **Thread-Safe File Operations**: No deadlocks, safe concurrent read/write
- ✅ **File Transfer Service**: Auto-transfers from Simulation → Main directory
- ✅ **Optional Backup**: Copy files to custom location
- ✅ **Simple UI**: Monitor all services on port 5004

## Architecture
```
ParquetDataGenerator/
├── app.py                      # Flask UI (port 5004)
├── simulation_engine.py        # Data generation service
├── file_transfer_service.py   # File transfer service
├── backup_service.py           # Optional backup service
├── config.json                 # Configuration
├── requirements.txt            # Dependencies
└── templates/index.html        # UI
```

## Installation
```bash
cd ParquetDataGenerator
pip install -r requirements.txt
```

## Configuration (config.json)
```json
{
  "Paths": {
    "SimulationOutputDirectory": "D:\\Simulation\\Parquet",
    "MainDataDirectory": "D:\\OpcLogs\\Data",
    "BackupDirectory": null
  },
  "Simulation": {
    "IntervalSeconds": 5,
    "DowntimeEnabled": true,
    "DowntimeProbability": 0.05
  }
}
```

## Usage
```bash
python app.py
```
Open browser: http://localhost:5004

## Data Flow
1. **Simulation Engine** → Generates data → `D:\Simulation\Parquet`
2. **File Transfer Service** → Reads simulation files → Appends to → `D:\OpcLogs\Data`
3. **Backup Service** (Optional) → Copies from main directory → Custom location

## Thread Safety
- **File-based locking**: `.lock` files prevent concurrent writes
- **Atomic operations**: Temp file + rename for safe updates
- **Retry mechanism**: 10 retries with 0.5s delay
- **Works alongside C# service**: Both can write to `D:\OpcLogs\Data` safely

## Monitored Tags (21)
### Vibrations
- BEARING_VIB_HP_FRONT-X/Y
- BEARING_VIB_HP_REAR-X/Y
- BEARING_VIB_IP_REAR-X/Y
- SHAFT_VIB_HP_FRONT-X/Y
- SHAFT_VIB_HP_REAR-X/Y
- SHAFT_VIB_IP_REAR-X/Y

### Steam Parameters
- STEAM_TEMP_HP_INLET
- STEAM_TEMP_IP_INLET
- STEAM_PRESSURE_HP_INLET
- STEAM_PRESSURE_IP_INLET

### Performance
- TURBINE_SPEED
- GENERATOR_LOAD_MW
- CONDENSER_VACUUM
- LUBE_OIL_PRESSURE
- LUBE_OIL_TEMP

## Downtime Behavior
When downtime occurs:
- `GENERATOR_LOAD_MW` → 0
- `TURBINE_SPEED` → 0
- 30% of tags return `null` (sensor loss)
- Vibrations drop to minimum values
- Temperatures/Pressures drop 40-60%
