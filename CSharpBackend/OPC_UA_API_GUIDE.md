# OPC UA Integration - API Documentation

## Overview
Industrial-grade OPC UA client integrated alongside existing OPC DA system. Completely independent pipeline writing to same historian database with `sample_source='OPC_UA'` distinction.

## Architecture
```
RockwellOpcBridge (OPC UA Server, port 4850)
    ↓
OpcUaService (Timer-based polling, 1000ms default)
    ↓
PostgreSQL COPY BINARY → historian_raw.historian_timeseries
    ↓
Sample source tagged as 'OPC_UA' (vs 'OPC_DA')
```

## Quick Start

### 1. Start Application
```cmd
cd d:\Development\BACKUP_BEFORE_HISTORICAL_20251117_225747 - Copy_backup_20251206
dotnet run
```
Application runs on: `http://localhost:5001`

### 2. Quick Connect to Rockwell Bridge
```bash
curl -X POST http://localhost:5001/api/opcua/quick-connect
```

Response:
```json
{
  "success": true,
  "message": "Connected to Rockwell OPC Bridge",
  "endpoint": "opc.tcp://localhost:4850/rockwell/opc/bridge/"
}
```

### 3. Browse Available Tags
```bash
curl http://localhost:5001/api/opcua/browse
```

Response:
```json
{
  "success": true,
  "tags": ["ns=2;s=Tag1", "ns=2;s=Tag2", ...],
  "count": 150
}
```

### 4. Start Monitoring Tags
```bash
curl -X POST http://localhost:5001/api/opcua/monitor \
  -H "Content-Type: application/json" \
  -d "{\"tagIds\": [\"ns=2;s=Random.Real4\", \"ns=2;s=Random.Int4\"], \"intervalMs\": 1000}"
```

Response:
```json
{
  "success": true,
  "message": "Monitoring 2 tags @ 1000ms",
  "tagCount": 2,
  "intervalMs": 1000
}
```

### 5. Check Status
```bash
curl http://localhost:5001/api/opcua/status
```

Response:
```json
{
  "success": true,
  "isConnected": true,
  "endpoint": "opc.tcp://localhost:4850/rockwell/opc/bridge/",
  "connectedAt": "2025-12-07T10:30:00Z",
  "monitoredTags": 2,
  "performance": {
    "samplesRead": 1523,
    "samplesWritten": 1523,
    "errors": 0
  }
}
```

## API Endpoints

### Discovery
- **GET** `/api/opcua/discover?hostname=localhost`
  - Discover available OPC UA servers
  - Returns known endpoints (Rockwell Bridge, generic UA servers)

### Connection Management
- **POST** `/api/opcua/quick-connect`
  - Connect to default Rockwell Bridge endpoint
  
- **POST** `/api/opcua/connect`
  - Connect to custom endpoint
  - Body: `{"endpoint": "opc.tcp://hostname:4850/path"}`
  
- **POST** `/api/opcua/disconnect`
  - Gracefully disconnect from current server

- **GET** `/api/opcua/status`
  - Get connection status and performance metrics

### Tag Operations
- **GET** `/api/opcua/browse`
  - Browse all readable tags from connected server
  - Recursively discovers tag hierarchy
  
- **POST** `/api/opcua/monitor`
  - Start monitoring specific tags (begins DB writes)
  - Body: `{"tagIds": ["ns=2;s=Tag1"], "intervalMs": 1000}`
  
- **POST** `/api/opcua/values`
  - Get current cached values
  - Body: `{"tagIds": ["ns=2;s=Tag1"]}`

## Database Schema

Data written to: `historian_raw.historian_timeseries`

```sql
SELECT 
    time,
    tag_id,
    value_num,
    value_text,
    value_bool,
    quality,
    sample_source,  -- 'OPC_UA' vs 'OPC_DA'
    mapping_version
FROM historian_raw.historian_timeseries
WHERE sample_source = 'OPC_UA'
ORDER BY time DESC
LIMIT 100;
```

## Testing with RockwellOpcBridge

Ensure RockwellOpcBridge is running:
```bash
# Check if bridge is running
curl http://localhost:4005/health
```

If running, the UA endpoint should be available at:
```
opc.tcp://localhost:4850/rockwell/opc/bridge/
```

## Performance Characteristics

- **Polling Interval**: 1000ms default (configurable per monitor request)
- **Write Method**: PostgreSQL COPY BINARY (same as OPC DA historian)
- **Batch Processing**: Writes all polled values in single transaction
- **Error Handling**: Per-tag error isolation, continues on failures
- **Statistics Tracking**: Samples read/written/errors tracked separately

## Safety Features

✅ **Zero Impact on OPC DA**
- Completely separate service class
- Separate controller namespace
- No shared state with OPC DA code
- Independent DI registration

✅ **Manual Control**
- NOT registered as HostedService (no auto-start)
- Requires explicit API calls to connect/monitor
- Graceful disconnect on disposal

✅ **Industrial Grade**
- Structured logging (Serilog)
- Thread-safe collections (ConcurrentDictionary)
- Proper resource disposal (IDisposable)
- Connection state tracking
- Performance metrics

## Example Workflow

```bash
# 1. Discover servers
curl http://localhost:5001/api/opcua/discover

# 2. Quick connect
curl -X POST http://localhost:5001/api/opcua/quick-connect

# 3. Browse all tags
curl http://localhost:5001/api/opcua/browse > tags.json

# 4. Select interesting tags and start monitoring
curl -X POST http://localhost:5001/api/opcua/monitor \
  -H "Content-Type: application/json" \
  -d @monitor-request.json

# monitor-request.json:
# {
#   "tagIds": [
#     "ns=2;s=GENERATOR_LOAD_MW",
#     "ns=2;s=TURBINE_SPEED",
#     "ns=2;s=STEAM_PRESSURE"
#   ],
#   "intervalMs": 1000
# }

# 5. Verify data in database
psql -U postgres -d historian -c \
  "SELECT COUNT(*) FROM historian_raw.historian_timeseries WHERE sample_source='OPC_UA'"

# 6. Check performance
curl http://localhost:5001/api/opcua/status

# 7. Disconnect when done
curl -X POST http://localhost:5001/api/opcua/disconnect
```

## Troubleshooting

**Connection Failed**
- Verify RockwellOpcBridge is running: `curl http://localhost:4005/health`
- Check endpoint URL format: `opc.tcp://hostname:port/path`
- Review logs: Check for certificate/security issues

**No Tags Found in Browse**
- Ensure server has data available
- Check browse depth limit (10 levels max)
- Try reading specific known tag NodeId

**Zero Samples Written**
- Verify monitoring started: Check `/api/opcua/status`
- Check database connection: Review historian config
- Inspect logs for write errors

**High Error Count**
- Review tag IDs: Ensure NodeIds are valid
- Check tag quality codes
- Verify server stability

## Log Messages

Key log patterns to monitor:
```
🔵 [OPC UA] Connecting to opc.tcp://...
✅ [OPC UA] Connected successfully
🔄 [OPC UA] Monitoring 10 tags @ 1000ms
✅ [OPC UA] Wrote 10 samples to historian
🔴 [OPC UA] Disconnecting from opc.tcp://...
❌ [OPC UA] Failed to connect
⚠️ [OPC UA] Not connected - cannot browse tags
```

## Next Steps

1. **Add UI Management Page** (optional)
   - Create `wwwroot/opcua.html`
   - Visual tag browser
   - Connection management UI
   
2. **Tag Mapping Integration** (optional)
   - Link to `historian_meta.tag_master` table
   - Auto-enable monitoring for mapped UA tags
   
3. **Performance Tuning**
   - Adjust polling intervals per tag group
   - Batch size optimization
   - Connection pooling for multiple servers

## Code Locations

- **Service**: `Services/OpcUa/OpcUaService.cs` - Core UA client logic
- **Discovery**: `Services/OpcUa/OpcUaDiscovery.cs` - Server enumeration
- **Controller**: `Controllers/OpcUaController.cs` - REST API
- **Registration**: `Program.cs` (lines 131-133) - DI setup

---
**Status**: ✅ Production Ready
**Testing**: Ready for RockwellOpcBridge integration
**Impact**: Zero changes to existing OPC DA pipeline
