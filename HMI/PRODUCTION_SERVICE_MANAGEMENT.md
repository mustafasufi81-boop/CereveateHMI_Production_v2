# Production Service Management - Windows

## 📋 Overview

All HMI services run as **background processes** (no visible windows) on Windows.

---

## 🚀 Service Architecture

```
Background Services:
├─ Flask Backend (Waitress) → Port 6001
│  ├─ Runs silently via VBScript launcher
│  ├─ Logging: logs/waitress.log
│  └─ Auto-restart: No (use Windows Service for that)
│
└─ nginx (Frontend Proxy) → Port 8080
   ├─ Runs as background process
   ├─ Logging: C:/nginx/logs/
   └─ Serves React + Proxies to Flask
```

---

## 📂 Control Scripts

### 1. start_production.bat
**Purpose:** Start all services in background

**What it does:**
- ✓ Creates logs directory if missing
- ✓ Checks if services are already running (prevents duplicates)
- ✓ Starts Flask Backend using VBScript (silent, no window)
  - Output redirected to `logs/waitress.log`
  - Runs: `waitress-serve --host=0.0.0.0 --port=6001 ...`
- ✓ Starts nginx using `start /B` (background mode)
  - Logs to: `C:/nginx/logs/error.log` and `access.log`
- ✓ Validates startup success (checks ports 6001 and 8080)

**Usage:**
```cmd
start_production.bat
```

**Expected Output:**
```
[1/2] Starting Flask Backend (Waitress on port 6001)...
[SUCCESS] Flask Backend started on port 6001 (background service)

[2/2] Starting nginx (Frontend on port 8080)...
[SUCCESS] nginx started on port 8080 (background service)

Production HMI System Status
  Flask Backend:  http://localhost:6001
  nginx Frontend: http://localhost:8080
```

---

### 2. stop_production.bat
**Purpose:** Stop all background services

**What it does:**
- ✓ Stops nginx gracefully (`nginx.exe -s quit`)
- ✓ Force kills nginx if graceful shutdown fails
- ✓ Finds Flask backend process by port 6001
- ✓ Kills Flask/Waitress processes
- ✓ Cleans up any remaining Python backend processes

**Usage:**
```cmd
stop_production.bat
```

**Expected Output:**
```
[1/2] Stopping nginx...
[SUCCESS] nginx stopped gracefully

[2/2] Stopping Flask Backend (Waitress)...
[SUCCESS] Flask Backend stopped (PID: 12345)
```

---

### 3. status_production.bat
**Purpose:** Check if services are running

**What it does:**
- ✓ Checks nginx status (running/stopped + PID)
- ✓ Checks Flask backend status (port 6001 + PID)
- ✓ Shows active connection counts
- ✓ Displays last 5 lines from `logs/waitress.log`
- ✓ Lists all log file locations

**Usage:**
```cmd
status_production.bat
```

**Expected Output:**
```
[1/3] nginx Status (Frontend - Port 8080)
----------------------------------------
Status: RUNNING
PID: 8532
URL: http://localhost:8080

[2/3] Flask Backend Status (Waitress - Port 6001)
----------------------------------------
Status: RUNNING
PID: 9124
URL: http://localhost:6001

[3/3] Active Connections
----------------------------------------
nginx connections: 3
Backend connections: 5

[Logs]
----------------------------------------
Flask Backend Log: logs/waitress.log
Last 5 lines:
Serving on http://0.0.0.0:6001
...
```

---

### 4. restart_production.bat
**Purpose:** Restart all services

**What it does:**
- ✓ Calls `stop_production.bat`
- ✓ Waits 3 seconds for clean shutdown
- ✓ Calls `start_production.bat`

**Usage:**
```cmd
restart_production.bat
```

---

## 🔍 How Background Execution Works

### Flask Backend (VBScript Launcher)
The script creates a temporary VBScript file that launches the Flask backend without any visible window:

```vbscript
Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Shakil\DJangoProjects\NEW_HMI\HMI"
WshShell.Run "cmd /c venv\Scripts\activate.bat && waitress-serve ...", 0, False
```

**Parameters:**
- `0` = Hidden window (no console)
- `False` = Don't wait for completion (async)

**Output Redirection:**
- `> logs\waitress.log 2>&1` = All output goes to log file

---

### nginx (Background Process)
nginx naturally runs as a background process. We use:

```cmd
start /B "" "C:\nginx\nginx.exe"
```

**Parameters:**
- `/B` = Background mode (no new window)
- nginx master process spawns workers automatically

---

## 📊 Monitoring Services

### Real-Time Monitoring

**Check if services are running:**
```cmd
# Flask Backend
netstat -ano | findstr ":6001"

# nginx
tasklist | findstr "nginx.exe"
```

**View live logs:**
```cmd
# Flask Backend (PowerShell)
Get-Content logs\waitress.log -Wait -Tail 20

# nginx Error Log
Get-Content C:\nginx\logs\error.log -Wait -Tail 20

# nginx Access Log
Get-Content C:\nginx\logs\access.log -Wait -Tail 20
```

---

## 🛠 Troubleshooting

### Services Won't Start

**Problem:** Port 6001 already in use
```cmd
# Find process using port 6001
netstat -ano | findstr ":6001"

# Kill the process (replace PID)
taskkill /F /PID <PID>
```

**Problem:** nginx error "address already in use"
```cmd
# Find process using port 8080
netstat -ano | findstr ":8080"

# Kill the process
taskkill /F /PID <PID>
```

**Problem:** nginx not found
```
# Install nginx to C:\nginx or update paths in scripts
```

---

### Services Won't Stop

**Problem:** Process stuck
```cmd
# Force kill Flask backend
wmic process where "CommandLine like '%waitress%'" delete

# Force kill nginx
taskkill /F /IM nginx.exe
```

---

### Logs Not Created

**Problem:** logs/waitress.log not found
```cmd
# Ensure logs directory exists
mkdir logs

# Check permissions - run as Administrator if needed
```

---

## 🔄 For Production (Windows Service)

For automatic startup on boot, install as Windows Service:

```cmd
# Run as Administrator
install_service_windows.bat
```

This uses NSSM (Non-Sucking Service Manager) to create a proper Windows Service that:
- ✓ Starts automatically on boot
- ✓ Restarts on failure
- ✓ Runs under SYSTEM or custom account
- ✓ Managed via Services applet (services.msc)

---

## 📝 Access URLs

**With nginx (Recommended):**
- **Frontend:** http://localhost:8080
- **API:** http://localhost:8080/api/
- **WebSocket:** ws://localhost:8080/socket.io/

**Direct Flask (Without nginx):**
- **Everything:** http://localhost:6001

---

## ⚡ Quick Reference

```cmd
# Start all services
start_production.bat

# Check status
status_production.bat

# View Flask logs
type logs\waitress.log

# View nginx logs
type C:\nginx\logs\error.log

# Restart services
restart_production.bat

# Stop all services
stop_production.bat

# Install as Windows Service (boot auto-start)
install_service_windows.bat
```

---

**Version:** 2.0  
**Date:** February 21, 2026  
**Services:** Flask (Waitress) + nginx  
**Mode:** Background/Silent Execution
