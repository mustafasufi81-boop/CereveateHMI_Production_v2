# 🌐 PLC Scanner - Web Interface

Web-based real-time PLC data acquisition dashboard with modern UI and live statistics.

## ✨ Features

- **🎨 Modern Web Dashboard** - Beautiful, responsive interface accessible from any browser
- **⚡ Real-Time Updates** - WebSocket-based live tag values and statistics
- **📊 Live Statistics** - PLC reads, DB writes, cache stats, efficiency metrics
- **💾 Smart Caching** - Same optimized logic as desktop version (90% reduction)
- **🔄 Change Detection** - Only writes changed values to database
- **⏰ Forced Writes** - Maintains data continuity every 2 minutes
- **🚨 Emergency Cleanup** - Prevents crashes if database fails
- **📱 Mobile Friendly** - Works on desktop, tablet, and mobile devices

## 🚀 Quick Start

### 1. Install Dependencies

```bash
cd PLC_Scanner_Web
pip install -r requirements.txt
```

### 2. Configure Settings

Edit `plc_scanner_web.py` and update these variables:

```python
# PLC Configuration
PLC_IP = "192.168.0.20"
PLC_SLOT = 0
SCAN_INTERVAL_MS = 1000

# Database Configuration
DB_CONFIG = {
    'host': '192.168.0.120',
    'port': 5432,
    'database': 'Cereveate',
    'user': 'cereveate',
    'password': 'Admin@123'
}

# Web Server Configuration
WEB_PORT = 5100
```

### 3. Start the Server

**Windows:**
```bash
START_WEB_SCANNER.bat
```

**Or manually:**
```bash
python plc_scanner_web.py
```

### 4. Access Dashboard

Open your browser and navigate to:
```
http://localhost:5100
```

Or from another computer on the network:
```
http://YOUR_SERVER_IP:5100
```

## 📊 Dashboard Sections

### Status Bar
- **PLC Connection** - Real-time connection status with indicator
- **Database** - Database connection status
- **Tags Monitored** - Total number of active tags
- **Cache Size** - Current number of cached values

### Statistics Cards

**⚡ PLC Statistics:**
- Total Reads
- Errors
- Scan Interval
- Last Scan Time

**💾 Database Statistics:**
- Total Writes
- Errors
- Forced Writes (2-minute interval)
- Last Write Time

**📦 Cache Statistics:**
- Values Cached (changed values only)
- Values Filtered (unchanged, not cached)
- Auto Cleanups (per-tag limit reached)
- Emergency Cleanups (50K threshold)

**📊 Efficiency Metrics:**
- Filter Rate (% of values filtered)
- Cache Usage (% of 50K limit)
- PLC Success Rate
- DB Success Rate

### Live Tag Values
- Grid display of all monitored tags
- Real-time value updates with pulse animation
- Timestamp showing last update
- Auto-scrolling for large tag lists

### Controls
- **Scan Interval** - Adjust PLC polling rate (100-10000ms)
- **Refresh Now** - Force immediate update
- **Clear Statistics** - Reset display (reloads page)

## 🏗️ Architecture

```
┌─────────────────────┐
│  Web Browser        │
│  (Any Device)       │
└──────────┬──────────┘
           │ WebSocket (Socket.IO)
           │ + REST API
┌──────────▼──────────┐
│  Flask Web Server   │
│  (Port 5100)        │
└──────────┬──────────┘
           │
     ┌─────┴─────┐
     │           │
┌────▼────┐ ┌───▼────┐
│ PLC     │ │ DB     │
│ Scanner │ │ Writer │
│ Thread  │ │ Thread │
└────┬────┘ └───┬────┘
     │          │
┌────▼────┐ ┌──▼─────┐
│   PLC   │ │ Postgres│
│ 192...20│ │ DB      │
└─────────┘ └─────────┘
```

### Components

1. **Flask Web Server**
   - Serves HTML dashboard
   - WebSocket server (Socket.IO)
   - REST API endpoints
   - Runs on port 5100

2. **PLC Scanner Thread**
   - Connects to Allen-Bradley PLC via pycomm3
   - Reads tags at configured interval
   - PLC-level change detection
   - Updates shared cache
   - Emits real-time updates via WebSocket

3. **DB Writer Thread**
   - Checks cache every 1 second
   - Applies smart filtering (skip unchanged values)
   - Per-tag forced write every 2 minutes
   - Emergency cleanup if cache > 50K
   - Writes to PostgreSQL/TimescaleDB

4. **Tag Cache**
   - Thread-safe in-memory storage
   - Deque-based per-tag queues
   - Automatic cleanup at 10K values per tag
   - Emergency cleanup at 50K total values
   - Real-time statistics tracking

## 🔧 Configuration

### Scan Interval
Change scan rate from the web interface or edit `SCAN_INTERVAL_MS` in code:
- **Fast**: 100-500ms (high-speed monitoring)
- **Normal**: 1000ms (default, balanced)
- **Slow**: 2000-5000ms (low bandwidth)

### Cache Limits
Edit in `plc_scanner_web.py`:
```python
MAX_CACHE_SIZE = 10000        # Per-tag limit
MAX_TOTAL_VALUES = 50000      # Emergency threshold
FORCED_WRITE_INTERVAL = 120.0 # 2 minutes
DB_WRITE_INTERVAL = 1.0       # 1 second
```

### Tag Configuration
Tags are loaded from database table `historian_meta.tag_master`:
```sql
SELECT tag_id 
FROM historian_meta.tag_master 
WHERE enabled = true
```

Add tags via:
```sql
INSERT INTO historian_meta.tag_master 
(tag_id, tag_name, data_type, enabled)
VALUES ('PLC_TAG_NAME', 'Display Name', 'double', true);
```

## 📡 API Endpoints

### REST API

**Get Statistics:**
```
GET /api/stats
```
Returns current system statistics (JSON)

**Get Tag Values:**
```
GET /api/values
```
Returns latest value for each tag (JSON)

**Set Scan Interval:**
```
POST /api/scan_interval
Content-Type: application/json

{
  "interval_ms": 1000
}
```

### WebSocket Events

**Client → Server:**
- `connect` - Client connected
- `disconnect` - Client disconnected
- `request_stats` - Request statistics update
- `request_values` - Request tag values update

**Server → Client:**
- `stats_update` - Statistics data broadcast
- `values_update` - Tag values data broadcast

## 🔒 Security

For production deployment:

1. **Change Secret Key:**
```python
app.config['SECRET_KEY'] = 'your-secure-random-key-here'
```

2. **Add Authentication:**
Consider adding Flask-Login or JWT tokens

3. **HTTPS:**
Use reverse proxy (nginx) with SSL/TLS

4. **Firewall:**
Restrict port 5100 to trusted networks

## 🐧 Linux Deployment

### SystemD Service

Create `/etc/systemd/system/plc-scanner-web.service`:
```ini
[Unit]
Description=PLC Scanner Web Interface
After=network.target

[Service]
Type=simple
User=plcuser
WorkingDirectory=/opt/plc_scanner_web
ExecStart=/usr/bin/python3 plc_scanner_web.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable plc-scanner-web
sudo systemctl start plc-scanner-web
sudo systemctl status plc-scanner-web
```

## 📊 Performance

### Expected Performance (50 tags @ 1000ms scan):
- **Cache Size**: 500-1000 values (with change detection)
- **Memory Usage**: ~100-200 MB
- **CPU Usage**: < 5%
- **Network**: ~10-20 KB/s WebSocket traffic
- **DB Writes**: 50-500 records/minute (depends on change rate)

### Scalability:
- **100 tags**: No issues
- **500 tags**: Recommended increase scan interval to 2000ms
- **1000+ tags**: Consider multiple scanner instances

## 🆚 Comparison with Desktop Version

| Feature | Desktop (Tkinter) | Web Interface |
|---------|-------------------|---------------|
| Interface | GUI window | Browser-based |
| Access | Local only | Network-wide |
| Multi-user | No | Yes |
| Mobile Support | No | Yes |
| Resource Usage | Lower | Slightly higher |
| Setup | Simpler | Requires web server |
| Core Logic | ✅ Same | ✅ Same |

**Same Performance:** Both use identical PLC scanning, caching, and database logic.

## 🐛 Troubleshooting

### Port Already in Use
Change `WEB_PORT` in `plc_scanner_web.py` or:
```bash
# Windows
netstat -ano | findstr :5100
taskkill /F /PID <PID>

# Linux
sudo lsof -i :5100
kill <PID>
```

### PLC Connection Failed
- Verify PLC IP and slot number
- Check network connectivity
- Ensure PLC is powered on
- Verify tag names in database

### Database Connection Failed
- Check PostgreSQL is running
- Verify connection credentials
- Check firewall allows port 5432
- Ensure database schema exists

### WebSocket Not Connecting
- Check browser console for errors
- Verify CORS settings
- Clear browser cache
- Try different browser

### High Memory Usage
- Reduce `MAX_CACHE_SIZE`
- Increase `DB_WRITE_INTERVAL` frequency
- Check for database connection issues
- Monitor `cache_emergency` count

## 📝 Logs

View logs in terminal or redirect to file:
```bash
python plc_scanner_web.py > scanner.log 2>&1
```

## 📄 License

Same as main project

## 🤝 Support

For issues or questions, check main project documentation or contact system administrator.

---

**Created:** February 2026  
**Version:** 1.0  
**Compatible with:** plc_scanner_enhanced.py logic
