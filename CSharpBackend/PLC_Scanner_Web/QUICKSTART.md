# 🚀 QUICK START - PLC Scanner Web Interface

## 📁 What You Have

```
PLC_Scanner_Web/
├── plc_scanner_web.py          # Main web server (Flask + SocketIO)
├── templates/
│   └── dashboard.html          # Web dashboard UI
├── requirements.txt            # Python dependencies
├── START_WEB_SCANNER.bat      # Windows startup script
└── README.md                   # Full documentation
```

## ⚡ 3-Minute Setup

### Step 1: Install Dependencies
```bash
cd PLC_Scanner_Web
pip install -r requirements.txt
```

### Step 2: Configure (Edit plc_scanner_web.py)
```python
PLC_IP = "192.168.0.20"          # YOUR PLC IP
PLC_SLOT = 0                     # YOUR PLC SLOT

DB_CONFIG = {
    'host': '192.168.0.120',     # YOUR DB SERVER
    'port': 5432,
    'database': 'Cereveate',
    'user': 'cereveate',
    'password': 'Admin@123'
}
```

### Step 3: Start
```bash
# Windows:
START_WEB_SCANNER.bat

# Or:
python plc_scanner_web.py
```

### Step 4: Open Browser
```
http://localhost:5100
```

## ✅ Features

✨ **Real-Time Dashboard** - Live tag values with WebSocket updates
📊 **Statistics** - PLC reads, DB writes, cache stats, efficiency metrics
🎨 **Modern UI** - Beautiful gradient design, responsive layout
📱 **Mobile Friendly** - Works on any device
⚡ **Same Performance** - Identical logic to desktop version:
  - 90% cache reduction (only changed values)
  - Per-tag forced write (2 minutes)
  - Emergency cleanup (50K threshold)
  - Thread-safe operations

## 🎯 Key Differences from Desktop Version

| Feature | Desktop (plc_scanner_enhanced.py) | Web (plc_scanner_web.py) |
|---------|-----------------------------------|--------------------------|
| **Interface** | Tkinter GUI window | Browser dashboard |
| **Access** | Local computer only | Any device on network |
| **Multi-user** | Single user | Multiple browsers |
| **Core Logic** | ✅ Same PLC/DB/Cache code | ✅ Same PLC/DB/Cache code |

## 🔧 Configuration Options

### Change Scan Interval (from web UI or code)
```python
SCAN_INTERVAL_MS = 1000  # milliseconds
```

### Change Web Port
```python
WEB_PORT = 5100
```

### Cache Limits
```python
MAX_CACHE_SIZE = 10000        # Per-tag limit
MAX_TOTAL_VALUES = 50000      # Emergency cleanup
FORCED_WRITE_INTERVAL = 120.0 # Force write (seconds)
```

## 📊 What You'll See

### Dashboard Sections:
1. **Status Bar** - PLC/DB connection, tag count, cache size
2. **PLC Statistics** - Reads, errors, scan interval, last scan
3. **Database Statistics** - Writes, errors, forced writes
4. **Cache Statistics** - Values cached/filtered, cleanups
5. **Efficiency Metrics** - Filter rate, cache usage, success rates
6. **Live Tag Values** - Real-time grid of all tags with animations
7. **Controls** - Adjust scan interval, refresh, clear stats

## 🌐 Network Access

**Local:**
```
http://localhost:5100
```

**From other computers:**
```
http://192.168.0.X:5100
```
(Replace X with your server's IP)

**Mobile/Tablet:**
Same URL as above - interface auto-adjusts!

## 🐛 Common Issues

### "Port 5100 already in use"
Change `WEB_PORT` in code or kill existing process:
```bash
# Windows:
netstat -ano | findstr :5100
taskkill /F /PID <PID>
```

### "Cannot connect to PLC"
- Check `PLC_IP` is correct
- Verify PLC is powered on
- Test network: `ping 192.168.0.20`

### "Database connection failed"
- Check PostgreSQL is running
- Verify `DB_CONFIG` credentials
- Ensure database `Cereveate` exists

### "No tags showing"
Tags must be in database:
```sql
INSERT INTO historian_meta.tag_master 
(tag_id, tag_name, data_type, enabled)
VALUES ('Program:MainProgram.GENERATOR_LOAD_MW', 'Generator Load', 'double', true);
```

## 💡 Tips

1. **Multi-Monitor Setup**: Open dashboard on second screen
2. **Mobile Monitoring**: Access from phone/tablet anywhere on network
3. **Team Access**: Share URL with team members
4. **Development**: Keep terminal open to see server logs
5. **Production**: Run as Windows service or Linux SystemD

## 📝 Next Steps

1. ✅ Start the server
2. ✅ Open browser dashboard
3. ✅ Verify PLC connection (green indicator)
4. ✅ Check tags are loading
5. ✅ Monitor cache statistics
6. ✅ Adjust scan interval if needed

## 🆘 Need Help?

- Full docs: See `README.md`
- Main project: See parent directory
- Compare with: `plc_scanner_enhanced.py` (desktop version)

---

**You're ready to go! 🚀**

Run `START_WEB_SCANNER.bat` and open `http://localhost:5100`
