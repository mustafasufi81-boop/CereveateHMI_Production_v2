# 🚀 QUICK START GUIDE - ALL APPLICATIONS

## ✅ TWO RUNNING APPLICATIONS

| Application | Purpose | Port | Status |
|-------------|---------|------|--------|
| **HMI Dashboard** | Real-time + Historical OPC Data | **5003** | ✅ RUNNING |
| **HistoricalTrends BI** | Advanced Analytics & BI | **6004** | ✅ RUNNING |

---

## 🏭 HMI DASHBOARD (Port 5003)

### **Purpose:** 
Real-time OPC data monitoring with historical trend capability

### **Quick Start:**
```bash
# Navigate to HMI folder
cd "d:\Development\MQTT_Implemented_OPC\BACKUP_BEFORE_HISTORICAL_20251117_225747 - Copy_backup_20251206\HMI"

# Install dependencies (one time)
pip install -r requirements.txt

# Start application
python app.py
```

### **Access URLs:**
- **Local**: http://localhost:5003
- **Network**: http://192.168.1.41:5003

### **Features:**
- ✅ Real-time OPC tag monitoring
- ✅ Historical trend queries
- ✅ Interactive dashboards
- ✅ Save/load layouts
- ✅ PostgreSQL integration (68 tags loaded)

### **Current Mode:** HISTORICAL ONLY (database connected, no C# backend)

---

## 📊 HISTORICALTRENDS BI (Port 6004)

### **Purpose:** 
Advanced Business Intelligence and Analytics for historical data

### **Quick Start:**
```bash
# Navigate to HistoricalTrends folder  
cd "d:\Development\MQTT_Implemented_OPC\BACKUP_BEFORE_HISTORICAL_20251117_225747 - Copy_backup_20251206\HistoricalTrends"

# Start application (no additional dependencies needed)
python app.py
```

### **Access URLs:**
- **Local**: http://localhost:6004
- **Network**: http://192.168.1.41:6004

### **Features:**
- ✅ Advanced BI Analytics
- ✅ Data interpolation and gap filling
- ✅ Statistical analysis (boxplots, distributions)
- ✅ Predictive modeling
- ✅ Export to CSV/Excel
- ✅ Parquet file processing (21 tags loaded)

### **Data Sources:**
- **Directory**: D:\OpcLogs\Data (parquet files)
- **Backup**: D:\OpcLogs\Backup
- **Derived Data**: D:/OpcLogs/DerivedData

---

## 🔧 CONFIGURATION FILES

### **HMI Dashboard Config** (`HMI/config.json`)
```json
{
  "hmi_server": {
    "host": "0.0.0.0",
    "port": 5003,
    "debug": false
  },
  "database": {
    "host": "localhost", 
    "port": 5432,
    "database": "Cereveate",
    "user": "cereveate",
    "password": "cereveate@222"
  }
}
```

### **HistoricalTrends Config** (hardcoded in app.py)
```python
# Port: 6004
# Host: 0.0.0.0
# Data Directory: D:\OpcLogs\Data
```

---

## 📋 STARTUP CHECKLIST

### **For HMI Dashboard:**
1. ✅ Python dependencies installed
2. ✅ PostgreSQL database connected
3. ✅ Port 5003 available
4. ✅ SocketIO threading mode enabled
5. ✅ 68 mapped tags loaded

### **For HistoricalTrends BI:**
1. ✅ Data directory exists (D:\OpcLogs\Data)
2. ✅ Parquet files available
3. ✅ Port 6004 available
4. ✅ 21 tags in cache
5. ✅ All BI modules loaded

---

## 🎯 USAGE SCENARIOS

### **Real-Time Monitoring** → **HMI Dashboard (Port 5003)**
- View live OPC tag values
- Monitor system status
- Create custom dashboards
- Query recent historical data

### **Advanced Analytics** → **HistoricalTrends BI (Port 6004)**  
- Deep historical analysis
- Statistical modeling
- Data quality assessment
- Predictive analytics
- Business intelligence reporting

---

## ⚡ PERFORMANCE STATUS

### **HMI Dashboard:**
- **Database**: Connected to PostgreSQL Cereveate
- **Tags**: 68 mapped tags from historian_meta.tag_master
- **Refresh**: Tag cache updates every 30 seconds
- **Mode**: HISTORICAL ONLY (C# backend not connected)

### **HistoricalTrends BI:**
- **Cache**: 21 tags loaded from parquet files
- **Files**: 1 parquet file in processing
- **Modules**: All advanced BI modules loaded successfully
- **Performance**: Prophet model disabled (optional)

---

## 🛠️ TROUBLESHOOTING

### **Port Issues:**
- **5003 blocked**: Change `hmi_server.port` in HMI/config.json
- **6004 blocked**: Change `port=6004` in HistoricalTrends/app.py

### **Database Issues:**
- **HMI no data**: Check PostgreSQL connection in config.json
- **BI no data**: Check D:\OpcLogs\Data directory for parquet files

### **Permission Issues:**
- **Socket errors**: Run as Administrator or change ports
- **File access**: Check D:\OpcLogs directory permissions

---

## 📈 SUCCESS INDICATORS

### **HMI Dashboard Running:**
```
✅ Connected to PostgreSQL: Cereveate
✅ Tag cache started (background refresh every 30s)
✅ HMI Mode: HISTORICAL ONLY  
✅ Services initialized successfully!
* Running on http://127.0.0.1:5003
✅ Loaded 68 mapped tags from database
```

### **HistoricalTrends BI Running:**
```
✓ Cache loaded: 21 tags, 1 files
✓ Loaded configuration from derived_analytics_config.json
* Running on http://127.0.0.1:6004
✓ All modules loaded successfully
```

---

## 🌐 ACCESS SUMMARY

| Service | URL | Purpose |
|---------|-----|---------|
| **HMI Dashboard** | http://localhost:5003 | Real-time monitoring |
| **HistoricalTrends BI** | http://localhost:6004 | Advanced analytics |

**Both applications are now fully operational! 🚀**

---

**✅ CONFIRMED WORKING: February 3, 2026 - 17:20**