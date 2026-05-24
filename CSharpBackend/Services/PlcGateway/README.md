# PLC Gateway - Modular Multi-Protocol PLC Communication

## Architecture Overview

```
┌───────────────────────────────────────────────────────────────────────────────┐
│                            PLC GATEWAY DATA FLOW                               │
│                                                                                │
│   PLC Devices (Siemens, Rockwell, Modbus, ABB, Mitsubishi, Omron)            │
│   ├─ 192.168.1.10 (Siemens S7-1500)                                          │
│   ├─ 192.168.1.20 (Allen Bradley ControlLogix)                                │
│   ├─ 192.168.1.30 (Modbus TCP Device)                                         │
│   └─ 192.168.1.40 (ABB AC500)                                                 │
│                            │                                                   │
│                            ▼                                                   │
│    ┌────────────────────────────────────────────────────────────┐            │
│    │          PlcDataLoggingService (1000ms polling)            │            │
│    │   • Creates isolated worker per PLC                        │            │
│    │   • Each worker has own driver instance                    │            │
│    │   • Failures isolated - one PLC can't affect another       │            │
│    └────────────────────────────────────────────────────────────┘            │
│                            │                                                   │
│                            ▼                                                   │
│    ┌────────────────────────────────────────────────────────────┐            │
│    │           PlcTagValuesPoolService (SHARED CACHE)           │            │
│    │   • Thread-safe ConcurrentDictionary                       │            │
│    │   • Updated every 1000ms                                   │            │
│    │   • Tracks all PLCs, tags, qualities, timestamps           │            │
│    └────────────────────────────────────────────────────────────┘            │
│                            │                                                   │
│           ┌────────────────┼────────────────┐                                │
│           ▼                ▼                ▼                                 │
│    ┌──────────────┐ ┌──────────────┐ ┌──────────────┐                        │
│    │ PlcController│ │PlcHistorian  │ │PlcParquet    │                        │
│    │ (REST API)   │ │IngestService │ │LoggingService│                        │
│    │              │ │              │ │              │                        │
│    │ GET /api/plc │ │ Rate Control │ │ File Rotation│                        │
│    │   /values    │ │ (deadband)   │ │ (10MB/1hr)   │                        │
│    │   /stats     │ │              │ │              │                        │
│    │   /health    │ │ PostgreSQL   │ │ CSV/Parquet  │                        │
│    │   /tag/{id}  │ │ COPY batch   │ │ Files        │                        │
│    └──────────────┘ └──────────────┘ └──────────────┘                        │
│           │                │                │                                 │
│           ▼                ▼                ▼                                 │
│        HMI/UI          Database        File System                           │
│       Dashboard    plc_gateway.       D:\PlcLogs\Data\                       │
│                    plc_timeseries     {plcId}\{date}\                        │
└───────────────────────────────────────────────────────────────────────────────┘
```

## Isolated Worker Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           PLC GATEWAY MANAGER                                │
│                    (Manages all workers independently)                       │
└─────────────────────────────────────────────────────────────────────────────┘
          │                    │                    │                    │
          ▼                    ▼                    ▼                    ▼
    ┌──────────┐         ┌──────────┐         ┌──────────┐         ┌──────────┐
    │ WORKER A │         │ WORKER B │         │ WORKER C │         │ WORKER D │
    │ Siemens  │         │ Siemens  │         │ Rockwell │         │ Modbus   │
    │ PLC #1   │         │ PLC #2   │         │ PLC      │         │ Device   │
    └──────────┘         └──────────┘         └──────────┘         └──────────┘
          │                    │                    │                    │
    ┌──────────┐         ┌──────────┐         ┌──────────┐         ┌──────────┐
    │  DRIVER  │         │  DRIVER  │         │  DRIVER  │         │  DRIVER  │
    │ Instance │         │ Instance │         │ Instance │         │ Instance │
    └──────────┘         └──────────┘         └──────────┘         └──────────┘
          │                    │                    │                    │
          ▼                    ▼                    ▼                    ▼
    ┌─────────────────────────────────────────────────────────────────────────┐
    │                    PlcTagValuesPoolService                               │
    │                        (UNIFIED SHARED CACHE)                            │
    └─────────────────────────────────────────────────────────────────────────┘
```

## Key Design Principles

### 1. Complete Isolation
- **One Worker per PLC** - Each PLC runs in its own dedicated Task
- **Own Driver Instance** - No shared connections
- **Own Data Pool** - No data interference
- **Own Error State** - Failures don't cascade

### 2. No Interference
- PLC #1 failure does NOT affect PLC #2
- Same manufacturer PLCs work independently
- Different manufacturers work together
- Connection issues isolated to single PLC

### 3. Zero System Load Impact
- Workers run in parallel (async/await)
- Each polling loop independent
- No shared locks between PLCs
- Scalable to many PLCs

## Supported Protocols

| Protocol | Library | Default Port | Manufacturer |
|----------|---------|--------------|--------------|
| SiemensS7 | S7.Net | 102 | Siemens S7-300/400/1200/1500 |
| ModbusTcp | NModbus | 502 | Generic Modbus TCP |
| Rockwell | libplctag | 44818 | Allen Bradley ControlLogix/CompactLogix |
| EtherNetIP | libplctag | 44818 | Allen Bradley (legacy) |
| ABB | NModbus | 502 | ABB AC500, PM5xx |
| Mitsubishi | NModbus | 502 | Mitsubishi MELSEC |
| Omron | Native FINS | 9600 | Omron CJ/CS/NJ series |

## Usage

### 1. Add Services (Program.cs)

```csharp
// Add PLC Gateway services
builder.Services.AddPlcGateway();

// Or with configuration
builder.Services.AddPlcGateway(options =>
{
    options.DefaultPollingIntervalMs = 1000;
    options.ConfigRefreshInterval = TimeSpan.FromMinutes(5);
});
```

### 2. Configure appsettings.json

```json
{
  "ConnectionStrings": {
    "PlcGateway": "Host=localhost;Database=historian;Username=postgres;Password=xxx"
  },
  "PlcGateway": {
    "PollingIntervalMs": 1000,
    "HistorianPollIntervalMs": 1000,
    "HistorianBatchSize": 100,
    "DefaultWriteIntervalMs": 1000,
    "EnableParquetLogging": true,
    "ParquetOutputPath": "D:\\PlcLogs\\Data",
    "ParquetWriteIntervalMs": 5000,
    "ParquetMaxFileSizeBytes": 10485760
  }
}
```

### 3. Configure PLCs in Database

```sql
INSERT INTO plc_gateway.plc_connections 
(plc_id, plc_name, plant_id, protocol, ip_address, port, s7_config)
VALUES 
('SIEMENS_01', 'Production Line 1', 'PlantA', 'SiemensS7', '192.168.1.10', 102, 
 '{"CpuType": "S71500", "Rack": 0, "Slot": 1}');
```

### 4. Add Tags

```sql
INSERT INTO plc_gateway.plc_tags 
(plc_id, tag_id, tag_name, address, data_type, unit, db_logging_enabled, parquet_logging_enabled)
VALUES 
('SIEMENS_01', 'TEMP_01', 'Temperature', 'DB100.DBD0', 'float', '°C', true, true);
```

### 5. Access Data via API

```
GET /api/plc/values                    - All values from all PLCs
GET /api/plc/values/{plcId}           - Values from specific PLC
GET /api/plc/tag/{plcId}/{tagName}    - Single tag value
GET /api/plc/stats                     - Pool statistics
GET /api/plc/status                    - PLC connection status
GET /api/plc/health                    - Health check endpoint
POST /api/plc/values/query             - Query specific tags
```

## Example: Multiple Same-Manufacturer PLCs

```sql
-- Siemens PLC #1
INSERT INTO plc_gateway.plc_connections 
(plc_id, plc_name, protocol, ip_address, port, s7_config)
VALUES 
('SIEMENS_01', 'Line 1', 'SiemensS7', '192.168.1.10', 102, 
 '{"CpuType": "S71500", "Rack": 0, "Slot": 1}');

-- Siemens PLC #2 (COMPLETELY INDEPENDENT!)
INSERT INTO plc_gateway.plc_connections 
(plc_id, plc_name, protocol, ip_address, port, s7_config)
VALUES 
('SIEMENS_02', 'Line 2', 'SiemensS7', '192.168.1.11', 102, 
 '{"CpuType": "S71200", "Rack": 0, "Slot": 1}');
```

Both PLCs:
- Run in parallel
- Have separate connections
- Have separate data pools
- Can fail independently

## Worker Status

Each worker reports:
- `WorkerId` - Unique identifier
- `State` - Created/Running/Disconnected/Stopped
- `IsConnected` - Connection status
- `ConsecutiveFailures` - Error count
- `TotalPolls` / `SuccessfulPolls` / `FailedPolls`
- `AverageReadTimeMs` - Performance metric
- `TagCount` - Number of tags
- `LastError` - Most recent error

## Error Handling

```
Worker A (Siemens PLC #1) → Connection Lost
    ↓
Worker A enters Disconnected state
Worker A attempts reconnect
    ↓
Workers B, C, D continue normally! ✓
```

## NuGet Packages Required

```xml
<PackageReference Include="S7netplus" Version="0.20.0" />
<PackageReference Include="NModbus" Version="3.0.81" />
<PackageReference Include="libplctag" Version="1.6.0" />
<PackageReference Include="Npgsql" Version="8.0.0" />
```

## File Structure

```
Services/PlcGateway/
├── Interfaces/
│   └── IPlcDriver.cs              # Universal driver interface
├── Models/
│   └── PlcConfig.cs               # Configuration models
├── Drivers/
│   ├── PlcDriverFactory.cs        # Creates driver instances
│   ├── SiemensS7Driver.cs         # Siemens S7 protocol
│   ├── ModbusTcpDriver.cs         # Modbus TCP
│   ├── RockwellDriver.cs          # Allen Bradley/Rockwell
│   ├── EtherNetIpDriver.cs        # EtherNet/IP
│   ├── AbbDriver.cs               # ABB PLCs
│   ├── MitsubishiDriver.cs        # Mitsubishi MELSEC
│   └── OmronDriver.cs             # Omron FINS
├── Services/
│   ├── PlcWorker.cs               # Isolated worker per PLC
│   ├── PlcWorkerPool.cs           # Per-worker data pool
│   ├── PlcGatewayManager.cs       # Manages all workers
│   ├── PlcGatewayHostedService.cs # Background service
│   └── PlcConfigLoader.cs         # Loads from database
├── Controllers/
│   └── PlcGatewayController.cs    # REST API
├── PlcGatewayExtensions.cs        # DI registration
└── create_plc_gateway_schema.sql  # Database schema
```
