# HOW TO START — Cereveate HMI Production
**Root:** `D:\CereveateHMI_Production\`

---

## Port Map

| Port | Service |
|------|------|
| 1883 | Mosquitto MQTT Broker (live broadcast only — no DB writes) |
| 5001 | C# OPC/PLC Backend (historian DB writes owned here) |
| 6001 | Flask HMI Backend |
| 8090 | Nginx (React Frontend) |

---

## Startup Sequence (MUST follow this order)

### ✅ Step 1 — PostgreSQL  *(auto-starts as Windows Service)*
Verify running:
```powershell
Get-Service postgresql*
```
If stopped, start it (run as Administrator):
```powershell
Start-Service -Name postgresql-x64-17
```

---

### ✅ Step 2 — Mosquitto MQTT Broker  *(auto-starts as Windows Service)*
Verify running:
```powershell
Get-Service mosquitto
netstat -ano | findstr ":1883"
```
If stopped, start it (run as Administrator):
```powershell
Start-Service -Name mosquitto
```

---

### Step 3 — C# OPC Backend
```powershell
Start-Process "D:\CereveateHMI_Production\CSharpBackend\bin\Release\net8.0\publish\OpcDaWebBrowser.exe" `
  -WorkingDirectory "D:\CereveateHMI_Production\CSharpBackend\bin\Release\net8.0\publish" `
  -WindowStyle Normal
```
Verify (wait ~5 seconds):
```powershell
netstat -ano | findstr ":5001"
```

---

### Step 4 — Flask HMI Backend

**First time only — install deps into .venv:**
```cmd
cd D:\CereveateHMI_Production\HMI
.venv\Scripts\pip install -r requirements-production.txt
```

**Every time — start Flask:**
```cmd
cd D:\CereveateHMI_Production\HMI
start "Flask HMI" cmd /k ".venv\Scripts\activate && python app.py"
```
Verify (wait ~5 seconds):
```powershell
netstat -ano | findstr ":6001"
```

---

### Step 6 — Nginx (React Frontend)
```cmd
cd D:\CereveateHMI_Production\HMI\nginx-1.28.0
start "Nginx" nginx.exe
```
Verify:
```powershell
netstat -ano | findstr ":8090"
```

**Access HMI at:** `http://localhost:8090`

---

## Stop Everything
```powershell
Get-Process nginx -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process OpcDaWebBrowser -ErrorAction SilentlyContinue | Stop-Process -Force
```
PostgreSQL and Mosquitto keep running (Windows services — leave them alone).

---

## Rebuild C# Backend  *(only if source code changed)*
```cmd
cd D:\CereveateHMI_Production\CSharpBackend
build.bat
```
Output: `bin\Release\net8.0\publish\OpcDaWebBrowser.exe`

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Port 5001 not listening | Check OpcDaWebBrowser window for errors; verify `appsettings.json` DB credentials |
| Flask not starting | `cd HMI && .venv\Scripts\activate && python app.py` — read the console error |
| Nginx port conflict | Another app on 8090 — `netstat -ano \| findstr ":8090"` then kill the PID |
| DB auth error | `appsettings.json` must have `Username=cereveate` `Password=cereveate@222` |
| OPC API returns 0 tags | 🅿️ PARKED — see `BUG_FIX_LOG.md`. Check `tag_master` has rows with `server_progid=Matrikon.OPC.Simulation.1` |
| Dashboard cards blank for non-admin | Fixed — RBAC now passes `(None,None)` plant/area tags for all users (see `BUG_FIX_LOG.md` Problem 2) |
| Alarm endpoint crashes | Fixed — `alarm_controller.py` uses `db_pool` + auto-reconnect property (see `BUG_FIX_LOG.md` Problem 1) |

---

## System Overview

```
D:\CereveateHMI_Production\
├── CSharpBackend\           ← .NET 8 backend: reads OPC/PLC tags, writes to DB, publishes to MQTT
├── HMI\                     ← Python Flask web app + Nginx React frontend
└── mqtt_subscriber_service\ ← ❌ DISABLED (was duplicate DB writer — C# already owns all writes)
```

**Startup order:**
```
1. PostgreSQL  →  2. Mosquitto  →  3. C# OPC/PLC Backend  →  4. Flask HMI  →  5. Nginx
```
> ⚠️ `mqtt_subscriber_service` is **permanently removed** — it was writing duplicate data to DB. C# owns all DB persistence.

---

## Prerequisites

| Dependency | Where | Notes |
|-----------|-------|-------|
| **PostgreSQL** | Windows Service | DB: `Automation_DB`, User: `cereveate`, PW: `cereveate@222` |
| **Mosquitto MQTT** | Windows Service or manual | Port `1883` |
| **Python 3.11+** | System PATH | Only needed if re-creating a venv |
| **Nginx** | `HMI\nginx-1.28.0\` | Already included — no install needed |
| **.NET 8 Runtime** | Not required | C# EXE is self-contained |

---

## Step 1 — Start PostgreSQL

Usually auto-starts as a Windows service. To check/start:

```powershell
# Run as Administrator
Start-Service -Name postgresql*
```

Or: `services.msc` → find **postgresql** → Start

---

## Step 2 — Start Mosquitto MQTT Broker

```powershell
# Run as Administrator
Start-Service -Name mosquitto
```

Or run manually:
```cmd
"C:\Program Files\mosquitto\mosquitto.exe" -v
```

Verify running:
```powershell
netstat -ano | findstr ":1883"
```

---

## Step 3 — Start C# OPC Backend

The EXE is **self-contained** (no .NET install needed).

```cmd
cd D:\CereveateHMI_Production\CSharpBackend\bin\Release\net8.0\publish
OpcDaWebBrowser.exe
```

Or in PowerShell (keeps it running in its own window):
```powershell
Start-Process "D:\CereveateHMI_Production\CSharpBackend\bin\Release\net8.0\publish\OpcDaWebBrowser.exe" `
  -WorkingDirectory "D:\CereveateHMI_Production\CSharpBackend\bin\Release\net8.0\publish"
```

**Expected output:**
```
[CONFIG] MaxWaitMs loaded: 500ms
Listening on http://0.0.0.0:5001
OPC connected: Matrikon.OPC.Simulation.1
```

Verify:
```powershell
netstat -ano | findstr ":5001"
```

---

## Step 4 — Start Flask HMI + Nginx

```cmd
cd D:\CereveateHMI_Production\HMI
start_all_services.bat
```

This starts:
1. Flask backend on **port 6001** (using `.venv`)
2. Nginx on **port 8080** (HTTP) and **8443** (HTTPS)

**Access the HMI at:** `http://localhost:8080`

---

## Verify All Services Running

```powershell
netstat -ano | findstr "1883 5001 6001 8080"
```

| Port | Service |
|------|---------|
| 1883 | Mosquitto MQTT |
| 5001 | C# OPC Backend |
| 6001 | Flask HMI |
| 8080 | Nginx (HTTP) |

---

## Stop Everything

```cmd
cd D:\CereveateHMI_Production\HMI
stop_all_services.bat

cd D:\CereveateHMI_Production\mqtt_subscriber_service
stop_service.bat
```

Stop C# backend:
```powershell
Get-Process OpcDaWebBrowser | Stop-Process
```

---

## First-Time Setup

### HMI venv (if `.venv\` is missing)
```cmd
cd D:\CereveateHMI_Production\HMI
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-production.txt
```

---

## Rebuild C# Backend (only if source code changed)

```cmd
cd D:\CereveateHMI_Production\CSharpBackend
build.bat
```

Output: `bin\Release\net8.0\publish\OpcDaWebBrowser.exe`

---

## Key Config File

`D:\CereveateHMI_Production\CSharpBackend\appsettings.json`

```json
"ConnectionStrings": {
  "PlcGateway": "Host=localhost;Port=5432;Database=Automation_DB;Username=cereveate;Password=cereveate@222"
},
"Historian": {
  "Database": {
    "ConnectionString": "Host=localhost;Port=5432;Database=Automation_DB;Username=cereveate;Password=cereveate@222"
  }
}
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Port 5001 not listening | Check `OpcDaWebBrowser.exe` started; check `appsettings.json` DB credentials |
| DB auth error | `appsettings.json` must have `Username=cereveate`, not `postgres` |
| Flask not starting | Run `.venv\Scripts\activate` then `python app.py` manually to see error |
| Nginx fails | Check `HMI\nginx-1.28.0\logs\error.log` |
| MQTT broker down | Verify Mosquitto running: `Get-Service mosquitto` |
| OPC API returns 0 tags | 🅿️ PARKED — see `BUG_FIX_LOG.md` for investigation steps |
| Dashboard blank for non-admin | ✅ Fixed — see `BUG_FIX_LOG.md` Problem 2 |
| Alarm endpoint crashes | ✅ Fixed — see `BUG_FIX_LOG.md` Problem 1 |
