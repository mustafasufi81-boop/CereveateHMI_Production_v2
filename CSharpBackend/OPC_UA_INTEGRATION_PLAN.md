# OPC UA Integration Implementation Plan
**Date:** December 7, 2025  
**System:** 10,000 Tag OPC DA/UA Hybrid System  
**Critical:** ZERO performance degradation, smooth integration

---

## 1. CURRENT ARCHITECTURE ANALYSIS

### Data Flow Pipeline (Working - DO NOT BREAK)
```
┌─────────────────────┐
│  OPC DA Server      │ (COM/DCOM)
│  (RSLinx, Matrikon) │
└──────────┬──────────┘
           │ Timer Poll (1000ms)
           ↓
┌─────────────────────────────────┐
│ OpcServerConnection             │
│ - ReadTagValues()               │
│ - Stores in _tagValues dict     │
└──────────┬──────────────────────┘
           │ Every poll cycle
           ↓
┌─────────────────────────────────┐
│ OpcDaService                    │
│ - Aggregates multi-connections  │
│ - Raises TagValuesUpdated event │
└──────┬──────────────────────────┘
       │
       ├─────────────────┬────────────────────┐
       ↓                 ↓                    ↓
┌──────────────┐  ┌─────────────────┐  ┌──────────────────────────┐
│ SignalR Hub  │  │ DataLogging     │  │ HistorianIngest         │
│ (UI updates) │  │ Service         │  │ HostedService           │
│              │  │ (Parquet files) │  │ (PostgreSQL/TimescaleDB)│
└──────────────┘  └─────────────────┘  └──────────────────────────┘
                   Selected tags only   Rate Control → Batcher → DB
```

### Key Components That MUST Continue Working
1. **OpcDaService** - Multi-connection manager, raises `TagValuesUpdated` event
2. **OpcServerConnection** - Individual server connection, timer-based polling
3. **DataLoggingService** - Subscribes to `TagValuesUpdated`, writes parquet
4. **HistorianIngestHostedService** - Uses polling loop (NOT event-based), reads from `GetActiveConnection()`
5. **SignalR Hub** - Real-time UI updates via `TagValuesUpdated` event

### Performance Requirements
- **10,000 tags** simultaneous monitoring
- **1000ms polling interval** (minimum)
- **NO LAG** in UI updates
- **Historian rate control** (per-tag `db_logging_interval_ms`)
- **Parquet rotation** (10MB files)
- **PostgreSQL batch writes** (COPY BINARY, 1-10k rows)

---

## 2. OPC UA INTEGRATION STRATEGY

### Recommended Approach: **Unified Interface Pattern**

#### Step 1: Create Abstraction Layer
```csharp
public interface IOpcDataSource
{
    string ConnectionId { get; }
    string ServerName { get; }
    bool IsConnected { get; }
    DateTime ConnectedAt { get; }
    int MonitoredTagCount { get; }
    
    Task<bool> ConnectAsync(CancellationToken ct);
    Task DisconnectAsync();
    Task<List<string>> BrowseTagsAsync();
    Task<Dictionary<string, object>> ReadTagValuesAsync(List<string> tagIds);
    
    event EventHandler<TagValuesEventArgs> TagValuesUpdated;
}
```

#### Step 2: Implement OPC UA Client
```csharp
public class OpcUaDataSource : IOpcDataSource
{
    private readonly UaClient _client; // Opc.UaFx.Client
    private readonly Timer _pollTimer;
    private readonly ConcurrentDictionary<string, OpcTag> _tagValues;
    
    // Same polling pattern as OpcDaServerConnection
    // Raises TagValuesUpdated event every 1000ms
}
```

#### Step 3: Refactor OpcDaService → OpcDataService
```csharp
public class OpcDataService
{
    private readonly ConcurrentDictionary<string, IOpcDataSource> _dataSources;
    
    public event EventHandler<TagValuesEventArgs>? TagValuesUpdated;
    
    // Wire up events from both DA and UA sources
    private void OnSourceTagValuesUpdated(object? sender, TagValuesEventArgs e)
    {
        TagValuesUpdated?.Invoke(this, e);
    }
}
```

### Why This Works
✅ **Zero breaking changes** - All consumers see same `TagValuesUpdated` event  
✅ **Performance isolated** - Each data source has its own timer  
✅ **Resource efficient** - Unified event aggregation  
✅ **Backward compatible** - Existing OPC DA code unchanged  

---

## 3. DETAILED IMPLEMENTATION STEPS

### Phase 1: Add NuGet Package (5 min)
```xml
<PackageReference Include="Opc.UaFx.Client" Version="2.41.0" />
```
**Risk:** Low - just adds library  
**Test:** `dotnet build` succeeds

### Phase 2: Create Interface (10 min)
- File: `Services/IOpcDataSource.cs`
- Copy method signatures from `OpcServerConnection`
- Add async versions where needed

**Risk:** Low - no existing code modified  
**Test:** Compiles successfully

### Phase 3: Implement OpcUaDataSource (60 min)
- File: `Services/OpcUaDataSource.cs`
- Mirror `OpcServerConnection` structure
- Use `UaClient` from Opc.UaFx
- Implement timer-based polling (same 1000ms pattern)
- Connection: `opc.tcp://localhost:4850/rockwell/opc/bridge/`

**Risk:** Medium - new code, needs thorough testing  
**Test:** Connect to RockwellOpcBridge, read tags, verify event fires

### Phase 4: Refactor OpcDaService (30 min)
- Rename to `OpcDataService` (or keep name, add UA support)
- Change `_connections` to `_dataSources` (type `IOpcDataSource`)
- Add `ConnectToOpcUa(string endpoint)` method
- Keep all existing DA methods unchanged

**Risk:** Medium - touches core service  
**Test:** Verify existing OPC DA connections still work

### Phase 5: Update Dependency Injection (5 min)
- `Program.cs` - register `OpcUaDataSource` if needed
- No changes to consumers (they use `OpcDaService` singleton)

**Risk:** Low  
**Test:** App starts, DA connections work

### Phase 6: Add UI Discovery for UA Servers (20 min)
- Update `OpcServerDiscovery.cs` - add UA discovery
- New method: `DiscoverOpcUaServers()` - hardcoded for now
- Returns: `opc.tcp://localhost:4850/rockwell/opc/bridge/`

**Risk:** Low  
**Test:** UI shows both DA and UA servers

### Phase 7: Update SignalR Hub (10 min)
- Add `ConnectToOpcUaServer(string endpoint)` method
- Calls `OpcDataService.ConnectToOpcUa(endpoint)`

**Risk:** Low  
**Test:** Connect from UI, verify tag values flow

---

## 4. PERFORMANCE SAFEGUARDS

### Memory Management
- Each data source: max 10,000 tags × 100 bytes = 1 MB
- Total for DA + UA: ~2 MB (acceptable)

### Threading
- OPC DA: Uses COM STA thread + Timer
- OPC UA: Uses async/await + Timer
- No thread conflicts (different sources, same event pattern)

### Event Aggregation
```csharp
// Current: 1 event per OPC DA connection every 1000ms
// After: 1 event per data source (DA or UA) every 1000ms
// Downstream consumers: NO CHANGE (they don't care about source)
```

### Rate Control (Historian)
- `HistorianIngestHostedService` already has per-tag rate control
- Works regardless of data source (DA or UA)

---

## 5. TESTING STRATEGY

### Unit Tests
1. `OpcUaDataSource` connects to RockwellOpcBridge
2. Browse tags returns expected list
3. Read tags returns values
4. Timer fires `TagValuesUpdated` event every 1000ms
5. Disconnect cleans up resources

### Integration Tests
1. Connect to both OPC DA (Matrikon) + OPC UA (Rockwell) simultaneously
2. Verify SignalR Hub receives updates from BOTH
3. Verify DataLoggingService logs tags from BOTH
4. Verify HistorianIngest writes to DB from BOTH
5. Monitor memory/CPU with 10,000 tags total

### Rollback Plan
- Keep `OpcDaService` original code in git branch
- If issues: disable UA connections, revert to DA-only
- Zero data loss (spool manager handles failures)

---

## 6. CONFIGURATION

### appsettings.json Extension
```json
{
  "OpcUa": {
    "Servers": [
      {
        "Name": "RockwellBridge",
        "Endpoint": "opc.tcp://localhost:4850/rockwell/opc/bridge/",
        "SecurityPolicy": "None",
        "AutoConnect": true
      }
    ],
    "PollingIntervalMs": 1000,
    "ConnectionTimeout": 30000
  }
}
```

---

## 7. ESTIMATED TIMELINE

| Phase | Time | Risk | Blocker |
|-------|------|------|---------|
| 1. Add NuGet | 5 min | Low | None |
| 2. Interface | 10 min | Low | None |
| 3. OpcUaDataSource | 60 min | Medium | UA server must be running |
| 4. Refactor Service | 30 min | Medium | Regression testing |
| 5. DI Update | 5 min | Low | None |
| 6. UI Discovery | 20 min | Low | None |
| 7. Hub Update | 10 min | Low | None |
| **Testing** | 60 min | High | Must verify 10K tags |
| **TOTAL** | **3.5 hours** | | |

---

## 8. GO/NO-GO CHECKLIST

### Prerequisites (MUST HAVE before starting)
- [ ] RockwellOpcBridge running on `opc.tcp://localhost:4850`
- [ ] Tags available via UA (verify with UA client tool)
- [ ] Git branch created for rollback
- [ ] Backup of current working DB historian data
- [ ] OPC DA connection still works (Matrikon test)

### After Implementation (MUST PASS)
- [ ] OPC DA discovery still works
- [ ] OPC DA connections still work
- [ ] SignalR UI updates still real-time (<1s delay)
- [ ] Parquet files still rotate correctly
- [ ] Historian DB writes continue (check `historian_raw.historian_timeseries`)
- [ ] No memory leaks (Task Manager: <500 MB for app)
- [ ] No CPU spikes (Task Manager: <30% sustained)
- [ ] 10,000 tags: all values update every 1000ms

---

## 9. RISKS & MITIGATIONS

| Risk | Impact | Mitigation |
|------|--------|------------|
| OPC UA client slower than DA | High | Use same timer pattern, monitor latency |
| Memory leak with 10K tags | Critical | Implement `IDisposable`, use `using` statements |
| Event storm (2× sources) | Medium | Debounce in hub (existing 1000ms throttle) |
| UA certificate validation fails | Medium | Disable for localhost, document for production |
| Historian writes duplicate data | Critical | Tag source in `sample_source` column (already exists) |

---

## 10. FINAL DECISION POINT

**PROCEED IF:**
✅ All prerequisites checked  
✅ Team reviewed this plan  
✅ Rollback tested  
✅ Performance baseline captured (current memory/CPU)  

**STOP IF:**
❌ Any breaking change to existing OPC DA flow required  
❌ Performance degradation in testing  
❌ Historian DB writes fail  

---

**Next Step:** Review this plan, then proceed with Phase 1 (Add NuGet Package)
