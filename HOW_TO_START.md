# HOW TO START — Cereveate HMI Production
**Root:** `D:\CereveateHMI_Production\`

---

## Port Map

| Port | Service |
|------|---------|
| 1883 | Mosquitto MQTT Broker |
| 5001 | C# OPC Backend |
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

### Step 4 — MQTT Subscriber Service

**First time only — create venv:**
```cmd
cd D:\CereveateHMI_Production\mqtt_subscriber_service
python -m venv venv
venv\Scripts\pip install -r requirements.txt
```

**Every time — start service:**
```cmd
cd D:\CereveateHMI_Production\mqtt_subscriber_service
start "MQTT Subscriber" cmd /k "venv\Scripts\activate && set PYTHONPATH=%CD% && python src\service_main.py"
```

---

### Step 5 — Flask HMI Backend

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
| MQTT subscriber crashing | `cd mqtt_subscriber_service && venv\Scripts\activate && python src\service_main.py` |
| DB auth error | `appsettings.json` must have `Username=cereveate` `Password=cereveate@222` |
| OPC not connecting | Verify Matrikon OPC server is registered via `dcomcnfg` |

---

## System Overview

```
D:\CereveateHMI_Production\
├── CSharpBackend\               ← .NET 8 OPC DA server (reads OPC tags, publishes to MQTT, writes to DB)
├── HMI\                         ← Python Flask web app + Nginx frontend
└── mqtt_subscriber_service\     ← Python MQTT subscriber (processes MQTT messages → DB)
```

**Startup order:**
```
1. PostgreSQL  →  2. Mosquitto  →  3. C# OPC Backend  →  4. MQTT Subscriber  →  5. Flask HMI + Nginx
```

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

## Step 4 — Start MQTT Subscriber Service

```cmd
cd D:\CereveateHMI_Production\mqtt_subscriber_service
run_service.bat
```

This script automatically:
- Creates `venv\` if missing
- Installs `requirements.txt`
- Starts `src\service_main.py`

To run in background:
```cmd
cd D:\CereveateHMI_Production\mqtt_subscriber_service
start_service.bat
```

---

## Step 5 — Start Flask HMI + Nginx

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

### MQTT Subscriber venv (if `venv\` is missing)
The `run_service.bat` creates it automatically. Or manually:
```cmd
cd D:\CereveateHMI_Production\mqtt_subscriber_service
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
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
| DB auth error for `postgres` user | `appsettings.json` must have `Username=cereveate`, not `postgres` |
| Flask not starting | Run `.venv\Scripts\activate` then `python app.py` manually to see error |
| Nginx fails | Check `HMI\nginx-1.28.0\logs\error.log` |
| MQTT not connecting | Verify Mosquitto running on port 1883 |
| OPC not connecting | Verify Matrikon OPC server COM registration via `dcomcnfg` |
| MQTT subscriber errors | Run `run_service.bat` manually to see console output |
