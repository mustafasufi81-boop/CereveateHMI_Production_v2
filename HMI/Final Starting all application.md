# Final Starting all application

Complete, verified guide to start the entire Cereveate HMI stack. Every command below has been tested and confirmed working.

---

## ✅ Verified Service Status

| Service | Port | Status |
|---------|------|--------|
| PostgreSQL | 5432 | 🟢 RUNNING |
| MQTT Broker (Mosquitto) | 1883 | 🟢 RUNNING |
| C# OPC DA Backend | 5001 | 🟢 RUNNING |
| Flask HMI Backend | 6001 | 🟢 RUNNING |
| Nginx Proxy | 8080 / 8443 | 🟢 RUNNING |
| Vite React Frontend | 8090 | 🟢 RUNNING |

---

## 📌 Port Map (Single Port per App — No Conflicts)

| Port | Application | Notes |
|------|-------------|-------|
| `5432` | **PostgreSQL** | Database `Automation_DB` (user `cereveate`) |
| `1883` | **Mosquitto MQTT Broker** | Live data transport |
| `5001` | **C# OPC DA Backend** | Main PLC/OPC service + SignalR `/opcHub` |
| `6001` | **Flask HMI Backend** | REST API + WebSocket |
| `8080` | **Nginx** (HTTP) | Reverse proxy |
| `8443` | **Nginx** (HTTPS) | Reverse proxy SSL |
| `8090` | **Vite React Frontend** | Dev UI — **open this in browser** |

> ⚠️ **Important:** Nginx uses `8080` and Vite uses `8090`. These were previously clashing — the bundled `nginx-1.28.0\conf\nginx.conf` was fixed from `8090` → `8080`.

---

## 🐍 Environments

| Component | Location | Run Tool |
|-----------|----------|----------|
| **Python venv** | `d:\CereveateHMI_Production\HMI\.venv` | `.venv\Scripts\python.exe` (Python 3.10) |
| **Node modules** | `d:\CereveateHMI_Production\HMI\apex-hmi\node_modules` | `npm` |

---

## ✅ Startup Order (Must Follow)

```
[PRE]  PostgreSQL   :5432   ← start first   (net start postgresql)
[PRE]  Mosquitto    :1883   ← start first   (net start mosquitto)
  1.   OPC Backend  :5001   ← C# PLC/OPC service
  2.   Flask HMI    :6001   ← main web API (wait ~10s)
  3.   Nginx        :8080   ← reverse proxy
  4.   Vite         :8090   ← React UI (browser)
```

---

## 🚀 STEP-BY-STEP — Start Each App in Its Own NEW CMD Window

> The golden rule: **each app must run in its own separate terminal window** so they stay alive independently. Below are the exact, tested commands.

### Step 0 — Pre-requisites (run once)
```cmd
net start postgresql
net start mosquitto
```

---

### Step 1 — C# OPC DA Backend (Port 5001)
Open a **new CMD window** and run:
```cmd
cd /d d:\CereveateHMI_Production\CSharpBackend\bin\Release\net8.0\publish
OpcDaWebBrowser.exe
```
- ✅ Verify: http://localhost:5001
- ⚠️ Single-instance only. If it exits instantly → it's already running.

---

### Step 2 — Flask HMI Backend (Port 6001)
Open a **new CMD window** and run:
```cmd
cd /d d:\CereveateHMI_Production\HMI
.venv\Scripts\python.exe app.py
```
- ✅ Verify: http://localhost:6001
- Takes ~10 seconds to fully bind.
- ⚠️ If you see `WinError 10048`, port 6001 is still held by an old instance. Kill it:
  ```cmd
  for /f "tokens=5" %a in ('netstat -ano ^| findstr :6001 ^| findstr LISTENING') do taskkill /PID %a /F
  ```

---

### Step 3 — Nginx Proxy (Port 8080 / 8443)
Open a **new CMD window** and run:
```cmd
cd /d d:\CereveateHMI_Production\HMI\nginx-1.28.0
nginx.exe
```
- ✅ Verify: http://localhost:8080
- Test config: `nginx.exe -t`
- Stop: `nginx.exe -s stop`

---

### Step 4 — Vite React Frontend (Port 8090)
Open a **new CMD window** and run:
```cmd
cd /d d:\CereveateHMI_Production\HMI\apex-hmi
npm run dev
```
- ✅ Open in browser: **http://localhost:8090**

---

## ⚡ One-Line Launchers (PowerShell — opens separate CMD windows)

These commands each pop a **new external CMD window** (tested working):

```powershell
# 1. OPC Backend
Start-Process cmd -ArgumentList '/k cd /d "d:\CereveateHMI_Production\CSharpBackend\bin\Release\net8.0\publish" && OpcDaWebBrowser.exe'

# 2. Flask HMI
Start-Process cmd -ArgumentList '/k cd /d "d:\CereveateHMI_Production\HMI" && .venv\Scripts\python.exe app.py'

# 3. Nginx
Start-Process cmd -ArgumentList '/k cd /d "d:\CereveateHMI_Production\HMI\nginx-1.28.0" && nginx.exe'

# 4. Vite
Start-Process cmd -ArgumentList '/k cd /d "d:\CereveateHMI_Production\HMI\apex-hmi" && npm run dev'
```

---

## 🔍 Check What Is Running / Stopped

Run this single command — it prints each service's status instantly:
```cmd
cmd /c "netstat -ano | findstr LISTENING > %TEMP%\p.txt & (findstr :5001 %TEMP%\p.txt >nul && echo OPC_5001=RUNNING || echo OPC_5001=STOPPED) & (findstr :6001 %TEMP%\p.txt >nul && echo FLASK_6001=RUNNING || echo FLASK_6001=STOPPED) & (findstr :8080 %TEMP%\p.txt >nul && echo NGINX_8080=RUNNING || echo NGINX_8080=STOPPED) & (findstr :8090 %TEMP%\p.txt >nul && echo VITE_8090=RUNNING || echo VITE_8090=STOPPED)"
```

---

## 🛑 Stop Everything

```cmd
taskkill /IM OpcDaWebBrowser.exe /F
taskkill /IM nginx.exe /F
taskkill /IM node.exe /F
for /f "tokens=5" %a in ('netstat -ano ^| findstr :6001 ^| findstr LISTENING') do taskkill /PID %a /F
```

---

## 🌐 Access Points

| What | URL |
|------|-----|
| **React UI (main — use this)** | http://localhost:8090 |
| Nginx Proxy (HTTP) | http://localhost:8080 |
| Nginx Proxy (HTTPS) | https://localhost:8443 |
| Flask API | http://localhost:6001 |
| OPC Backend | http://localhost:5001 |

---

## ⚠️ Troubleshooting Notes (lessons learned)

1. **App dies right after starting?**
   Don't launch with `start /B` attached to a shared terminal — a `Ctrl+C` in that terminal kills it. Always use a **separate CMD window** (`Start-Process cmd`).

2. **OPC Backend exits instantly?**
   It has a single-instance lock (`Global\CereveateOPCWebBrowser_SingleInstance`). It's already running — check port 5001.

3. **`FINDSTR: Cannot open :8080`?**
   That's a shell quoting glitch, **not** a real error. The port is fine.

4. **Nginx + Vite both on 8090?**
   Already fixed — Nginx is now `8080`, Vite stays `8090`.
