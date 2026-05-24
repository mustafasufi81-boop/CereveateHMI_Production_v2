# PLC Gateway Configuration Guide

## Overview

The PLC Gateway reads Rockwell ControlLogix PLC data and exposes it via:
- **REST API**: `http://localhost:5001/api/plc/values`
- **MQTT**: `localhost:1883`, topic `plc/plc/all`
- **TCP Broadcast**: Port 5050 (optional)

---

## ⚠️ IMPORTANT: What Config Is Actually Used

### Currently USED from appsettings.json:
| Section | Used By | Purpose |
|---------|---------|---------|
| `ConnectionStrings.PlcGateway` | ✅ PlcConfigLoaderService | Database connection to read tag_master |
| `PlcGateway.Mqtt` | ✅ MultiProtocolPublisherService | MQTT broker settings |
| `PlcGateway.LocalBroadcast` | ✅ MultiProtocolPublisherService | TCP broadcast settings |
| `PlcGateway.Transport` | ✅ MultiProtocolPublisherService | General transport settings |

### ❌ NOT USED from appsettings.json:
| Section | Status | Reason |
|---------|--------|--------|
| `PlcGateway.Connections` | ❌ **NOT READ** | PLC connection details come from DATABASE only |
| `PlcGateway.Connections[].IpAddress` | ❌ Ignored | Read from `tag_master.plc_ip_address` |
| `PlcGateway.Connections[].Port` | ❌ Ignored | Read from `tag_master.plc_port` |
| `PlcGateway.Connections[].RockwellConfig` | ❌ Ignored | Read from `tag_master.plc_type`, `plc_path` |

### Where PLC Connection Config ACTUALLY Comes From:
```
┌─────────────────────────────────────────────────────────────────────┐
│  appsettings.json                                                   │
│  "PlcGateway": {                                                    │
│    "Connections": [ ... ]  ← ❌ NOT USED! Just for reference        │
│    "Mqtt": { ... }         ← ✅ USED for MQTT broker settings       │
│  }                                                                  │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│  PostgreSQL: historian_meta.tag_master                              │
│                                                                      │
│  server_progid = 'Rockwel_PLC_001'    ← ✅ PLC ID                   │
│  plc_ip_address = '192.168.0.20'      ← ✅ PLC IP Address           │
│  plc_port = 44818                      ← ✅ PLC Port                │
│  plc_type = 'ControlLogix'             ← ✅ PLC Type                │
│  plc_path = '1,0'                      ← ✅ Slot Path               │
│  use_connected_messaging = true        ← ✅ Connection Mode         │
│  tag_id = 'Pump_RPM'                   ← ✅ Tag Address             │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Configuration Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                    CONFIGURATION SOURCES                            │
├────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────────────┐      ┌───────────────────────────────┐   │
│  │   appsettings.json   │      │  PostgreSQL Database          │   │
│  │                      │      │  historian_meta.tag_master    │   │
│  │  • Database Conn ✅  │      │                               │   │
│  │  • MQTT Settings ✅  │      │  • PLC Connection Details ✅  │   │
│  │  • Transport ✅      │      │  • Tag Definitions ✅         │   │
│  │  • Connections ❌    │      │  • Deadband/Logging Config ✅ │   │
│  │    (NOT USED)        │      │                               │   │
│  └──────────┬───────────┘      └───────────────┬───────────────┘   │
│             │                                   │                    │
│             └───────────┬───────────────────────┘                   │
│                         │                                            │
│                         ▼                                            │
│              ┌─────────────────────────┐                            │
│              │  PlcConfigLoaderService │                            │
│              │                         │                            │
│              │  Reads DB → Builds      │                            │
│              │  PlcConfigEntry objects │                            │
│              └───────────┬─────────────┘                            │
│                          │                                           │
│                          ▼                                           │
│              ┌─────────────────────────┐                            │
│              │    PlcGatewayService    │                            │
│              │                         │                            │
│              │  Connects to PLC        │                            │
│              │  Polls tags @ 1000ms    │                            │
│              └───────────┬─────────────┘                            │
│                          │                                           │
│         ┌────────────────┼────────────────┐                         │
│         │                │                │                          │
│         ▼                ▼                ▼                          │
│    ┌─────────┐     ┌──────────┐    ┌────────────┐                   │
│    │REST API │     │   MQTT   │    │TCP Broadcast│                  │
│    │:5001    │     │  :1883   │    │   :5050    │                   │
│    └─────────┘     └──────────┘    └────────────┘                   │
│                                                                      │
└────────────────────────────────────────────────────────────────────┘
```

---

## 1. Database Connection String (appsettings.json)

The database connection is defined in `appsettings.json`:

```json
{
  "ConnectionStrings": {
    "PlcGateway": "Host=localhost;Port=5432;Database=Cereveate;Username=cereveate;Password=cereveate@222"
  }
}
```

**PlcConfigLoaderService reads this connection string:**
```csharp
_connectionString = configuration.GetConnectionString("PlcGateway") 
    ?? configuration.GetConnectionString("Historian");
```

---

## 2. PLC Connection Details (historian_meta.tag_master)

The `PlcConfigLoaderService` queries the database to discover PLCs:

```sql
SELECT DISTINCT 
    server_progid,           -- PLC ID (e.g., 'Rockwel_PLC_001')
    plc_protocol,            -- 'Rockwell', 'SiemensS7', 'ModbusTcp'
    plc_ip_address,          -- '192.168.0.20'
    plc_port,                -- 44818
    plc_type,                -- 'ControlLogix'
    plc_path,                -- '1,0'
    plc_timeout_ms,          -- 3000
    plc_polling_interval_ms, -- 1000
    use_connected_messaging  -- true
FROM historian_meta.tag_master
WHERE server_progid IS NOT NULL 
  AND enabled = true
  AND plc_ip_address IS NOT NULL
ORDER BY server_progid
```

### Required Table Columns

| Column | Type | Description | Example |
|--------|------|-------------|---------|
| `server_progid` | VARCHAR | Unique PLC identifier | `Rockwel_PLC_001` |
| `plc_protocol` | VARCHAR | Protocol type | `Rockwell` |
| `plc_ip_address` | VARCHAR | PLC IP address | `192.168.0.20` |
| `plc_port` | INTEGER | Communication port | `44818` |
| `plc_type` | VARCHAR | PLC hardware type | `ControlLogix` |
| `plc_path` | VARCHAR | Slot path | `1,0` |
| `plc_timeout_ms` | INTEGER | Connection timeout | `3000` |
| `use_connected_messaging` | BOOLEAN | Connected mode | `true` |
| `enabled` | BOOLEAN | Enable flag | `true` |

---

## 3. Tag Definitions (historian_meta.tag_master)

Each PLC's tags are loaded with:

```sql
SELECT 
    tag_id,                  -- 'Blastfurnace_Tuyer1_Pressure'
    tag_name,                -- Display name
    data_type,               -- 'double', 'int', 'boolean'
    eng_unit,                -- 'PSI', 'RPM', '°C'
    deadband_value,          -- 0.5 (change threshold)
    db_logging_interval_ms,  -- 1000 (logging rate)
    enabled                  -- true/false
FROM historian_meta.tag_master
WHERE server_progid = @plcId AND enabled = true
ORDER BY tag_id
```

### Tag Column Definitions

| Column | Type | Description | Example |
|--------|------|-------------|---------|
| `tag_id` | VARCHAR(PK) | Unique tag address | `Blastfurnace_Tuyer1_Pressure` |
| `tag_name` | VARCHAR | Human-readable name | `Blast Furnace Tuyer 1 Pressure` |
| `data_type` | VARCHAR | Value type | `double`, `int`, `boolean` |
| `eng_unit` | VARCHAR | Engineering unit | `PSI`, `RPM`, `°C` |
| `deadband_value` | DOUBLE | Change detection threshold | `0.5` |
| `db_logging_interval_ms` | INTEGER | Minimum log interval | `1000` |
| `enabled` | BOOLEAN | Tag enabled flag | `true` |

---

## 4. Transport Configuration (appsettings.json)

### MQTT Settings
```json
"Mqtt": {
  "Enabled": true,
  "BrokerHost": "localhost",
  "BrokerPort": 1883,
  "ClientId": "PlcGateway_Server",
  "TopicPrefix": "plc",
  "PublishMode": "Bulk",
  "QualityOfService": 1,
  "RetainMessages": true
}
```

**MQTT Topic Pattern**: `{TopicPrefix}/{PlcId}/all` → `plc/plc/all`

### TCP Broadcast Settings
```json
"LocalBroadcast": {
  "Enabled": true,
  "Port": 5050,
  "IntervalMs": 1000,
  "BindAddress": "0.0.0.0"
}
```

### Transport General
```json
"Transport": {
  "Enabled": true,
  "PublishIntervalMs": 1000
}
```

---

## 5. Adding New PLC Tags

### Step 1: Insert into historian_meta.tag_master

```sql
INSERT INTO historian_meta.tag_master (
    tag_id, tag_name, data_type, 
    server_progid, plc_protocol, plc_ip_address, plc_port,
    plc_type, plc_path, use_connected_messaging,
    eng_unit, deadband_value, db_logging_interval_ms, 
    enabled, created_by
) VALUES 
    ('Motor_Speed_RPM', 'Motor Speed', 'double',
     'Rockwel_PLC_001', 'Rockwell', '192.168.0.20', 44818,
     'ControlLogix', '1,0', true,
     'RPM', 10.0, 1000,
     true, 'admin'),
    ('Tank_Level_Percent', 'Tank Level', 'double',
     'Rockwel_PLC_001', 'Rockwell', '192.168.0.20', 44818,
     'ControlLogix', '1,0', true,
     '%', 0.5, 1000,
     true, 'admin');
```

### Step 2: Restart the Server

The `PlcConfigLoaderService` loads config at startup:
```bash
dotnet run
```

### Step 3: Verify Tags

```bash
# REST API
curl http://localhost:5001/api/plc/values

# MQTT (subscribe)
mosquitto_sub -h localhost -t "plc/#" -v
```

---

## 6. Current Configuration (Dec 2025)

### PLC Connection
| Setting | Value |
|---------|-------|
| PLC ID | `Rockwel_PLC_001` |
| IP Address | `192.168.0.20` |
| Port | `44818` |
| PLC Type | `ControlLogix` |
| Path | `1,0` |
| Connected Messaging | `true` |

### Tags (32 total)
```
Blastfurnace_Tuyer1_Pressure    Pump_RPM
Blastfurnace_Tuyer2_Pressure    Pump_Discharge_Pressure
Blastfurnace_Tuyer3_Pressure    Pump_Suction_Pressure
... (32 tags in historian_meta.tag_master)
```

### Endpoints
| Endpoint | URL/Address |
|----------|-------------|
| REST API | `http://localhost:5001/api/plc/values` |
| PLC Status | `http://localhost:5001/api/plc/status` |
| MQTT Broker | `localhost:1883` |
| MQTT Topic | `plc/plc/all` |
| TCP Broadcast | `0.0.0.0:5050` |
| HMI Page | `http://localhost:5002` |

---

## 7. Data Type Mapping

The `PlcConfigLoaderService` maps database types to PLC types:

| Database Type | PLC Type |
|---------------|----------|
| `boolean`, `bool` | `bool` |
| `int`, `integer` | `int32` |
| `double`, `float` | `float` |
| (default) | `float` |

---

## 8. Protocol Support

| Protocol | Supported | Example |
|----------|-----------|---------|
| Rockwell (AB) | ✅ Yes | ControlLogix, CompactLogix |
| Siemens S7 | ⚙️ Planned | S7-300/400/1200/1500 |
| Modbus TCP | ⚙️ Planned | Generic Modbus |
| EtherNet/IP | ⚙️ Planned | CIP Protocol |
| OPC UA | ⚙️ Planned | OPC UA Servers |

---

## 9. Troubleshooting

### No Tags Loading
1. Check database connection:
   ```sql
   SELECT COUNT(*) FROM historian_meta.tag_master WHERE enabled = true;
   ```
2. Verify `server_progid` matches in all tag rows
3. Check logs for `[CONFIG LOADER]` messages

### PLC Connection Failed
1. Verify PLC IP is reachable: `ping 192.168.0.20`
2. Check firewall allows port 44818
3. Verify PLC slot path (`1,0` for slot 0)

### MQTT Not Publishing
1. Verify Mosquitto is running: `netstat -an | findstr 1883`
2. Check `Mqtt.Enabled = true` in appsettings.json
3. Subscribe to topic: `mosquitto_sub -t "plc/#" -v`

---

## 10. File Locations

| File | Purpose |
|------|---------|
| `appsettings.json` | Database connection, MQTT/Transport settings |
| `Services/PlcGateway/Services/PlcConfigLoaderService.cs` | Loads config from database |
| `Services/PlcGateway/Services/PlcGatewayService.cs` | Main gateway service |
| `Services/PlcGateway/Services/PlcDataPublisherService.cs` | MQTT/TCP publishing |
| `HMI/plc_mqtt_api_comparison.py` | HMI comparison page (port 5002) |

---

## Summary

**Configuration is read from TWO sources:**

1. **appsettings.json** → Database connection string, MQTT broker settings, transport config
2. **PostgreSQL historian_meta.tag_master** → PLC connection details (IP, port, path), tag definitions (name, type, deadband)

The `PlcConfigLoaderService` queries the database at startup, builds `PlcConfigEntry` objects, and passes them to `PlcGatewayService` which establishes PLC connections and begins polling.
