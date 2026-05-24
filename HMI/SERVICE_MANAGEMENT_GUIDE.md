# HMI Service Management Scripts

## Overview
Comprehensive scripts to manage all HMI services: **Nginx** (Frontend Proxy) and **Flask Backend** (Waitress).

## Configuration Summary

### Nginx Configuration
- **Location**: `nginx-1.28.0\conf\nginx.conf`
- **HTTP Port**: 8080
- **HTTPS Port**: 8443
- **SSL Certificates**: `nginx-1.28.0\ssl\localhost.crt` and `localhost.key`

### Flask Backend
- **Port**: 6001
- **Server**: Waitress (Production WSGI Server)
- **Threads**: 6
- **Connection Limit**: 1000

### Architecture
```
User Browser
    ↓
Nginx (8080/8443)
    ↓ Proxy
    ├─→ /api/* → Flask Backend (6001)
    ├─→ /socket.io/* → Flask WebSocket (6001)
    └─→ /* → React Static Files (apex-hmi/dist/)
```

---

## Service Management Scripts

### Windows Batch Files (.bat)
Use these for simple command-line execution:

| Script | Description |
|--------|-------------|
| `start_all_services.bat` | Start Nginx + Flask Backend |
| `stop_all_services.bat` | Stop all services |
| `restart_all_services.bat` | Restart all services |
| `status_all_services.bat` | Check service status |

**Usage:**
```cmd
start_all_services.bat
stop_all_services.bat
restart_all_services.bat
status_all_services.bat
```

### PowerShell Scripts (.ps1)
Use these for better error handling and detailed output:

| Script | Description |
|--------|-------------|
| `start_all_services.ps1` | Start Nginx + Flask Backend |
| `stop_all_services.ps1` | Stop all services |
| `restart_all_services.ps1` | Restart all services |
| `status_all_services.ps1` | Check service status with diagnostics |

**Usage:**
```powershell
.\start_all_services.ps1
.\stop_all_services.ps1
.\restart_all_services.ps1
.\status_all_services.ps1
```

---

## Quick Start Guide

### 1. Initial Setup
Before starting services, ensure:

```cmd
# Create virtual environment (if not exists)
python -m venv venv

# Activate virtual environment
venv\Scripts\activate

# Install dependencies
pip install -r requirements-production.txt

# Build React frontend (if not already built)
cd apex-hmi
npm install
npm run build
cd ..
```

### 2. Start Services
```cmd
# Option 1: Using batch file
start_all_services.bat

# Option 2: Using PowerShell
.\start_all_services.ps1
```

### 3. Access Your Application
- **HTTP**: http://localhost:8080
- **HTTPS**: https://localhost:8443
- **Backend API**: http://localhost:6001/api/

### 4. Check Status
```cmd
# Option 1: Using batch file
status_all_services.bat

# Option 2: Using PowerShell
.\status_all_services.ps1
```

### 5. Stop Services
```cmd
# Option 1: Using batch file
stop_all_services.bat

# Option 2: Using PowerShell
.\stop_all_services.ps1
```

---

## Service Details

### Start Sequence
1. **Flask Backend** starts on port 6001 (runs in background)
2. **Nginx** starts and listens on ports 8080 (HTTP) and 8443 (HTTPS)
3. Nginx proxies API requests to Flask backend
4. Nginx serves React static files for frontend

### Stop Sequence
1. **Nginx** is stopped (graceful shutdown, then force if needed)
2. **Flask Backend** is stopped (terminates Waitress process on port 6001)

---

## Troubleshooting

### Services Won't Start

**Check Port Availability:**
```cmd
# Check if ports are in use
netstat -ano | findstr ":6001"
netstat -ano | findstr ":8080"
netstat -ano | findstr ":8443"
```

**Check Dependencies:**
```cmd
# Verify virtual environment
venv\Scripts\python.exe --version

# Test Flask app directly
venv\Scripts\activate
python app.py
```

**Check Nginx Configuration:**
```cmd
cd nginx-1.28.0
nginx.exe -t
```

### Services Won't Stop

**Force Stop All:**
```cmd
# Kill nginx
taskkill /F /IM nginx.exe

# Kill Python processes
taskkill /F /IM python.exe

# Or restart your computer
shutdown /r /t 0
```

### Check Logs

**Flask Backend Logs:**
```cmd
type logs\waitress.log
```

**Nginx Access Logs:**
```cmd
type nginx-1.28.0\logs\hmi_access.log
```

**Nginx Error Logs:**
```cmd
type nginx-1.28.0\logs\hmi_error.log
```

**Nginx SSL Logs:**
```cmd
type nginx-1.28.0\logs\hmi_ssl_access.log
type nginx-1.28.0\logs\hmi_ssl_error.log
```

### SSL Certificate Issues

If you get SSL warnings when accessing https://localhost:8443:

1. **Use Self-Signed Certificates (Default)**
   - Browser will show warning - this is normal for development
   - Click "Advanced" → "Proceed to localhost"

2. **Generate New Self-Signed Certificates**
   ```cmd
   cd nginx-1.28.0\ssl
   
   # Using OpenSSL (if installed)
   openssl req -x509 -nodes -days 365 -newkey rsa:2048 ^
     -keyout localhost.key -out localhost.crt ^
     -subj "/C=US/ST=State/L=City/O=Organization/CN=localhost"
   ```

3. **Use Production Certificates**
   - Replace `nginx-1.28.0\ssl\localhost.crt` and `localhost.key`
   - Update paths in `nginx-1.28.0\conf\nginx.conf` if needed

---

## Advanced Configuration

### Change Nginx Ports

Edit `nginx-1.28.0\conf\nginx.conf`:

```nginx
# HTTP Server
server {
    listen 8080;  # Change this
    ...
}

# HTTPS Server
server {
    listen 8443 ssl http2;  # Change this
    ...
}
```

Then restart services:
```cmd
restart_all_services.bat
```

### Change Flask Backend Port

1. Edit `start_all_services.bat` or `start_all_services.ps1`
2. Change `--port=6001` to your desired port
3. Update `nginx-1.28.0\conf\nginx.conf`:
   ```nginx
   upstream hmi_backend {
       server 127.0.0.1:YOUR_NEW_PORT;
   }
   ```
4. Restart services

### Add More Nginx Workers

Edit `nginx-1.28.0\conf\nginx.conf`:

```nginx
worker_processes 4;  # Change from 1 to number of CPU cores
```

### Increase Waitress Threads

Edit start scripts and change:
```
--threads=6  # Increase for more concurrent requests
```

---

## Production Deployment

### Windows Service Installation

For automatic startup on boot, consider installing as Windows services:

1. **Using NSSM (Non-Sucking Service Manager)**
   ```cmd
   # Download NSSM from https://nssm.cc/
   
   # Install Flask Backend service
   nssm install HMI-Backend "C:\Shakil\DJangoProjects\NEW_HMI\HMI\venv\Scripts\waitress-serve.exe"
   nssm set HMI-Backend AppParameters "--host=0.0.0.0 --port=6001 --threads=6 wsgi:application"
   nssm set HMI-Backend AppDirectory "C:\Shakil\DJangoProjects\NEW_HMI\HMI"
   
   # Install Nginx service
   nssm install HMI-Nginx "C:\Shakil\DJangoProjects\NEW_HMI\HMI\nginx-1.28.0\nginx.exe"
   nssm set HMI-Nginx AppDirectory "C:\Shakil\DJangoProjects\NEW_HMI\HMI\nginx-1.28.0"
   
   # Start services
   nssm start HMI-Backend
   nssm start HMI-Nginx
   ```

### Firewall Configuration

Allow ports through Windows Firewall:

```cmd
# Allow HTTP (8080)
netsh advfirewall firewall add rule name="HMI HTTP" dir=in action=allow protocol=TCP localport=8080

# Allow HTTPS (8443)
netsh advfirewall firewall add rule name="HMI HTTPS" dir=in action=allow protocol=TCP localport=8443
```

---

## Monitoring

### Real-Time Log Monitoring

**PowerShell:**
```powershell
# Watch Flask logs
Get-Content logs\waitress.log -Wait -Tail 20

# Watch Nginx logs
Get-Content nginx-1.28.0\logs\hmi_access.log -Wait -Tail 20
```

**Command Prompt:**
```cmd
# Create a monitoring script
powershell -Command "Get-Content logs\waitress.log -Wait -Tail 20"
```

### Health Checks

Create a simple health check script `health_check.ps1`:
```powershell
# Check backend
$backend = Invoke-WebRequest -Uri "http://localhost:6001/api/" -UseBasicParsing -ErrorAction SilentlyContinue
Write-Host "Backend: $($backend.StatusCode)"

# Check frontend
$frontend = Invoke-WebRequest -Uri "http://localhost:8080" -UseBasicParsing -ErrorAction SilentlyContinue
Write-Host "Frontend: $($frontend.StatusCode)"
```

---

## Additional Resources

- **React Frontend**: `apex-hmi/`
- **Flask Backend**: `app.py`, `wsgi.py`
- **Nginx Config**: `nginx-1.28.0\conf\nginx.conf`
- **Environment Config**: `.env`
- **Production Guide**: `REACT_FLASK_PRODUCTION_GUIDE.md`

---

## Summary

| Command | Action |
|---------|--------|
| `start_all_services.bat` | Start all services |
| `stop_all_services.bat` | Stop all services |
| `restart_all_services.bat` | Restart all services |
| `status_all_services.bat` | Check status |
| Navigate to http://localhost:8080 | Access HMI (HTTP) |
| Navigate to https://localhost:8443 | Access HMI (HTTPS) |

**That's it! Your HMI system is ready to use.** 🚀
