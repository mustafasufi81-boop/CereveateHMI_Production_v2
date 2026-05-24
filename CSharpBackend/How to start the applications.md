# How to Start the Applications

## Overview

This system consists of **4 services** that must all be running for full functionality.

| # | Service | Port | URL |
|---|---------|------|-----|
| 1 | C# OPC Backend | 5001 | http://localhost:5001 |
| 2 | Flask HMI Backend | 6001 | http://localhost:6001 |
| 3 | HistoricalTrends / BI | 6004 | http://localhost:6004 |
| 4 | React Vite HMI (frontend) | 8090 | http://localhost:8090 |

**Login**: `http://localhost:8090` — Username: `Mustafa` / Password: `Admin@123`

---

## ⚠️ Important Rules Before Starting

1. **Start services in order**: C# first → Flask → HistoricalTrends → Vite
2. **Never run `dotnet build` or `RESTART_SERVER.bat`** — use the pre-built `.exe` instead
3. **Always set `PYTHONIOENCODING=utf-8`** when starting Python services — prevents crash on Windows
4. **Port 8090 can be stolen** by `WsToastNotification.exe` — always verify the correct PID owns the port

---

## Step 1 — Start C# OPC Backend (Port 5001)

Open a **new Command Prompt** window and run:

```cmd
cd /d "c:\MQTT_Implemented_OPC\Copied_MQTT\BACKUP_BEFORE_HISTORICAL_20251117_225747 - Copy_backup_20251206\bin\Release\net8.0\win-x86"
OpcDaWebBrowser.exe
```

**Verify:**
```powershell
netstat -ano | findstr ":5001" | findstr LISTENING
# Should show a PID → confirm with:
Get-Process -Id <PID>   # ProcessName should be OpcDaWebBrowser
```

> This also starts the embedded **MQTT broker on port 1883** automatically.

---

## Step 2 — Start Flask HMI Backend (Port 6001)

Open a **new Command Prompt** window and run:

```cmd
cd /d "c:\MQTT_Implemented_OPC\Copied_MQTT\BACKUP_BEFORE_HISTORICAL_20251117_225747 - Copy_backup_20251206\WEB_HMI_MFA\HMI"
set PYTHONIOENCODING=utf-8
python app.py
```

**Verify:**
```powershell
netstat -ano | findstr ":6001" | findstr LISTENING
# Quick API test:
Invoke-RestMethod "http://localhost:6001/api/alarms/active" -Headers @{"Authorization"="Bearer dummy"}
# Should return: success=True
```

> ⚠️ The `PYTHONIOENCODING=utf-8` line is **mandatory**. Without it Flask will crash on startup due to emoji characters in MQTT log messages.

---

## Step 3 — Start HistoricalTrends / BI Engine (Port 6004)

Open a **new Command Prompt** window and run:

```cmd
cd /d "c:\MQTT_Implemented_OPC\Copied_MQTT\BACKUP_BEFORE_HISTORICAL_20251117_225747 - Copy_backup_20251206\HistoricalTrends"
set PYTHONIOENCODING=utf-8
python app.py
```

**Verify:**
```powershell
netstat -ano | findstr ":6004" | findstr LISTENING
```

> This service powers the Analytics tab and Predictive Trends in the HMI.

---

## Step 4 — Start React Vite HMI Frontend (Port 8090)

Open a **new Command Prompt** window and run:

```cmd
cd /d "c:\MQTT_Implemented_OPC\Copied_MQTT\BACKUP_BEFORE_HISTORICAL_20251117_225747 - Copy_backup_20251206\WEB_HMI_MFA\HMI\apex-hmi"
npm run dev
```

**Verify:**
```powershell
netstat -ano | findstr ":8090" | findstr LISTENING
# Then confirm it's actually node (not WsToastNotification):
Get-Process -Id <PID>   # ProcessName MUST be node
```

> Wait ~10 seconds after running `npm run dev` before opening the browser.

---

## Step 5 — Final Check (All 4 Services)

Run this to confirm all ports are listening at once:

```powershell
netstat -ano | findstr ":5001 :6001 :6004 :8090" | findstr LISTENING
# Should show 4 lines (one per port)
```

Then open: **http://localhost:8090** → login with `Mustafa` / `Admin@123`

---

## Stopping a Service

To kill a service by port (PowerShell):

```powershell
# Replace 6001 with the port you want to kill
$pid = (netstat -ano | Select-String ":6001.*LISTENING") -replace '.*\s+(\d+)$','$1'
Stop-Process -Id ([int]$pid.Trim()) -Force
```

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Flask crashes immediately on start | Missing `PYTHONIOENCODING=utf-8` | Add `set PYTHONIOENCODING=utf-8` before `python app.py` |
| Port 8090 shows LISTENING but HMI is blank or 501 error | `WsToastNotification` stole the port | Kill that PID, then restart Vite |
| Analytics / Predictive Trends not loading | Port 6004 not running | Start HistoricalTrends (Step 3) |
| C# not starting | Wrong directory or wrong exe | Use `bin\Release\net8.0\win-x86\OpcDaWebBrowser.exe` — NOT `dotnet run` |
| Flask returns `{"error":"0"}` | Duplicate route in alarm controller | Check `alarm_controller.py` for duplicate `@alarm_bp.route` decorators |
| No OPC tags in historian DB | `historian_meta.tag_master` table empty | Insert rows into tag_master table — see `copilot-instructions.md` for SQL example |
| MQTT messages not arriving | C# not running | Start Step 1 first — MQTT broker is embedded in the C# service |

---

## Current Working State (as of May 23, 2026)

| Service | Status | PID | Notes |
|---------|--------|-----|-------|
| C# OPC Backend (5001) | ✅ Running | 29100 | Also runs MQTT on 1883 |
| Flask HMI (6001) | ✅ Running | 47668 | Started with `PYTHONIOENCODING=utf-8` |
| HistoricalTrends (6004) | ✅ Running | 35044 | BI engine + predictive trends |
| Vite React HMI (8090) | ✅ Running | 47008 | Frontend — open http://localhost:8090 |
