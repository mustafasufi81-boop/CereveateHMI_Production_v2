# HOW TO START THE APPLICATION
## Cereveate OPC DA / HMI Platform

---

## ARCHITECTURE OVERVIEW

```
┌─────────────────────────────────────────────────────────────────┐
│                        BROWSER                                   │
│              http://localhost:8090                               │
│         (React UI - TypeScript / Vite)                          │
└──────────────────────┬──────────────────────────────────────────┘
                       │  HTTP /api/*  →  port 6001
                       │  WebSocket /socket.io  →  port 6001
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                 FLASK HMI BACKEND  (Python)                      │
│                    port 6001                                     │
│  • Login / Auth / RBAC                                          │
│  • Alarm ACK / Clear API                                        │
│  • Historical trends API                                        │
│  • MQTT subscriber (receives live PLC data)                     │
│  • Socket.IO (pushes live data to browser)                      │
└──────────┬──────────────────────────┬────────────────────────────┘
           │  REST /api/alarms/*       │  SQL queries
           │  proxies to port 5001     │
           ▼                           ▼
┌──────────────────────┐   ┌──────────────────────────────────────┐
│  C# OPC BACKEND      │   │  PostgreSQL / TimescaleDB            │
│  port 5001           │   │  Database: Automation_DB             │
│  • OPC DA polling    │   │  port 5432                           │
│  • Alarm evaluation  │   │  • historian_raw (tag data)          │
│  • SignalR hub       │   │  • historian_meta (users, tags)      │
│  • Historian ingest  │   │  • historian_raw.alarm_active        │
└──────────┬───────────┘   └──────────────────────────────────────┘
           │ COM/DCOM
           ▼
┌──────────────────────┐   ┌──────────────────────────────────────┐
│  Matrikon OPC Server │   │  MQTT Broker (Mosquitto)             │
│  (you start this)    │   │  port 1883                           │
│  Supplies tag values │   │  Carries PLC live data to Flask      │
└──────────────────────┘   └──────────────────────────────────────┘
```

---

## PART 1 — C# BACKEND (OPC + Alarm Engine)

**Folder:** `c:\...\BACKUP_BEFORE_HISTORICAL_20251117_225747 - Copy_backup_20251206\`
**Port:** `5001`
**Language:** C# (.NET 8, x86)

### Start:
```cmd
cd "c:\MQTT_Implemented_OPC\Copied_MQTT\BACKUP_BEFORE_HISTORICAL_20251117_225747 - Copy_backup_20251206"
dotnet run
```

### What it does:
- Connects to **Matrikon OPC Server** (you must start OPC server first)
- Polls all OPC tags every **1000ms**
- Evaluates alarm conditions (ISA-18.2 state machine)
- Writes historian data to PostgreSQL (`historian_raw.historian_timeseries`)
- Exposes REST API on `http://localhost:5001/api/alarms/*`
- SignalR hub at `http://localhost:5001/opcHub`

### Ready when you see:
```
Now listening on: http://0.0.0.0:5001
```

---

## PART 2 — FLASK HMI BACKEND (Python)

**Folder:** `c:\...\WEB_HMI_MFA\HMI\`
**Port:** `6001`
**Language:** Python (Flask + Socket.IO)

### Start:
```cmd
cd "c:\MQTT_Implemented_OPC\Copied_MQTT\BACKUP_BEFORE_HISTORICAL_20251117_225747 - Copy_backup_20251206\WEB_HMI_MFA\HMI"
venv\Scripts\python.exe app.py
```

### What it does:
- Handles **login / logout / MFA** authentication
- Provides **alarm ACK / clear** API (proxies to C# backend)
- Provides **historical trends** API (reads from PostgreSQL)
- Subscribes to **MQTT broker** to receive live PLC tag data
- Pushes live tag data to browser via **Socket.IO (WebSocket)**
- Writes alarm audit trail to database

### Config file: `config.json`
```json
{
  "csharp_backend": { "host": "127.0.0.1", "port": 5001 },
  "hmi_server":     { "host": "0.0.0.0",   "port": 6001 },
  "database":       { "host": "localhost",  "port": 5432, "database": "Automation_DB" },
  "mqtt":           { "broker_host": "127.0.0.1", "broker_port": 1883 }
}
```

### Ready when you see:
```
[OK] Historical data service ready
[OK] MQTT client initialized
HMI Mode: FULL (Live MQTT/SignalR + Historical)
```

---

## PART 3 — REACT FRONTEND (Browser UI)

**Folder:** `c:\...\WEB_HMI_MFA\HMI\apex-hmi\`
**Port:** `8090` (dev server)
**Language:** TypeScript / React / Vite

### Start:
```cmd
cd "c:\MQTT_Implemented_OPC\Copied_MQTT\BACKUP_BEFORE_HISTORICAL_20251117_225747 - Copy_backup_20251206\WEB_HMI_MFA\HMI\apex-hmi"
npm run dev
```

### What it does:
- Serves the HMI dashboard at **http://localhost:8090**
- Proxies all `/api/*` requests → Flask on port 6001
- Proxies all `/socket.io/*` WebSocket → Flask on port 6001
- Provides: Login, Dashboard, Alarm Panel, Historical Trends, Reports

### Config file: `.env`
```
VITE_API_URL=http://localhost:6001/api
VITE_WS_URL=http://localhost:6001
```

### Ready when you see:
```
VITE v5.x.x  ready in xxx ms
➜  Local:   http://localhost:8090/
```

---

## PART 4 — MQTT BROKER (Mosquitto)

**Port:** `1883`
**Already running as a Windows service** (check with `netstat -an | findstr 1883`)

If not running:
```cmd
net start mosquitto
```
or start manually:
```cmd
"C:\Program Files\mosquitto\mosquitto.exe" -v
```

---

## STARTUP ORDER (IMPORTANT)

Start in this exact order:

```
1.  Matrikon OPC Server        ← you do this manually
2.  MQTT Broker (Mosquitto)    ← usually auto-starts as service
3.  C# Backend (dotnet run)    ← port 5001
4.  Flask HMI Backend          ← port 6001
5.  React Frontend (npm dev)   ← port 8090
```

---

## LOGIN CREDENTIALS

Open browser: **http://localhost:8090**

| Username | Password   | MFA Required | Role  |
|----------|------------|--------------|-------|
| `admin`  | (set yours)| ❌ No        | Admin |
| `Mustafa`| `Admin@123`| ❌ No (reset)| User  |
| `Talha`  | (set yours)| ❌ No        | User  |
| `shakil` | (set yours)| ✅ Yes (OTP) | Admin |

> **Note:** Mustafa's password was reset to `Admin@123` with MFA disabled on 12-May-2026.

---

## QUICK CHECK — IS EVERYTHING RUNNING?

Run this in PowerShell to check all ports:
```powershell
@(5001,5432,6001,8090,1883) | ForEach-Object {
    $r = netstat -an | Select-String ":$_\s.*LISTENING"
    if ($r) { Write-Host "✅ Port $_  RUNNING" -ForegroundColor Green }
    else     { Write-Host "❌ Port $_  NOT RUNNING" -ForegroundColor Red }
}
```

Expected output:
```
✅ Port 5001  RUNNING   ← C# Backend
✅ Port 5432  RUNNING   ← PostgreSQL
✅ Port 6001  RUNNING   ← Flask HMI
✅ Port 8090  RUNNING   ← React UI
✅ Port 1883  RUNNING   ← MQTT Broker
```

---

## STOP ALL SERVICES

| Service | How to stop |
|---------|-------------|
| C# Backend | Press `Ctrl+C` in its terminal |
| Flask HMI  | Press `Ctrl+C` in its terminal |
| React UI   | Press `Ctrl+C` in its terminal |
| MQTT       | `net stop mosquitto` |

---

## TROUBLESHOOTING

| Problem | Fix |
|---------|-----|
| Login fails with MFA screen | Use `admin` or `Mustafa` (no MFA) |
| `192.168.0.107:6002` refused | Wrong URL — use **localhost:8090** |
| Alarms not showing | Check C# backend is running on port 5001 |
| No live data | Check MQTT broker is running on port 1883 |
| Historical trends empty | Check PostgreSQL is running on port 5432 |
| React shows blank page | Run `npm run dev` in `apex-hmi` folder |
