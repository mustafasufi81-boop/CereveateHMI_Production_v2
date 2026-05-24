# Quick Start Testing Guide - HMI Flask Production Setup

## ⚡ Test Production Setup Locally (Windows)

Follow these steps to test the production deployment on your local Windows machine **before** installing as a service.

---

## Step 1: Install Production Dependencies

Open PowerShell or Command Prompt in the HMI directory:

```cmd
cd C:\Shakil\DJangoProjects\NEW_HMI\HMI
```

Run the deployment script:

```cmd
deploy_windows.bat
```

**What this does:**
- Creates Python virtual environment
- Installs Waitress and all production dependencies
- Creates `.env` file from template
- Validates configuration

**Action Required:** When prompted, edit the `.env` file. For local testing, you can leave defaults, but **update database credentials**:

```env
HMI_ENV=production
DEBUG=False
SECRET_KEY=test-secret-key
DB_HOST=localhost
DB_PORT=5432
DB_NAME=Cereveate
DB_USER=postgres
DB_PASSWORD=cereveate@222  # ← Update this!
```

---

## Step 2: Test Production Server

The deployment script will automatically start the Waitress server. You should see:

```
============================================================================
Server will start on: http://0.0.0.0:6001
Press CTRL+C to stop the server
============================================================================
```

**Test the application:**
1. Open browser: http://localhost:6001
2. Try logging in
3. Check real-time data updates
4. Monitor WebSocket connections

**Verify logs:** Open new terminal and check logs:
```cmd
type logs\hmi_app.log
```

---

## Step 3: Performance Comparison

### Test Development Server (For Comparison)

Open a new terminal:
```cmd
start_dev.bat
```

This starts Flask's development server on the same port.

**Compare:**
- ✅ **Development**: Good for coding, hot-reload, debugging
- ✅ **Production (Waitress)**: Better performance, thread-safe, production-ready

---

## Step 4: Test Environment Configuration

Test different environments:

**Development Mode:**
```cmd
set HMI_ENV=development
set DEBUG=True
python app.py
```

**Production Mode with Waitress:**
```cmd
set HMI_ENV=production
set DEBUG=False
waitress-serve --host=0.0.0.0 --port=6001 --threads=6 wsgi:application
```

**Production Mode with Manual Python:**
```cmd
python wsgi.py
```

---

## Step 5: Verify All Components

### 5.1 Database Connection
```cmd
python -c "from container import container; container.db_pool.test_connection(); print('✅ Database OK')"
```

### 5.2 Configuration Validation
```cmd
python config_manager.py
```

Expected output:
```
✅ Configuration loaded successfully!
📋 Environment: production
🌐 Server: 0.0.0.0:6001
🗄️  Database: localhost:5432/Cereveate
```

### 5.3 WSGI Application
```cmd
python wsgi.py
```

Should start server on port 6001.

---

## Step 6: Load Testing (Optional)

Install Apache Bench or use curl:

```cmd
# Simple availability test
curl http://localhost:6001/api/system/health

# Expected response:
# {"status":"healthy","uptime":123,"version":"1.0.0"}
```

For stress testing:
```cmd
# Install Apache Bench (ab) first
# Windows: Download from https://www.apachelounge.com/download/

ab -n 1000 -c 10 http://localhost:6001/api/system/health
```

---

## Step 7: Check Logs

**Application logs:**
```cmd
# Latest log entries
type logs\hmi_app.log | more

# Errors only
type logs\hmi_errors.log

# Daily log
type logs\hmi_daily.log
```

**Watch logs in real-time (PowerShell):**
```powershell
Get-Content logs\hmi_app.log -Wait -Tail 50
```

---

## Step 8: Test WebSocket Connections

### Browser Console Test:
1. Open browser to http://localhost:6001
2. Open Developer Tools (F12)
3. Go to Console tab
4. Run:
```javascript
// Check if Socket.IO is connected
if (typeof socket !== 'undefined') {
    console.log('Socket.IO Status:', socket.connected);
} else {
    console.log('Socket.IO not initialized');
}
```

### Python WebSocket Test:
```python
# test_websocket.py
import socketio

sio = socketio.Client()

@sio.event
def connect():
    print('✅ Connected to WebSocket')

@sio.event
def disconnect():
    print('❌ Disconnected from WebSocket')

@sio.on('live_data')
def on_live_data(data):
    print(f'📊 Received data: {data}')

sio.connect('http://localhost:6001')
sio.wait()
```

Run:
```cmd
pip install python-socketio[client]
python test_websocket.py
```

---

## Step 9: SQL Database Check

Verify database is accessible:

```cmd
python check_db.py
```

Or manually with psql:
```cmd
psql -U postgres -d Cereveate -c "SELECT COUNT(*) FROM tag_master;"
```

---

## Step 10: Security Validation

### Check 1: Debug Mode is OFF
```cmd
curl http://localhost:6001/api/system/health
# Should NOT show detailed error traces
```

### Check 2: Secret Key is Changed
```cmd
# Edit .env and ensure:
# SECRET_KEY is NOT "dev-secret-key-change-in-production"
```

### Check 3: CORS Configuration
```cmd
# Edit .env:
# CORS_ORIGINS=http://localhost:3000,https://yourdomain.com
```

---

## ✅ Success Checklist

Before proceeding to Windows Service installation:

- [ ] ✅ Waitress server starts without errors
- [ ] ✅ Can access http://localhost:6001 in browser
- [ ] ✅ Login works correctly
- [ ] ✅ Database connection successful
- [ ] ✅ MQTT client connects (if configured)
- [ ] ✅ WebSocket connections work
- [ ] ✅ Real-time data updates display
- [ ] ✅ Logs are written to logs/ directory
- [ ] ✅ No critical errors in logs
- [ ] ✅ Configuration validation passes
- [ ] ✅ DEBUG=False in .env

---

## 🚀 Next Steps

Once all tests pass:

### Option A: Continue Manual Testing
```cmd
deploy_windows.bat
```
Keep running for extended testing.

### Option B: Install as Windows Service
```cmd
install_service_windows.bat
```
Requires Administrator privileges.

### Option C: Set Up nginx Reverse Proxy
See `PRODUCTION_DEPLOYMENT_GUIDE.md` section on nginx setup.

---

## 🔧 Troubleshooting

### Issue: Port 6001 Already in Use
```cmd
# Find what's using the port
netstat -ano | findstr :6001

# Kill the process (replace PID)
taskkill /F /PID <PID>
```

### Issue: Database Connection Failed
```cmd
# Check PostgreSQL is running
sc query postgresql-x64-14  # Adjust version

# Start PostgreSQL
net start postgresql-x64-14

# Test connection
psql -U postgres -d Cereveate
```

### Issue: Import Errors
```cmd
# Reinstall dependencies
venv\Scripts\activate
pip install -r requirements-production.txt --force-reinstall
```

### Issue: .env File Not Found
```cmd
copy .env.example .env
notepad .env
```

### Issue: Logs Show Errors
```cmd
# Check latest errors
type logs\hmi_errors.log

# Common fixes:
# 1. Database credentials wrong → Edit .env
# 2. MQTT broker down → Check MQTT_BROKER_HOST in .env
# 3. Missing modules → Reinstall requirements
```

---

## 📊 Performance Benchmarks

Expected performance on typical hardware:

| Metric                  | Development | Production (Waitress) |
|-------------------------|-------------|----------------------|
| Concurrent Connections  | ~100        | ~1000+               |
| Requests/sec            | ~50         | ~500+                |
| Memory Usage            | ~150 MB     | ~200 MB              |
| WebSocket Latency       | <50ms       | <20ms                |
| CPU Usage (idle)        | 5-10%       | 2-5%                 |

---

## 📞 Need Help?

1. Check logs in `logs/` directory
2. Review error messages carefully
3. Consult `PRODUCTION_DEPLOYMENT_GUIDE.md`
4. Verify all prerequisites are installed

---

**Happy Testing! 🎉**
