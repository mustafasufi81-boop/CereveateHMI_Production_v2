# Remote OPC Server Historian Integration Analysis

## 🎯 Executive Summary

**CONCLUSION**: The historian system **AUTOMATICALLY WORKS** with both local and remote OPC servers without any code changes needed. The architecture is already designed to handle remote connections transparently.

---

## 🏗️ Architecture Overview

### Multi-Server Connection Manager (`OpcDaService`)

```
OpcDaService (Singleton)
    ├── ConcurrentDictionary<ConnectionId, OpcServerConnection>
    │   ├── Local Server:  "Matrikon.OPC.Simulation.1"
    │   ├── Remote Server: "MCS.OPCServer.1@192.168.1.100"
    │   └── Remote Server: "Kepware.KEPServerEX.V6@SCADA-PC"
    │
    └── GetActiveConnection() → Returns FIRST connected server
                                (used by historian)
```

### Key Design Pattern

```csharp
// ConnectionId Format:
// - Local:  "{ServerProgID}"
// - Remote: "{ServerProgID}@{Host}"

// Examples:
// Local:  "Matrikon.OPC.Simulation.1"
// Remote: "MCS.OPCServer.1@192.168.1.100"
// Remote: "Kepware.KEPServerEX.V6@SCADA-SERVER"
```

---

## 🔌 Remote OPC Connection Mechanism

### Connection Creation (`OpcServerConnection.cs` Lines 80-130)

```csharp
// STEP 1: Server Type Resolution
Type? serverType = null;

if (!string.IsNullOrWhiteSpace(ServerCLSID))
{
    // Recommended for Windows XP compatibility
    Guid clsidGuid = Guid.Parse(ServerCLSID);
    serverType = IsLocal
        ? Type.GetTypeFromCLSID(clsidGuid)
        : Type.GetTypeFromCLSID(clsidGuid, Host);  // ← DCOM CALL
}
else
{
    // Standard ProgID resolution
    serverType = IsLocal
        ? Type.GetTypeFromProgID(ServerProgID)
        : Type.GetTypeFromProgID(ServerProgID, Host);  // ← DCOM CALL
}

// STEP 2: COM Activation (DCOM if remote)
_opcServer = (IOPCServer)Activator.CreateInstance(serverType)!;
```

### Remote Connection Properties

| Property | Local Example | Remote Example |
|----------|---------------|----------------|
| `ServerProgID` | `"MCS.OPCServer.1"` | `"MCS.OPCServer.1"` |
| `Host` | `""` (empty) | `"192.168.1.100"` or `"SCADA-PC"` |
| `ServerCLSID` | `"{...GUID...}"` | `"{...GUID...}"` (recommended for XP) |
| `IsLocal` | `true` | `false` |
| `ConnectionId` | `"MCS.OPCServer.1"` | `"MCS.OPCServer.1@192.168.1.100"` |

---

## 📊 Historian Integration Flow

### How Historian Reads Data (Remote or Local - Same Code Path)

```
1. HistorianIngestHostedService.StartHistorianOpcPollingAsync()
   └─> var activeConnection = _opcService.GetActiveConnection();
       └─> Returns FIRST IsConnected server (local OR remote)

2. PrecisePollingLoopAsync()
   └─> activeConnection.ReadTagValues()  ← WORKS FOR BOTH
       └─> Polls OPC groups via COM/DCOM
       └─> Returns List<TagValue> with timestamps

3. ProcessTagValueAsync(tagValue, "OPC_Historian", pollTimestamp)
   └─> Creates RawSample with:
       ├─ Time = pollTimestamp (respects DbLoggingIntervalMs)
       └─ OpcTimestamp = tagValue.Timestamp (OPC server time)

4. Database Write (DbWriterService)
   └─> COPY historian_raw.historian_timeseries
       ├─ time = poll timestamp (controlled intervals)
       └─ opc_timestamp = original OPC server timestamp
```

### Critical Code Path (Lines 464-490 in HistorianIngestHostedService.cs)

```csharp
// INDUSTRY STANDARD: Capture ONE poll timestamp for entire batch
var pollTimestamp = DateTimeOffset.UtcNow;

// Read all tag values from active connection
// ⚠️ THIS WORKS FOR BOTH LOCAL AND REMOTE SERVERS
var allTagValues = activeConnection.ReadTagValues();

// Filter to only tags in our enabled mappings (by TagId)
var mappedTagIds = new HashSet<string>(enabledMappings.Select(m => m.TagId));
var relevantTagValues = allTagValues.Where(tv => mappedTagIds.Contains(tv.ItemID)).ToList();

// SAME CODE PATH FOR LOCAL AND REMOTE
foreach (var tagValue in relevantTagValues)
{
    await ProcessTagValueAsync(tagValue, "OPC_Historian", pollTimestamp);
}
```

---

## 🌐 Remote OPC Server Discovery

### Discovery Flow (`OpcDaService.cs` Lines 85-160)

```csharp
public List<RemoteServerInfo> DiscoverRemoteServers(string host)
{
    // Method 1: OPCEnum (OPC Foundation standard)
    Type? enumType = Type.GetTypeFromProgID("OPC.ServerList.1", host);
    IOPCServerList2? serverList = (IOPCServerList2)Activator.CreateInstance(enumType);
    
    // Enumerate OPC DA 2.0/3.0 servers
    Guid catid = new Guid("63D5F432-CFE4-11d1-B2C8-0060083BA1FB");
    serverList.EnumClassesOfCategories(1, new[] { catid }, 0, null, out IEnumGUID? enumGuid);
    
    // Method 2: Query CLSIDs for server details
    IOPCServer tempServer = (IOPCServer)Activator.CreateInstance(serverType);
    tempServer.GetStatus(out OPCSERVERSTATUS status);
    
    // Returns: ProgID, CLSID, Description, Version
}
```

### Discovery vs Connection

| Discovery | Connection |
|-----------|------------|
| **Purpose**: List available servers | **Purpose**: Establish active session |
| **Method**: OPCEnum (OPC.ServerList.1) | **Method**: Direct COM activation |
| **Result**: Server metadata (ProgID, CLSID) | **Result**: IOPCServer interface |
| **DCOM**: Required if remote | **DCOM**: Required if remote |

---

## 🔒 DCOM Security Requirements

### Required Configuration (Remote OPC Only)

**On OPC Server Machine (192.168.1.100):**

1. **DCOM Permissions**
   - Run `dcomcnfg.exe`
   - Component Services → Computers → My Computer → DCOM Config
   - Find OPC server (e.g., "MCS.OPCServer.1")
   - Properties → Security tab:
     - Launch and Activation: Allow remote launch/activation
     - Access Permissions: Allow remote access
     - Add client machine user account

2. **Windows Firewall**
   - Allow TCP 135 (DCOM endpoint mapper)
   - Allow dynamic RPC ports (1024-65535) OR restrict range
   - Configure via: `netsh advfirewall firewall add rule...`

3. **OPC Server Service**
   - Must run under account with network access
   - Not recommended: Local System (no network identity)
   - Recommended: Domain account or local account (mirrored on both machines)

**On Client Machine (Running Historian):**

1. **Network Credentials**
   - User account must exist on both machines (same username/password)
   - OR use domain authentication

2. **COM Security**
   - May need to lower UAC restrictions
   - Configure DCOM default permissions

### Error Codes Reference

| Error Code | Meaning | Solution |
|------------|---------|----------|
| `0x80070005` | Access Denied | Fix DCOM permissions, check user account |
| `0x800706BA` | RPC Server Unavailable | Check firewall, verify network connectivity |
| `0x80080005` | Server Execution Failed | OPC server not running or cannot start |
| `0x800401F0` | Class Not Registered | OPC server not installed on remote machine |

---

## ✅ Verification: Remote Connection Works with Historian

### Test Scenario 1: Local MCS OPC Server

```csharp
// Connection
OpcDaService.AddServerConnection("MCS.OPCServer.1", "", "");
OpcDaService.ConnectServer("MCS.OPCServer.1");

// Historian reads from
var activeConnection = _opcService.GetActiveConnection();
// Returns: Local connection
// ConnectionId: "MCS.OPCServer.1"
// IsLocal: true
```

### Test Scenario 2: Remote MCS OPC Server

```csharp
// Connection
OpcDaService.AddServerConnection("MCS.OPCServer.1", "192.168.1.100", "{...CLSID...}");
OpcDaService.ConnectServer("MCS.OPCServer.1@192.168.1.100");

// Historian reads from
var activeConnection = _opcService.GetActiveConnection();
// Returns: Remote connection
// ConnectionId: "MCS.OPCServer.1@192.168.1.100"
// IsLocal: false
// Host: "192.168.1.100"

// ✅ SAME ReadTagValues() METHOD - TRANSPARENT TO HISTORIAN
```

### Test Scenario 3: Multiple Servers (Local + Remote)

```csharp
// Connection 1: Local
OpcDaService.AddServerConnection("Matrikon.OPC.Simulation.1", "", "");
OpcDaService.ConnectServer("Matrikon.OPC.Simulation.1");

// Connection 2: Remote MCS
OpcDaService.AddServerConnection("MCS.OPCServer.1", "192.168.1.100", "");
OpcDaService.ConnectServer("MCS.OPCServer.1@192.168.1.100");

// Historian reads from
var activeConnection = _opcService.GetActiveConnection();
// Returns: FIRST connected server (Matrikon local)

// To switch to remote MCS:
// 1. Disconnect Matrikon
// 2. GetActiveConnection() will return MCS remote
```

---

## 📝 Database Schema (Same for Local & Remote)

### historian_raw.historian_timeseries

```sql
CREATE TABLE historian_raw.historian_timeseries (
    time            timestamptz NOT NULL,  -- Poll timestamp (controlled intervals)
    tag_id          text NOT NULL,         -- Tag ID from OPC (local or remote)
    value_num       double precision,      -- Numeric value
    value_text      text,                  -- Text value
    value_bool      boolean,               -- Boolean value
    quality         text NOT NULL,         -- G/B/U quality code
    sample_source   text NOT NULL,         -- "OPC_Historian"
    mapping_version bigint NOT NULL,       -- Tag mapping version
    opc_timestamp   timestamptz,           -- Original OPC server timestamp ← NEW
    PRIMARY KEY (tag_id, time)
);
```

### Data Flow Example (Remote MCS Server)

```
Remote OPC Server (192.168.1.100)
    ├─ Tag: "Plant1.Reactor.Temperature"
    ├─ Value: 245.8
    └─ OPC Timestamp: 2024-12-04 22:25:32.894 (server time)
            ↓
    DCOM Call (ReadTagValues)
            ↓
    Local Historian (Your Machine)
    ├─ Poll Timestamp: 2024-12-04 22:25:33.000 (local time, 1s intervals)
    └─ OPC Timestamp: 2024-12-04 22:25:32.894 (preserved from server)
            ↓
    PostgreSQL Database
    ├─ time: 2024-12-04 22:25:33.000+05:30 (poll timestamp)
    ├─ tag_id: "Plant1.Reactor.Temperature"
    ├─ value_num: 245.8
    ├─ quality: "G"
    ├─ sample_source: "OPC_Historian"
    └─ opc_timestamp: 2024-12-04 22:25:32.894+05:30 (original OPC time)
```

---

## 🔧 Configuration for Remote MCS Server

### Step 1: Connect via Web UI

**Endpoint**: `/api/opc/connect` (POST)

```json
{
    "serverProgID": "MCS.OPCServer.1",
    "host": "192.168.1.100",
    "clsid": "{YOUR-MCS-CLSID-HERE}"  // Optional but recommended for XP
}
```

### Step 2: Verify Connection

**Endpoint**: `/api/opc/connections` (GET)

```json
[
    {
        "connectionId": "MCS.OPCServer.1@192.168.1.100",
        "serverProgID": "MCS.OPCServer.1",
        "host": "192.168.1.100",
        "isLocal": false,
        "isConnected": true,
        "status": "Connected",
        "connectedAt": "2024-12-04T22:20:00",
        "monitoredTagCount": 150
    }
]
```

### Step 3: Browse Remote Tags

**Endpoint**: `/api/opc/browse-tags?connectionId=MCS.OPCServer.1@192.168.1.100` (GET)

Returns all available tags from remote MCS server.

### Step 4: Map Tags to Historian

**SQL Insert** (same as local):

```sql
INSERT INTO historian_meta.tag_master 
(tag_id, tag_name, data_type, enabled, created_by)
VALUES 
('Plant1.Reactor.Temperature', 'Reactor Temperature', 'Double', true, 'admin'),
('Plant1.Reactor.Pressure', 'Reactor Pressure', 'Double', true, 'admin')
ON CONFLICT (tag_id) DO UPDATE SET enabled = true;
```

### Step 5: Historian Auto-Starts Logging

```
HistorianIngestHostedService
    ├─ Detects enabled mappings in tag_master
    ├─ Calls GetActiveConnection() → Returns remote MCS connection
    ├─ Starts polling at DbLoggingIntervalMs (1000ms)
    └─ Writes to database with poll timestamp + OPC timestamp
```

---

## ⚡ Performance Considerations

### Network Latency Impact

| Network | DCOM Latency | Poll Impact | Recommendation |
|---------|--------------|-------------|----------------|
| LAN (Gigabit) | 1-5ms | Negligible | 1000ms interval OK |
| LAN (100Mbps) | 5-20ms | Minor | 1000ms interval OK |
| WAN/VPN | 50-200ms | Moderate | Consider 2000ms+ interval |
| Internet | 100-500ms+ | Significant | Not recommended |

### DCOM vs OPC UA

| Protocol | Remote Support | Firewall Friendly | Security | Performance |
|----------|----------------|-------------------|----------|-------------|
| **DCOM (OPC DA)** | ✅ Yes (complex) | ❌ Multiple ports | ⚠️ Windows auth | ⚡ Good on LAN |
| **OPC UA** | ✅ Yes (simple) | ✅ Single TCP port | ✅ Certificates | ⚡ Better over WAN |

**Note**: Current system uses OPC DA (DCOM). If MCS server supports OPC UA, consider migrating for better remote performance.

---

## 🎓 Key Takeaways

### ✅ What Works Automatically

1. **Historian logging from remote OPC servers** - No code changes needed
2. **Multi-server support** - Can connect to multiple servers (local + remote)
3. **Tag browsing** - Works same as local via DCOM
4. **Timestamp preservation** - Both poll timestamp and OPC timestamp stored
5. **Rate control** - DbLoggingIntervalMs respected regardless of server location

### ⚠️ What Requires Configuration

1. **DCOM permissions** - Windows security (server machine)
2. **Firewall rules** - TCP 135 + RPC ports (both machines)
3. **Network credentials** - User account setup (both machines)
4. **Tag mappings** - Insert into `historian_meta.tag_master` (same as local)

### 🚀 Deployment Checklist for Remote MCS Server

- [ ] Verify MCS OPC server installed on 192.168.1.100
- [ ] Configure DCOM permissions for MCS.OPCServer.1
- [ ] Open firewall ports (TCP 135, RPC dynamic range)
- [ ] Test connectivity: `ping 192.168.1.100`
- [ ] Discover remote server: `/api/opc/discover-remote?host=192.168.1.100`
- [ ] Connect: POST `/api/opc/connect` with ProgID + Host + CLSID
- [ ] Browse tags: GET `/api/opc/browse-tags?connectionId=...`
- [ ] Map tags: INSERT into `historian_meta.tag_master`
- [ ] Verify historian polling: Check logs for "🔄 Polling: Read X tag(s)"
- [ ] Query database: `SELECT * FROM historian_raw.historian_timeseries ORDER BY time DESC LIMIT 10;`

---

## 📞 Support Information

**System Architecture**: Multi-server OPC DA with industry-standard historian pattern
**Remote Protocol**: DCOM (OPC DA 2.0/3.0 specification)
**Historian Mode**: Polling-only (respects DbLoggingIntervalMs)
**Database**: PostgreSQL 15 + TimescaleDB (hypertable partitioned by timestamp)

**For remote OPC issues, check**:
1. Windows Event Viewer (DCOM errors)
2. Application logs: `bin/Logs/historian-{date}.log`
3. Network connectivity: `telnet 192.168.1.100 135`
4. DCOM test: Use `OpcEnum.exe` or similar diagnostic tool
