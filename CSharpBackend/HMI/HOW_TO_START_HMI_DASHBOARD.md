# 🚀 HOW TO START HMI DASHBOARD - WORKING SOLUTION

## ✅ CONFIRMED WORKING METHOD

### **Prerequisites Fixed:**
1. **Python Dependencies**: Install with `pip install -r requirements.txt`
2. **SocketIO Configuration**: Changed from `eventlet` to `threading` mode
3. **Port Configuration**: Use port 5003 (5002 has permission issues)

---

## 📋 **Step-by-Step Instructions**

### **Step 1: Navigate to HMI Directory**
```bash
cd "d:\Development\MQTT_Implemented_OPC\BACKUP_BEFORE_HISTORICAL_20251117_225747 - Copy_backup_20251206\HMI"
```

### **Step 2: Install Dependencies (One Time)**
```bash
pip install -r requirements.txt
```

### **Step 3: Start the HMI Application**
```bash
python app.py
```

### **Step 4: Access the Dashboard**
Open your browser and go to:
- **Local Access**: http://localhost:5003
- **Network Access**: http://192.168.1.41:5003

---

## 🔧 **Configuration Changes Made**

### **1. Fixed SocketIO Mode** (in `app.py`)
```python
# BEFORE (problematic):
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# AFTER (working):  
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')
```

### **2. Removed Eventlet Monkey Patch** (in `app.py`)
```python
# REMOVED these lines:
# import eventlet
# eventlet.monkey_patch()
```

### **3. Changed Port** (in `config.json`)
```json
{
  "hmi_server": {
    "host": "0.0.0.0",
    "port": 5003,
    "debug": false
  }
}
```

---

## 📊 **Expected Startup Output**

When working correctly, you should see:
```
Server initialized for threading.
🚀 HMI Application Starting...
📍 HMI Dashboard: http://0.0.0.0:5003
✅ Connected to PostgreSQL: Cereveate
✅ Tag cache started (background refresh every 30s)
✅ HMI Mode: HISTORICAL ONLY
✅ Services initialized successfully!
🚀 Starting Flask-SocketIO server...
 * Running on http://127.0.0.1:5003
 * Running on http://192.168.1.41:5003
✅ Loaded 68 mapped tags from database
```

---

## 🎯 **Operating Modes**

| Mode | Status | Features Available |
|------|--------|-------------------|
| **DEMO** | ❌ C# Backend, ❌ Database | UI exploration only |
| **HISTORICAL** | ❌ C# Backend, ✅ Database | Historical trends |
| **FULL** | ✅ C# Backend, ✅ Database | Live + Historical data |

**Current Mode**: HISTORICAL ONLY (database connected, no C# backend)

---

## 🛠️ **Troubleshooting**

### **Problem: Socket Permission Error**
```
An attempt was made to access a socket in a way forbidden by its access permissions
```
**Solution**: Change port in `config.json` to 5003 or another available port

### **Problem: Import Errors**
**Solution**: Install dependencies: `pip install -r requirements.txt`

### **Problem: Database Connection Failed**
**Solution**: Check PostgreSQL is running and credentials in `config.json`

### **Problem: No Live Data**
**Solution**: Start C# backend: `dotnet run --project OpcDaWebBrowser.csproj`

---

## 📁 **Key Files**

| File | Purpose |
|------|---------|
| `app.py` | Main Flask application (START THIS) |
| `config.json` | Configuration (ports, database, etc.) |
| `templates/dashboard.html` | Main dashboard UI |
| `static/js/dashboard.js` | Frontend JavaScript |
| `static/css/dashboard.css` | Styling |
| `services/` | Backend services (database, cache) |

---

## ✅ **Success Indicators**

1. **Server Running**: See "Running on http://127.0.0.1:5003"
2. **Database Connected**: See "Connected to PostgreSQL: Cereveate"  
3. **Tags Loaded**: See "Loaded X mapped tags from database"
4. **Web Access**: Dashboard loads at http://localhost:5003

---

## 🎮 **Next Steps**

1. **Access Dashboard**: http://localhost:5003
2. **View Historical Trends**: Select tags and time ranges
3. **Enable Live Data**: Start C# backend for real-time updates
4. **Save Dashboards**: Create custom layouts

---

**✅ CONFIRMED WORKING: February 3, 2026**

The HMI Dashboard is now fully operational with historical trend capability!