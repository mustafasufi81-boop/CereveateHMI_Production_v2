# Cereveate OPC DA / Analytics Platform - System Architecture Documentation

**Version:** 2.0  
**Date:** December 15, 2025  
**Platform:** Windows x86 (COM Interop Required)  
**Framework:** .NET 8.0 + Python 3.8+

---

## Table of Contents
1. [System Overview](#system-overview)
2. [Module 1: OPC DA Web Browser](#module-1-opc-da-web-browser)
3. [Module 2: Historian Database System](#module-2-historian-database-system)
4. [Module 3: Trend Analytics Module](#module-3-trend-analytics-module)
5. [Module 4: Archiver Service (Health Monitoring)](#module-4-archiver-service-health-monitoring)
6. [Data Flow Architecture](#data-flow-architecture)
7. [Configuration Management](#configuration-management)
8. [Deployment Guide](#deployment-guide)

---

## System Overview

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   CEREVEATE OPC DA / ANALYTICS PLATFORM                      │
│                         (Industrial SCADA System)                            │
└─────────────────────────────────────────────────────────────────────────────┘

OPC DA Servers (Local/Remote via DCOM)
         ↓
┌────────────────────────────────────────────────────────────────────────────┐
│  MODULE 1: OPC DA WEB BROWSER (C# ASP.NET Core - Port 5000)                │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│  ├─ OpcDaService (Multi-Server Connection Manager)                          │
│  ├─ SignalR Hub (Real-Time Broadcasting - /opcHub)                          │
│  ├─ TagValuesPoolService (Shared In-Memory Cache)                           │
│  └─ Web UI (Server Discovery, Tag Monitoring, Live Data)                    │
└────────────────────────────────────────────────────────────────────────────┘
         ↓                    ↓                           ↓
    [Event: TagValuesUpdated - Broadcast to 3 Parallel Pipelines]
         ↓                    ↓                           ↓
┌─────────────────┐  ┌──────────────────┐  ┌───────────────────────────────┐
│ DataLogging     │  │ MODULE 2:        │  │ MODULE 4: Archiver Service    │
│ Service         │  │ HISTORIAN DB     │  │ (Health Monitoring)           │
│                 │  │                  │  │                               │
│ Parquet Writer  │  │ HistorianIngest  │  │ LogBackupService              │
│ (Selected Tags) │  │ (All Mapped)     │  │ - Consolidates 10MB→200MB    │
│ 10MB rotation   │  │ PostgreSQL       │  │ - Atomic operations           │
│                 │  │ TimescaleDB      │  │ - Health metrics push         │
└─────────────────┘  └──────────────────┘  └───────────────────────────────┘
         ↓                    ↓                           ↓
         ↓                    ↓                 ┌─────────────────────┐
         ↓                    ↓                 │ HealthStatusService │
         ↓                    ↓                 │ (Central Cache)     │
         ↓                    ↓                 │ - Volatile fields   │
         ↓                    ↓                 │ - Zero-lock reads   │
         ↓                    ↓                 │ - <1ms response     │
         ↓                    ↓                 └─────────────────────┘
    D:\OpcLogs\Data\    historian_raw.               ↓
    *.parquet           historian_timeseries    Web UI Health Tab
         ↓                    ↓                  (Auto-refresh 3s)
         ↓                    ↓
┌────────────────────────────────────────────────────────────────────────────┐
│  MODULE 3: TREND ANALYTICS (Python - Port 5001)                             │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│  ├─ Historical Trends Viewer (Flask - Port 5001)                            │
│  │  └─ Parquet File Reader → Plotly Charts → CSV/Excel Export              │
│  │                                                                           │
│  ├─ BI Analytics Engine (FastAPI - Port 8000)                               │
│  │  ├─ Adaptive Baseline Calculation                                        │
│  │  ├─ Efficiency Scoring (Weighted Metrics)                                │
│  │  ├─ Influence Correlation (Pearson/Spearman)                             │
│  │  ├─ Stability Analysis                                                   │
│  │  └─ Production Loss Attribution                                          │
│  │                                                                           │
│  └─ PostgresLogger (Optional TimescaleDB Importer - Port 6001)              │
│     ├─ Parquet → PostgreSQL Importer                                        │
│     ├─ FastAPI Trends Service                                               │
│     └─ WebSocket Live Data (/ws/live-data)                                  │
└────────────────────────────────────────────────────────────────────────────┘
```

### System Components Summary

| Module | Technology | Port | Purpose | Data Storage |
|--------|-----------|------|---------|--------------|
| **OPC DA Web** | C# ASP.NET Core | 5000 | OPC server connectivity, real-time monitoring | In-Memory Cache |
| **Historian DB** | C# + PostgreSQL | 5432 | Database historian for ALL mapped tags | TimescaleDB Hypertable |
| **Trend Analytics** | Python (Flask) | 5001 | Historical analysis & visualization | Reads Parquet Files |
| **BI Engine** | Python (FastAPI) | 8000 | Advanced analytics & correlations | Stateless (computes on-demand) |
| **PostgresLogger** | Python (FastAPI) | 6001 | Optional DB trends viewer | TimescaleDB (separate instance) |
| **Archiver** | C# Background Service | N/A | Health monitoring + parquet consolidation | D:\OpcLogs\Backup |

---

## Module 1: OPC DA Web Browser

### Overview
Core C# ASP.NET application providing OPC DA connectivity, real-time data acquisition, and web-based monitoring interface.

### Key Components

#### 1.1 OpcDaService (Multi-Server Connection Manager)
**File:** `Services/OpcDaService.cs`

**Purpose:** Singleton service managing multiple concurrent OPC DA server connections

**Key Features:**
- ✅ Multi-server support (multiple simultaneous connections)
- ✅ Local server discovery (automatic)
- ✅ Remote server discovery via DCOM (requires proper COM casting)
- ✅ Connection pooling and lifecycle management
- ✅ Health status integration

**Critical Pattern - Remote Discovery:**
```csharp
// MUST use out object then cast to avoid E_NOINTERFACE
serverList.EnumClassesOfCategories(1, new Guid[] { catid }, 0, null!, out object enumGuidObj);
OpcRcw.Comn.IEnumGUID enumGuid = (OpcRcw.Comn.IEnumGUID)enumGuidObj;
```

**API Methods:**
- `DiscoverServers()` - Local server discovery
- `DiscoverRemoteServers(string host)` - Remote DCOM discovery
- `ConnectToServer(string progId, string host)` - Establish connection
- `GetActiveConnection()` - Get preferred connection for historian
- `GetAllConnections()` - List all active connections

#### 1.2 OpcServerConnection (Per-Server Polling)
**File:** `Services/OpcServerConnection.cs`

**Purpose:** Individual OPC server connection with autonomous polling

**Key Features:**
- ✅ Timer-based polling (1000ms default)
- ✅ Async read operations (IOPCAsyncIO2)
- ✅ Quality code handling (OPC DA quality flags)
- ✅ Auto-reconnection logic
- ✅ Per-connection statistics

**Event Emission:**
```csharp
public event EventHandler<TagValuesEventArgs>? TagValuesUpdated;
```

**Tag Reading Flow:**
```
Timer (1000ms) → ReadTagValues() → IOPCAsyncIO2.Read() 
    → OnReadComplete callback → Raise TagValuesUpdated event
    → OpcDaService aggregates → Broadcast to subscribers
```

#### 1.3 SignalR Hub (Real-Time Broadcasting)
**File:** `Hubs/OpcDaHub.cs`

**Purpose:** WebSocket-based real-time communication with web clients

**Key Features:**
- ✅ Client-specific tag subscriptions (reduces network by 95%)
- ✅ Broadcast throttling (200ms minimum interval)
- ✅ Zero-allocation filtering (performance optimized)
- ✅ Graceful disconnect handling

**Critical Pattern - Event Subscription:**
```csharp
// MUST use async lambda to avoid async void
_opcDaService.TagValuesUpdated += async (s, e) => await OnTagValuesUpdatedAsync(s, e);
```

**High-Performance Optimization:**
- Clients subscribe to specific tags: `hub.invoke("SubscribeToTags", [tagIds])`
- Server filters before sending (avoids broadcasting 10K+ tags to all clients)
- Thread-safe snapshot prevents collection modified exceptions

#### 1.4 TagValuesPoolService (Shared Cache)
**File:** `Services/TagValuesPoolService.cs`

**Purpose:** Central in-memory cache for tag values (shared by Parquet + Historian)

**Key Features:**
- ✅ ConcurrentDictionary for thread-safe access
- ✅ Timestamp tracking (last update per tag)
- ✅ Zero-lock reads (volatile pattern)
- ✅ Automatic cleanup of stale values

#### 1.5 DataLoggingService (Parquet Writer)
**File:** `Services/DataLoggingService.cs`

**Purpose:** Background service writing **SELECTED TAGS** to Parquet files

**Key Features:**
- ✅ Configurable tag selection (`logging-config.json` → SelectedTags)
- ✅ File rotation at 10MB threshold
- ✅ Atomic write pattern (temp file + rename)
- ✅ Thread-safe file locking
- ✅ WAL (Write-Ahead Log) for stress testing

**Configuration:**
```json
{
  "SelectedTags": [
    "GENERATOR_LOAD_MW",
    "TURBINE_SPEED",
    "STEAM_PRESSURE_BAR"
  ],
  "LoggingIntervalMs": 5000
}
```

**Parquet Schema:**
```csharp
RowId (long), TagId (string), Timestamp (DateTime), Value (string), Quality (string)
```

**File Rotation:**
- Current file grows until 10MB
- Lock acquired → Write to temp file → Rename → Release lock
- New file created automatically

### REST API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/opc/servers` | GET | Discover local OPC servers |
| `/api/opc/servers/remote` | POST | Discover remote servers (DCOM) |
| `/api/opc/connect` | POST | Connect to OPC server |
| `/api/opc/disconnect` | POST | Disconnect from server |
| `/api/opc/status` | GET | Connection status |
| `/api/opc/tags` | GET | Browse tags |
| `/api/opc/tags/monitor` | POST | Add tag to monitor list |
| `/api/opc/tags/read` | POST | Read tag values |

### Web UI Features

**Tabs:**
1. **Server Browser** - Discover and connect to OPC servers
2. **Health Monitor** - System health dashboard (3-second auto-refresh)
3. **Tag Monitor** - Real-time tag value display
4. **Log Viewer** - Historical parquet file viewer with trends
5. **Configuration** - System settings management

**SignalR Events:**
- `TagValuesUpdated` - Real-time tag value updates
- `ConnectionStatusChanged` - Connection state changes
- `ErrorOccurred` - Error notifications

---

## Module 2: Historian Database System

### Overview
Enterprise-grade database historian writing **ALL MAPPED TAGS** to PostgreSQL/TimescaleDB with high-performance binary COPY protocol.

### Architecture

```
OPC TagValuesUpdated Event
         ↓
┌────────────────────────────────────────────────────────────────┐
│  HistorianIngestHostedService (Orchestrator)                   │
│  - Subscribes to OPC events                                    │
│  - Reads from GetActiveConnection() (reuses main OPC)          │
│  - NO duplicate connections                                    │
└────────────────────────────────────────────────────────────────┘
         ↓
┌────────────────────────────────────────────────────────────────┐
│  MappingCacheService (Tag Registry)                            │
│  - Loads from historian_meta.tag_master table                  │
│  - PostgreSQL NOTIFY trigger for auto-refresh                  │
│  - In-memory cache for fast lookups                            │
└────────────────────────────────────────────────────────────────┘
         ↓
┌────────────────────────────────────────────────────────────────┐
│  RateControllerService (Frequency Filter)                      │
│  - Per-tag sampling interval (1s-60s configurable)             │
│  - Change detection (only log when value changes)              │
│  - In-memory timestamp tracking                                │
└────────────────────────────────────────────────────────────────┘
         ↓
┌────────────────────────────────────────────────────────────────┐
│  BatcherService (Data Aggregation)                             │
│  - Sharded batching (8 shards default)                         │
│  - Flush triggers: MaxRows (1000), MaxBytes (1MB), MaxWait (5s)│
│  - Thread-safe concurrent queues                               │
└────────────────────────────────────────────────────────────────┘
         ↓
┌────────────────────────────────────────────────────────────────┐
│  DbWriterService (PostgreSQL Writer)                           │
│  - Binary COPY protocol (fastest PostgreSQL insert method)     │
│  - Automatic failover to SpoolManager on error                 │
│  - Connection pooling with Npgsql                              │
└────────────────────────────────────────────────────────────────┘
         ↓                                    ↓ (on DB failure)
PostgreSQL TimescaleDB              ┌────────────────────────┐
historian_raw.                      │  SpoolManagerService   │
historian_timeseries                │  - Disk-based failover │
(hypertable)                        │  - Auto-replay on DB   │
                                    │    recovery            │
                                    └────────────────────────┘
```

### Key Components

#### 2.1 HistorianIngestHostedService
**File:** `Services/HistorianIngest/Services/HistorianIngestHostedService.cs`

**Purpose:** Main orchestrator coordinating the historian pipeline

**Key Features:**
- ✅ Subscribes to OPC `TagValuesUpdated` event
- ✅ **Reuses main OPC connection** (calls `GetActiveConnection()`)
- ✅ Filters by enabled tag mappings only
- ✅ Health status reporting
- ✅ Graceful shutdown with flush

**Critical Pattern:**
```csharp
// REUSE main OPC connection - DO NOT create duplicate
var activeConnection = _opcService.GetActiveConnection();
if (activeConnection == null) return;

var tagValues = activeConnection.ReadTagValues(enabledTagIds);
```

#### 2.2 MappingCacheService
**File:** `Services/HistorianIngest/Services/MappingCacheService.cs`

**Purpose:** In-memory cache of tag mappings from `historian_meta.tag_master`

**Key Features:**
- ✅ PostgreSQL NOTIFY/LISTEN for real-time updates
- ✅ 30-second fallback polling
- ✅ Version tracking for change detection
- ✅ Thread-safe concurrent collections

**Database Table: historian_meta.tag_master**
```sql
CREATE TABLE historian_meta.tag_master (
    tag_id VARCHAR(255) PRIMARY KEY,
    tag_name VARCHAR(255) NOT NULL,
    data_type VARCHAR(50),
    db_logging_interval_ms INT DEFAULT 1000,
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by VARCHAR(100)
);
```

**CRITICAL: Empty table = no DB writes!**
```sql
-- Add mappings manually or via API
INSERT INTO historian_meta.tag_master (tag_id, tag_name, data_type, enabled)
VALUES ('Random.Real4', 'Random Value', 'Double', true)
ON CONFLICT (tag_id) DO UPDATE SET enabled = true;
```

#### 2.3 RateControllerService
**File:** `Services/HistorianIngest/Services/RateControllerService.cs`

**Purpose:** Per-tag frequency filtering and change detection

**Key Features:**
- ✅ Sampling frequency per tag (default 1000ms)
- ✅ Change detection (±0.1% threshold)
- ✅ In-memory last-value tracking
- ✅ Reduces DB writes by 70-90%

**Algorithm:**
```csharp
if (now - lastTimestamp < samplingInterval) return false; // Too soon
if (Math.Abs(newValue - lastValue) < changeThreshold) return false; // No change
return true; // Write to DB
```

#### 2.4 BatcherService
**File:** `Services/HistorianIngest/Services/BatcherService.cs`

**Purpose:** Sharded batch aggregation for high throughput

**Key Features:**
- ✅ 8 shards (configurable) for parallel processing
- ✅ Multiple flush triggers (rows, bytes, time)
- ✅ Lock-free concurrent queues
- ✅ Automatic batch optimization

**Flush Triggers:**
- **MaxRows:** 1000 records per batch
- **MaxBytes:** 1MB per batch
- **MaxWaitMs:** 5000ms maximum wait time

#### 2.5 DbWriterService
**File:** `Services/HistorianIngest/Services/DbWriterService.cs`

**Purpose:** High-performance PostgreSQL writer using binary COPY

**Key Features:**
- ✅ Binary COPY protocol (10x faster than INSERT)
- ✅ Npgsql connection pooling
- ✅ Automatic spool failover on DB error
- ✅ Retry logic with exponential backoff

**Performance:**
- 10K tags @ 1Hz = 10,000 rows/second
- Binary COPY can handle 50K+ rows/second
- TimescaleDB compression after 7 days

#### 2.6 SpoolManagerService
**File:** `Services/HistorianIngest/Services/SpoolManagerService.cs`

**Purpose:** Disk-based failover for database outages

**Key Features:**
- ✅ Binary format spool files
- ✅ Automatic replay when DB recovers
- ✅ FIFO processing (oldest first)
- ✅ Spool size monitoring

**Spool Directory:**
```
D:\OpcLogs\Spool\
  ├─ spool_20251215_143022.bin
  ├─ spool_20251215_143027.bin
  └─ ...
```

### Database Schema

**Schema: historian_raw**
```sql
CREATE TABLE historian_raw.historian_timeseries (
    timestamp TIMESTAMPTZ NOT NULL,
    tag_id VARCHAR(255) NOT NULL,
    value DOUBLE PRECISION,
    quality SMALLINT,
    PRIMARY KEY (timestamp, tag_id)
);

-- Convert to TimescaleDB hypertable
SELECT create_hypertable('historian_raw.historian_timeseries', 'timestamp');
```

**Schema: historian_meta (Tag Mappings)**
```sql
CREATE SCHEMA historian_meta;
CREATE TABLE historian_meta.tag_master (
    tag_id VARCHAR(255) PRIMARY KEY,
    tag_name VARCHAR(255) NOT NULL,
    data_type VARCHAR(50),
    db_logging_interval_ms INT DEFAULT 1000,
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by VARCHAR(100)
);
```

### Configuration (appsettings.json)

```json
{
  "Historian": {
    "Database": {
      "ConnectionString": "Host=localhost;Port=5432;Database=historian;Username=postgres;Password=yourpassword",
      "CommandTimeout": 30,
      "MaxPoolSize": 20
    },
    "Batch": {
      "MaxRows": 1000,
      "MaxBytes": 1048576,
      "MaxWaitMs": 5000
    },
    "Writer": {
      "ShardCount": 8,
      "RetryAttempts": 3,
      "RetryDelayMs": 1000
    },
    "Spool": {
      "Directory": "D:\\OpcLogs\\Spool",
      "MaxSizeMB": 1000,
      "ReplayBatchSize": 5000
    }
  }
}
```

### API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/historian/mapping` | GET | List all tag mappings |
| `/api/historian/mapping` | POST | Add new tag mapping |
| `/api/historian/mapping/{tagId}` | PUT | Update tag mapping |
| `/api/historian/mapping/{tagId}` | DELETE | Delete tag mapping |
| `/api/historian/health/live` | GET | Liveness probe |
| `/api/historian/health/ready` | GET | Readiness probe (checks DB) |
| `/api/historian/metrics` | GET | Prometheus metrics |

---

## Module 3: Trend Analytics Module

### Overview
Python-based historical data analysis and visualization platform with advanced BI capabilities.

### Sub-Components

#### 3.1 Historical Trends Viewer (Flask - Port 5001)
**Directory:** `HistoricalTrends/`

**Purpose:** Web-based parquet file viewer with trend charts and data export

**Key Features:**
- ✅ Date/time range selection
- ✅ Multi-tag trend charts (Plotly.js)
- ✅ Combined & separate view modes
- ✅ CSV/Excel export
- ✅ Auto-refresh capabilities
- ✅ 21 supported tags (configurable)

**Startup:**
```bash
cd HistoricalTrends
python app.py
# Access: http://localhost:5001
```

**Data Source:**
```python
PARQUET_FILE = "D:\\OpcLogs\\Data\\ALL_SENSORS_COMPLETE_FORWARDFILL.parquet"
```

**UI Tabs:**
- **Live Data** - Real-time values (3-second refresh)
- **Historical Trends** - Date range queries with charts
- **Statistics** - Tag statistics and data quality

#### 3.2 BI Analytics Engine (FastAPI - Port 8000)
**Directory:** `HistoricalTrends/` (bi_api.py)

**Purpose:** Advanced stateless analytics engine for KPI calculations

**Key Features:**
- ✅ Adaptive baseline calculation
- ✅ Weighted efficiency scoring
- ✅ Influence correlation (Pearson/Spearman)
- ✅ Stability analysis
- ✅ Production loss attribution
- ✅ Multi-user session isolation

**Startup:**
```bash
cd HistoricalTrends
uvicorn bi_api:app --port 8000
# API Docs: http://localhost:8000/docs
```

**Analytics Engines:**

**Baseline Engine** (`bi_engines/adaptive_baseline_engine.py`)
- Dynamic baseline calculation with seasonal adjustment
- Outlier detection (IQR method)
- Confidence interval calculation
- Deviation scoring

**Efficiency Engine** (`bi_engines/efficiency_engine.py`)
- Multi-parameter weighted scoring
- Target-based efficiency calculation
- Performance trend analysis

**Correlation Engine** (`bi_engines/influence_correlation_engine.py`)
- Pearson correlation (linear relationships)
- Spearman correlation (monotonic relationships)
- Time-lagged correlation analysis
- Correlation matrix generation

**Stability Engine** (`bi_engines/stability_engine.py`)
- Standard deviation analysis
- Coefficient of variation (CV)
- Range analysis
- Process capability metrics

**API Endpoints:**
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/bi/baseline` | POST | Calculate adaptive baseline |
| `/api/bi/efficiency` | POST | Calculate efficiency scores |
| `/api/bi/correlation` | POST | Calculate correlations |
| `/api/bi/stability` | POST | Calculate stability metrics |
| `/api/bi/attribution` | POST | Production loss attribution |

#### 3.3 PostgresLogger (Optional - Port 6001)
**Directory:** `PostgresLogger/`

**Purpose:** Parquet → PostgreSQL importer with TimescaleDB trends viewer

**Key Features:**
- ✅ High-performance parquet importer
- ✅ File hash tracking (idempotent)
- ✅ Tag catalog auto-discovery
- ✅ FastAPI trends API
- ✅ WebSocket live data stream

**Database Schema:**
```sql
-- sensor_data (TimescaleDB hypertable)
CREATE TABLE sensor_data (
    id BIGSERIAL,
    timestamp TIMESTAMPTZ NOT NULL,
    ingest_timestamp TIMESTAMPTZ DEFAULT NOW(),
    plant VARCHAR(100),
    asset VARCHAR(100),
    subsystem VARCHAR(100),
    tag_name VARCHAR(255),
    tag_code VARCHAR(100),
    value DOUBLE PRECISION,
    raw_value TEXT,
    unit VARCHAR(50),
    quality_code VARCHAR(50),
    status_flag VARCHAR(50),
    data_source VARCHAR(100),
    sensor_id VARCHAR(100),
    shift VARCHAR(20),
    batch_id VARCHAR(100),
    PRIMARY KEY (timestamp, tag_code)
);

-- tag_catalog (auto-discovery)
CREATE TABLE tag_catalog (
    tag_id VARCHAR(255) PRIMARY KEY,
    first_seen TIMESTAMPTZ,
    last_seen TIMESTAMPTZ,
    last_file TEXT,
    record_count BIGINT,
    is_mapped BOOLEAN DEFAULT false,
    last_updated TIMESTAMPTZ
);

-- file_imports (import tracking)
CREATE TABLE file_imports (
    id SERIAL PRIMARY KEY,
    file_path TEXT,
    file_hash VARCHAR(64),
    file_size BIGINT,
    import_timestamp TIMESTAMPTZ,
    records_imported INT,
    status VARCHAR(20), -- PENDING, PROCESSING, SUCCESS, FAILED
    error_message TEXT,
    processing_time_ms INT,
    UNIQUE (file_path, file_hash)
);
```

**Startup:**
```bash
cd PostgresLogger
START_ALL.bat  # Starts web server + importer
# Access: http://localhost:6001
```

**Configuration:** `PostgresLogger/config/app_config.json`
```json
{
  "database": {
    "host": "localhost",
    "port": 5432,
    "database": "sensor_db",
    "user": "postgres",
    "password": "yourpassword"
  },
  "parquet_source": "D:\\OpcLogs\\Data",
  "import_settings": {
    "check_interval_seconds": 60,
    "batch_size": 1000,
    "concurrent_workers": 2
  }
}
```

---

## Module 4: Archiver Service (Health Monitoring)

### Overview
Background service providing system health monitoring and parquet file consolidation.

### Components

#### 4.1 LogBackupService (Archiver)
**File:** `Services/LogBackupService.cs`

**Purpose:** Consolidate multiple small parquet files into 200MB archives

**Key Features:**
- ✅ Hourly execution (configurable)
- ✅ Atomic operations (temp file strategy)
- ✅ Oldest-first processing
- ✅ Automatic cleanup after successful archive
- ✅ Crash recovery (restarts fresh)
- ✅ Skip locked files (non-blocking)

**Archive Flow:**
```
D:\OpcLogs\Data\
  ├─ ALL_SENSORS_001.parquet (10MB)
  ├─ ALL_SENSORS_002.parquet (10MB)
  └─ ALL_SENSORS_003.parquet (10MB)
              ↓ (Archive Process)
D:\OpcLogs\Backup\
  ├─ Archive_20251215_140000.parquet (200MB)
  └─ Logs\
      └─ archive_20251215.log
```

**Health Metrics:**
- Unarchived files count
- Archive files count
- Current archive size
- Last archive time
- Error count

#### 4.2 HealthStatusService (Central Cache)
**File:** `Services/Health/HealthStatusService.cs`

**Purpose:** Thread-safe central cache for all system health metrics

**Key Features:**
- ✅ Volatile fields (lock-free reads)
- ✅ PUSH architecture (services update cache)
- ✅ <1ms read time
- ✅ Weighted health scoring
- ✅ Automatic alert calculation

**Health Models:**
```csharp
public record SystemHealthSnapshot
{
    public DateTime Timestamp { get; init; }
    public string OverallStatus { get; init; }  // Healthy, Degraded, Critical, Offline
    public double OverallHealthScore { get; init; }  // 0-100
    
    public OpcHealth Opc { get; init; }
    public DbWriterHealth DbWriter { get; init; }
    public SpoolHealth Spool { get; init; }
    public ArchiverHealth Archiver { get; init; }
    public ResourceHealth Resources { get; init; }
    
    public int ActiveAlerts { get; init; }
    public int WarningCount { get; init; }
    public int ErrorCount { get; init; }
}
```

**Health Score Weighting:**
```
Overall Score = 
    OPC (30%) + 
    DB Writer (25%) + 
    Spool (15%) + 
    Archiver (10%) + 
    Resources (20%)
```

**Status Thresholds:**
- **Healthy:** Score ≥ 90%
- **Degraded:** Score ≥ 70%
- **Critical:** Score ≥ 50%
- **Offline:** Score < 50%

#### 4.3 ResourceMonitor
**File:** `Services/Health/ResourceMonitor.cs`

**Purpose:** Background service monitoring system resources

**Key Features:**
- ✅ CPU usage percentage
- ✅ Memory usage (MB and %)
- ✅ Disk free space
- ✅ Thread count
- ✅ 10-second sampling interval

**Metrics Push:**
```csharp
_healthService.UpdateResourceHealth(new ResourceHealth
{
    CpuUsagePercent = cpuUsage,
    MemoryUsageMB = memoryMB,
    MemoryUsagePercent = memoryPercent,
    DiskFreeMB = diskFreeMB,
    DiskUsagePercent = diskUsagePercent,
    ThreadCount = threadCount,
    HealthScore = CalculateScore(...)
});
```

#### 4.4 ArchiveMonitoringService
**File:** `Services/ArchiveMonitoringService.cs`

**Purpose:** Read-only monitoring of archive status (pushes metrics to health cache)

**Key Features:**
- ✅ File count monitoring
- ✅ Disk space tracking
- ✅ Archive age calculation
- ✅ Non-intrusive (read-only)

### Health Dashboard

**Web UI:** `http://localhost:5000` → Health Tab

**Auto-Refresh:** 3 seconds

**Displayed Metrics:**
- Overall system status (color-coded)
- OPC connection status
- Database writer throughput
- Spool queue depth
- Archive statistics
- System resources (CPU, RAM, Disk)
- Active alerts/warnings/errors

**API Endpoint:**
```http
GET /api/health
Response:
{
  "timestamp": "2025-12-15T14:30:00Z",
  "overallStatus": "Healthy",
  "overallHealthScore": 95.5,
  "opc": {
    "status": "Connected",
    "tagsConnected": 1250,
    "updateRateMs": 1000,
    "healthScore": 100
  },
  "dbWriter": {
    "status": "Running",
    "writeRatePerSecond": 1250,
    "batchQueueSize": 0,
    "healthScore": 100
  },
  ...
}
```

---

## Data Flow Architecture

### Real-Time Data Flow

```
OPC DA Server
    ↓ [OPC DA Protocol - COM]
OpcServerConnection (Polling 1000ms)
    ↓ [Timer Callback]
Read Tag Values (Async IOPCAsyncIO2)
    ↓ [OnReadComplete]
Update In-Memory Tag Dictionary
    ↓ [Raise Event]
TagValuesUpdated Event
    ↓ ↓ ↓ ↓ [4 Parallel Subscribers]
    ↓ ↓ ↓ ↓
    ↓ ↓ ↓ └─→ SignalR Hub → Web Clients (filtered by subscription)
    ↓ ↓ └───→ TagValuesPoolService → Shared Cache
    ↓ └─────→ DataLoggingService → Parquet Files (selected tags)
    └───────→ HistorianIngestHostedService → PostgreSQL (all mapped tags)
```

### Historical Data Flow

```
Parquet Files (D:\OpcLogs\Data\)
    ↓
┌───────────────────────────────────────┐
│  HistoricalTrends (Port 5001)         │
│  - Flask web viewer                   │
│  - Plotly.js charts                   │
│  - CSV/Excel export                   │
└───────────────────────────────────────┘

Parquet Files
    ↓
┌───────────────────────────────────────┐
│  BI Analytics Engine (Port 8000)      │
│  - Stateless calculations             │
│  - Multi-user sessions                │
│  - Advanced analytics                 │
└───────────────────────────────────────┘

Parquet Files
    ↓
┌───────────────────────────────────────┐
│  PostgresLogger Importer              │
│  - Hash-based idempotent import       │
│  - Tag catalog auto-discovery         │
└───────────────────────────────────────┘
    ↓
TimescaleDB (sensor_data)
    ↓
┌───────────────────────────────────────┐
│  PostgresLogger API (Port 6001)       │
│  - FastAPI trends service             │
│  - WebSocket live data                │
└───────────────────────────────────────┘
```

### Archive Flow

```
D:\OpcLogs\Data\ALL_SENSORS_*.parquet (10MB files)
    ↓ [LogBackupService - Hourly]
Check unarchived files (oldest first)
    ↓ [Consolidate until 200MB]
D:\OpcLogs\Data\temp_archive_*.parquet (temp file)
    ↓ [Atomic rename]
D:\OpcLogs\Backup\Archive_YYYYMMDD_HHMMSS.parquet
    ↓ [Delete source files]
Cleanup D:\OpcLogs\Data\ (source files removed)
    ↓ [Push metrics]
HealthStatusService.UpdateArchiverHealth(...)
```

---

## Configuration Management

### Primary Configuration: logging-config.json

**Location:** Application root directory

**Sections:**

```json
{
  "LoggingPaths": {
    "DataLogDirectory": "D:\\OpcLogs\\Data",
    "BackupDirectory": "D:\\OpcLogs\\Backup",
    "ArchiveLogsPath": "D:\\OpcLogs\\Backup\\Logs",
    "ApplicationLogDirectory": "Logs"
  },
  
  "Logging": {
    "Enabled": true,
    "IntervalSeconds": 5,
    "SelectedTags": [
      "GENERATOR_LOAD_MW",
      "TURBINE_SPEED",
      "STEAM_PRESSURE_BAR"
    ],
    "WalChannelCapacity": 512,
    "MaxWalSizeMB": 100
  },
  
  "ArchiveSettings": {
    "Enabled": true,
    "ArchiveIntervalMinutes": 60,
    "AutoCompressEnabled": false
  },
  
  "TrendViewerSettings": {
    "DefaultPointsPerTag": 500,
    "MaxPointsPerTag": 2000,
    "DefaultTrendCount": 20,
    "MaxTrendCount": 20,
    "ChartContainerMaxHeight": 8000,
    "ChartHeight": 350,
    "TableMaxRecords": 100
  },
  
  "Serilog": {
    "MinimumLevel": "Information",
    "OutputTemplate": "{Timestamp:yyyy-MM-dd HH:mm:ss.fff} [{Level}] {Message}{NewLine}{Exception}"
  }
}
```

### Historian Configuration: appsettings.json

**Section: Historian**

```json
{
  "Historian": {
    "Database": {
      "ConnectionString": "Host=localhost;Port=5432;Database=historian;Username=postgres;Password=yourpassword",
      "CommandTimeout": 30,
      "MaxPoolSize": 20
    },
    "Batch": {
      "MaxRows": 1000,
      "MaxBytes": 1048576,
      "MaxWaitMs": 5000
    },
    "Writer": {
      "ShardCount": 8,
      "RetryAttempts": 3,
      "RetryDelayMs": 1000
    },
    "Spool": {
      "Directory": "D:\\OpcLogs\\Spool",
      "MaxSizeMB": 1000,
      "ReplayBatchSize": 5000
    }
  }
}
```

### PostgresLogger Configuration: config/app_config.json

**Location:** `PostgresLogger/config/app_config.json`

```json
{
  "database": {
    "host": "localhost",
    "port": 5432,
    "database": "sensor_db",
    "user": "postgres",
    "password": "yourpassword"
  },
  "web_ui": {
    "host": "0.0.0.0",
    "port": 6001,
    "default_chart_points": 1000,
    "max_chart_points": 5000
  },
  "parquet_source": "D:\\OpcLogs\\Data",
  "import_settings": {
    "check_interval_seconds": 60,
    "batch_size": 1000,
    "concurrent_workers": 2,
    "file_format": "auto"
  },
  "tag_mappings": {
    "GENERATOR_LOAD_MW": {
      "plant": "PowerPlant1",
      "asset": "Generator",
      "subsystem": "Electrical",
      "unit": "MW"
    }
  }
}
```

---

## Deployment Guide

### Prerequisites

**Software Requirements:**
- Windows 10/11 or Windows Server 2016+
- .NET 8.0 Runtime (x86 for COM interop)
- PostgreSQL 15+ with TimescaleDB extension
- Python 3.8+ (for analytics module)
- OPC DA Server (local or remote via DCOM)

**Hardware Requirements:**
- CPU: 4+ cores recommended
- RAM: 8GB minimum, 16GB recommended
- Disk: SSD recommended for parquet/database storage
- Network: 1Gbps for remote OPC servers

### Installation Steps

#### Step 1: Build C# Application

```batch
cd D:\Development\OpcDaWebBrowser
build.bat
```

Output: `bin\Release\net8.0\win-x86\publish\OpcDaWebBrowser.exe`

#### Step 2: Install as Windows Service

```batch
install-service.bat
```

Service Details:
- Name: `CereveateOPCServer`
- Display Name: `Cereveate_Praxis OPC Server`
- Auto-start on system boot
- Auto-restart on failure (3 seconds delay)

#### Step 3: Configure PostgreSQL Historian Database

```batch
SETUP_HISTORIAN_DB.bat
```

Manual setup:
```sql
-- Connect to PostgreSQL
psql -U postgres

-- Create database
CREATE DATABASE historian;
\c historian

-- Enable TimescaleDB
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Run migration script
\i Services/HistorianIngest/DB/schema_migration.sql
```

#### Step 4: Add Tag Mappings

**Via Web UI:**
```
http://localhost:5000/historian/mapping.html
```

**Via SQL:**
```sql
INSERT INTO historian_meta.tag_master (tag_id, tag_name, data_type, enabled)
VALUES 
    ('GENERATOR_LOAD_MW', 'Generator Load', 'Double', true),
    ('TURBINE_SPEED', 'Turbine Speed', 'Double', true),
    ('STEAM_PRESSURE_BAR', 'Steam Pressure', 'Double', true)
ON CONFLICT (tag_id) DO UPDATE SET enabled = EXCLUDED.enabled;
```

#### Step 5: Setup Python Analytics Module

```batch
cd HistoricalTrends
pip install -r requirements.txt
start.bat
```

Access: `http://localhost:5001`

#### Step 6: (Optional) Setup PostgresLogger

```batch
cd PostgresLogger
setup.bat
START_ALL.bat
```

Access: `http://localhost:6001`

### Verification Checklist

✅ **OPC DA Web (Port 5000)**
- Navigate to `http://localhost:5000`
- Check "Server Browser" tab discovers local OPC servers
- Connect to an OPC server
- Verify "Health Monitor" tab shows green status
- Confirm "Tag Monitor" updates in real-time

✅ **Historian Database**
- Check logs: `Logs\app-YYYYMMDD.log`
- Verify: `MappingCacheService initialized with X tags`
- Verify: `Subscribed to OPC TagValuesUpdated events`
- Query database:
  ```sql
  SELECT COUNT(*) FROM historian_raw.historian_timeseries;
  ```

✅ **Parquet Files**
- Check directory: `D:\OpcLogs\Data\`
- Verify files exist: `ALL_SENSORS_*.parquet`
- Check file sizes (should rotate at 10MB)

✅ **Historical Trends**
- Navigate to `http://localhost:5001`
- Select date range
- Verify charts load
- Test CSV export

✅ **Health Monitoring**
- Navigate to `http://localhost:5000` → Health Tab
- Verify auto-refresh every 3 seconds
- Check all subsystems show green status
- Verify metric values update

### Troubleshooting

**Issue: No OPC servers discovered**
- Solution: Verify OPC DA servers installed and COM registered
- Check: `regedit` → `HKEY_CLASSES_ROOT` → search for server ProgID

**Issue: Remote OPC discovery fails (E_NOINTERFACE)**
- Solution: Verify COM casting pattern in `OpcDaService.cs` lines 94-104
- Check: DCOM configuration on remote host

**Issue: No data in historian database**
- Solution: Verify `historian_meta.tag_master` table has enabled mappings
- Check: Run `SELECT * FROM historian_meta.tag_master;`
- Fix: Insert mappings manually or via API

**Issue: SignalR updates not working**
- Solution: Verify hub subscription in `OpcDaHub.cs` line 47
- Check: Browser console for SignalR connection errors
- Verify: `/opcHub` endpoint mapped in `Program.cs`

**Issue: Parquet files empty**
- Solution: Verify `SelectedTags` array in `logging-config.json`
- Check: DataLoggingService logs for errors
- Verify: OPC server connected and tags readable

**Issue: High CPU usage**
- Solution: Reduce polling frequency in OPC connection
- Check: Number of monitored tags (reduce if >5000)
- Verify: SignalR throttling enabled (200ms minimum)

**Issue: Database connection errors**
- Solution: Verify PostgreSQL running and credentials correct
- Check: Connection string in `appsettings.json`
- Test: `psql -U postgres -d historian`

---

## Performance Characteristics

### OPC DA Module
- **Tag Capacity:** 10,000+ tags per connection
- **Polling Rate:** 1000ms default (configurable 100ms-10000ms)
- **SignalR Throughput:** 50+ concurrent clients
- **Network Optimization:** 95% reduction via client-side subscriptions

### Historian Database
- **Write Throughput:** 50,000+ rows/second (binary COPY)
- **Batch Size:** 1000 rows or 1MB or 5 seconds
- **Spool Failover:** Automatic disk spooling on DB outage
- **Compression:** TimescaleDB compression after 7 days (10:1 ratio)

### Parquet Logging
- **File Rotation:** 10MB per file (configurable)
- **Write Latency:** <50ms per batch
- **Storage Efficiency:** Snappy compression (~3:1 ratio)
- **Archive Consolidation:** 200MB per archive file

### Health Monitoring
- **Update Frequency:** 3-second web UI refresh
- **Read Latency:** <1ms (volatile fields)
- **Alert Calculation:** Real-time (no polling)
- **Resource Overhead:** <1% CPU, <100MB RAM

---

## Security Considerations

### Authentication
- ✅ Session-based authentication (24-hour timeout)
- ✅ Credential encryption service (AES-256)
- ✅ Hardware-locked licensing system

### Network Security
- ⚠️ CORS enabled (AllowAll) - restrict in production
- ⚠️ SignalR unauthenticated - add authentication for production
- ✅ HTTPS support available (configure in Program.cs)

### Database Security
- ✅ Connection string encryption recommended
- ✅ Npgsql connection pooling with timeouts
- ✅ PostgreSQL role-based access control

### File System Security
- ✅ Atomic file operations (temp file + rename)
- ✅ File locking prevents corruption
- ✅ Directory permissions required (write access)

---

## Maintenance & Operations

### Daily Tasks
- ✅ Monitor health dashboard (automated)
- ✅ Check disk space (D:\OpcLogs\ directory)
- ✅ Verify OPC connection status

### Weekly Tasks
- ✅ Review application logs (`Logs\app-*.log`)
- ✅ Check archive consolidation status
- ✅ Verify database backups

### Monthly Tasks
- ✅ Archive old parquet files to cold storage
- ✅ Analyze database size and compression
- ✅ Review and optimize tag mappings
- ✅ Update OPC server credentials if changed

### Log Locations
- **Application Logs:** `Logs\app-YYYYMMDD.log`
- **Archive Logs:** `D:\OpcLogs\Backup\Logs\archive_YYYYMMDD.log`
- **Historian Logs:** Included in application logs
- **PostgresLogger Logs:** `PostgresLogger\server.log`

---

## Support & Documentation

### Additional Documentation
- `README_WORKING_VERSION.md` - Verified working configuration
- `HEALTH_MONITORING_SYSTEM.md` - Detailed health system guide
- `HISTORIAN_SETUP_GUIDE.md` - Database historian setup
- `CONFIGURATION_GUIDE.md` - Complete configuration reference
- `API_DOCUMENTATION.md` - REST API reference
- `DEPLOYMENT_README.md` - Deployment package details

### Contact Information
- **Project:** Cereveate OPC DA / Analytics Platform
- **Repository:** opc-da-web-historian
- **Owner:** shahbpcl

---

**Document Version:** 2.0  
**Last Updated:** December 15, 2025  
**Status:** Production Ready ✅
