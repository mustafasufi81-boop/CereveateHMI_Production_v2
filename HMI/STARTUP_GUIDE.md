# 🚀 Cereveate HMI — Startup Guide

Complete reference for starting every service in the HMI stack: virtual environments, port numbers, and exact commands.

---

## 📋 Service Overview

| # | Service | Type | Port | Working Directory |
|---|---------|------|------|-------------------|
| — | **PostgreSQL** | Database | `5432` | Windows Service |
| — | **Mosquitto** | MQTT Broker | `1883` | Windows Service |
| 1 | **C# OPC DA Backend** | PLC/OPC connectivity | `5001` | `CSharpBackend\bin\Release\net8.0\publish` |
| 2 | **MQTT Publisher** | DB → MQTT | — | `HMI` |
| 3 | **Flask HMI Backend** | Main web API | `6001` | `HMI` |
| 4 | **Nginx Proxy** | Reverse proxy | `8080` / `8443` | `HMI\nginx-1.28.0` |
| 5 | **Vite React Frontend** | Dev UI | `8090` | `HMI\apex-hmi` |
| 6 | **MQTT Dashboard** | Optional dashboard | — | `HMI` |

> ⚠️ **Port conflict fixed:** Nginx was previously set to `8090` (same as Vite). It is now `8080`.

---

## 🐍 Virtual Environment

The Python virtual environment lives at:

```
d:\CereveateHMI_Production\HMI\.venv
```

- **Python executable:** `.venv\Scripts\python.exe`
- **Python version:** 3.10.0
- **Pip:** `.venv\Scripts\pip.exe`

### First-Time Setup (only if `.venv` is missing)

```cmd
cd d:\CereveateHMI_Production\HMI
python -m venv .venv
.venv\Scripts\pip install -r requirements-production.txt
```

### Node / Vite Setup (only if `node_modules` is missing)

```cmd
cd d:\CereveateHMI_Production\HMI\apex-hmi
npm install
```

---

## ✅ Startup Sequence (Order Matters)

Start services **in this exact order**. Each depends on the previous ones being ready.

```
[PRE]  PostgreSQL   :5432   ← must be running first
[PRE]  Mosquitto    :1883   ← must be running first
  1.   OPC Backend  :5001   ← PLC/OPC main service
  2.   MQTT Publisher       ← reads DB, publishes to broker
  3.   Flask HMI    :6001   ← main web API (wait ~8s for it)
  4.   Nginx        :8080   ← reverse proxy
  5.   Vite         :8090   ← React dev UI
  6.   MQTT Dashboard       ← optional
```

---

## 🔧 Pre-Requisites (Database + Broker)

### PostgreSQL — Port 5432
```cmd
net start postgresql
```
- **Database:** `Automation_DB`
- **User:** `cereveate`
- **Host:** `localhost:5432`

### Mosquitto MQTT Broker — Port 1883
```cmd
net start mosquitto
```
- **Host:** `127.0.0.1:1883`

---

## 1️⃣ C# OPC DA Backend — Port 5001

**Main service for PLC/OPC connectivity + SignalR hub.**

```cmd
cd d:\CereveateHMI_Production\CSharpBackend\bin\Release\net8.0\publish
OpcDaWebBrowser.exe
```

- **URL:** http://localhost:5001
- **SignalR Hub:** http://localhost:5001/opcHub
- ⚠️ **Single-instance lock:** Only ONE instance can run. If it exits instantly, it's already running.

**Build it (if exe is missing):**
```cmd
cd d:\CereveateHMI_Production\CSharpBackend
build.bat
```

---

## 2️⃣ MQTT Publisher

**Reads tag values from the historian DB and publishes them to the MQTT broker.**

```cmd
cd d:\CereveateHMI_Production\HMI
.venv\Scripts\python.exe mqtt_publisher_realtime_from_db.py
```

- **Publishes to:** `127.0.0.1:1883`
- **Interval:** every 2 seconds

---

## 3️⃣ Flask HMI Backend — Port 6001

**Main web application / REST API / WebSocket server.**

```cmd
cd d:\CereveateHMI_Production\HMI
.venv\Scripts\python.exe app.py
```

- **URL:** http://localhost:6001
- **Logs:** `HMI\logs\hmi_app.log`
- ⚠️ If you get `WinError 10048` (port in use), an old instance is still running. Kill it:
  ```cmd
  for /f "tokens=5" %a in ('netstat -ano ^| findstr :6001 ^| findstr LISTENING') do taskkill /PID %a /F
  ```

---

## 4️⃣ Nginx Proxy — Port 8080 (HTTP) / 8443 (HTTPS)

**Reverse proxy in front of Flask + React.**

```cmd
cd d:\CereveateHMI_Production\HMI\nginx-1.28.0
nginx.exe
```

- **HTTP:** http://localhost:8080
- **HTTPS:** https://localhost:8443
- **Test config:** `nginx.exe -t`
- **Stop:** `nginx.exe -s stop`  (or `taskkill /IM nginx.exe /F`)

---

## 5️⃣ Vite React Frontend — Port 8090

**React development UI (proxies API calls to Flask & OPC backend).**

```cmd
cd d:\CereveateHMI_Production\HMI\apex-hmi
npm run dev
```

- **URL:** http://localhost:8090
- **Proxies:**
  - `/api` → http://localhost:6001 (Flask)
  - `/api/opc`, `/api/plc`, `/opcHub` → http://localhost:5001 (C# OPC)
  - `/socket.io` → http://localhost:6001 (WebSocket)

---

## 6️⃣ MQTT Dashboard (Optional)

**Separate dashboard showing live MQTT data from PostgreSQL.**

```cmd
cd d:\CereveateHMI_Production\HMI
.venv\Scripts\python.exe mqtt_app.py
```

---

## 🎯 One-Click Launch

Run everything in the correct order automatically:

```cmd
cd d:\CereveateHMI_Production\HMI
launch_all.bat
```

### Individual batch scripts (in `HMI\`)

| Script | Action |
|--------|--------|
| `start_opc_backend.bat` | Start C# OPC Backend |
| `start_mqtt_publisher.bat` | Start MQTT Publisher |
| `start_flask.bat` | Start Flask HMI |
| `start_nginx.bat` | Start Nginx |
| `start_vite.bat` | Start Vite frontend |
| `start_mqtt_app.bat` | Start MQTT Dashboard |
| `launch_all.bat` | Start everything in order |
| `stop_flask.bat` | Stop Flask |
| `stop_nginx.bat` | Stop Nginx |

---

## 🔍 Check What's Running

```cmd
netstat -ano | findstr LISTENING | findstr ":5001 :6001 :8080 :8090 :8443"
```

| Port | If listening → |
|------|----------------|
| `5432` | PostgreSQL ✅ |
| `1883` | Mosquitto ✅ |
| `5001` | OPC Backend ✅ |
| `6001` | Flask HMI ✅ |
| `8080` | Nginx HTTP ✅ |
| `8443` | Nginx HTTPS ✅ |
| `8090` | Vite Frontend ✅ |

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
| **React UI (Dev)** | http://localhost:8090 |
| **Nginx Proxy (HTTP)** | http://localhost:8080 |
| **Nginx Proxy (HTTPS)** | https://localhost:8443 |
| **Flask API** | http://localhost:6001 |
| **OPC Backend** | http://localhost:5001 |
