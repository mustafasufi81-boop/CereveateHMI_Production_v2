# 🏭 Professional PLC Scanner - Enterprise Edition

## Overview
Professional-grade industrial data acquisition system with an attractive modern UI, designed for real-time PLC monitoring and intelligent database logging.

## ✨ Key Features

### 🎨 **Modern Professional UI**
- Dark theme with gradient effects and modern color palette
- Real-time statistics dashboard with colored cards
- Live trend visualization with interactive sparklines
- Professional typography and spacing
- Intuitive controls and status indicators

### ⚡ **Smart Data Management**
- **Value Change Detection**: Only writes to database when values change
- **Forced Write Every 2 Minutes**: Maintains data continuity for constant values
- **Automatic Filtering**: Dramatically reduces database load
- **Thread-Safe Caching**: High-performance in-memory tag cache

### 📊 **Live Monitoring**
- Real-time tag value updates
- Interactive trend charts with hover tooltips
- PLC response time tracking
- Comprehensive statistics (Reads, Writes, Skipped, Errors)

### 💾 **Database Integration**
- PostgreSQL/TimescaleDB historian
- Dual table strategy: latest values + timeseries
- Batch writes every 1 second
- Automatic reconnection on failure

## 🚀 Quick Start

### Requirements
```bash
pip install pycomm3 psycopg2-binary tkinter
```

### Configuration
Edit the following constants in `professional_plc_scanner.py`:

```python
PLC_IP = "192.168.0.20"          # Your PLC IP address

DB_CONFIG = {
    'host': '192.168.0.120',      # Database server
    'port': 5432,
    'database': 'Cereveate',
    'user': 'cereveate',
    'password': 'cereveate@222'
}
```

### Run
```bash
python professional_plc_scanner.py
```

## 📈 How It Works

### Architecture
```
PLC (Allen-Bradley ControlLogix)
    ↓
Fast Scanner Thread (1ms - 2000ms configurable)
    ↓
Thread-Safe Cache (in-memory)
    ↓
Database Writer Thread (every 1 second)
    ↓
PostgreSQL TimescaleDB
```

### Smart Filtering Logic

**Example Timeline:**
```
Time 0:00  → Temperature = 25.5°C → ✓ WRITE (first time)
Time 0:01  → Temperature = 25.5°C → ✗ SKIP (unchanged)
Time 0:02  → Temperature = 25.5°C → ✗ SKIP (unchanged)
...
Time 1:59  → Temperature = 25.5°C → ✗ SKIP (unchanged)
Time 2:00  → Temperature = 25.5°C → ✓ WRITE (2 min forced!)
Time 2:01  → Temperature = 25.5°C → ✗ SKIP (unchanged)
Time 3:00  → Temperature = 26.1°C → ✓ WRITE (value changed!)
Time 3:01  → Temperature = 26.1°C → ✗ SKIP (unchanged)
Time 5:00  → Temperature = 26.1°C → ✓ WRITE (2 min forced!)
```

### Benefits
- ✅ **90% reduction in database writes** for stable processes
- ✅ **No data loss** - all changes captured immediately
- ✅ **Data continuity** - forced writes every 2 minutes
- ✅ **High-speed scanning** - up to 1ms scan rate
- ✅ **Low database load** - only meaningful data stored

## 🎨 UI Components

### Statistics Dashboard
- **Tags**: Total discovered tags
- **Selected**: Tags selected for trending
- **PLC Reads**: Total PLC read operations
- **DB Writes**: Database write operations
- **Skipped**: Filtered unchanged values (database savings!)
- **Errors**: Connection/read errors
- **Response**: PLC response time (ms)
- **Uptime**: System runtime

### Trend Viewer
- Interactive sparkline charts
- Hover for exact values and timestamps
- Auto-scaling for value ranges
- Constant value detection
- Multi-tag comparison

### Tag Table
- Live value updates
- Tag name, type, value, timestamp
- Quick search/filter
- Select/deselect for trending
- Professional monospace display

## ⚙ Configuration Options

### Scan Interval
Choose from: `1ms, 5ms, 10ms, 50ms, 100ms, 500ms, 1000ms, 2000ms`
- Fast scanning (1-10ms): For high-speed applications
- Medium (50-500ms): General purpose
- Slow (1000-2000ms): Low-priority monitoring

### Database Logging
Toggle ON/OFF via UI checkbox
- When OFF: Data still scanned but not saved to database
- When ON: Smart filtering + 2-minute forced writes active

### Forced Write Interval
Default: 120 seconds (2 minutes)
Edit in code:
```python
FORCED_WRITE_INTERVAL = 120.0  # seconds
```

## 📁 Database Schema

### historian_latest_value
Stores the most recent value for each tag:
- `tag_id` (PK)
- `last_time`
- `last_value_num`, `last_value_text`, `last_value_bool`
- `last_quality`
- `updated_at`

### historian_timeseries
Stores all historical samples (filtered):
- `time` (PK part)
- `tag_id` (PK part)
- `value_num`, `value_text`, `value_bool`
- `quality`
- `sample_source`
- `mapping_version`

## 🔧 Troubleshooting

### PLC Connection Issues
1. Check PLC IP address and network connectivity
2. Ensure PLC slot/path is correct (default: `/1,0`)
3. Verify firewall settings
4. Check PLC is online and accessible

### Database Issues
1. Verify PostgreSQL is running
2. Check network connectivity to database server
3. Confirm database credentials
4. Ensure schemas exist: `historian_raw`
5. Verify tables created: `historian_latest_value`, `historian_timeseries`

### Performance
- For 1ms scanning: Ensure adequate CPU resources
- Large tag counts: Consider increasing cache size
- High DB writes: Adjust forced write interval

## 📝 Logging
Console logs show:
- ⚡ PLC operations (connects, scans, response times)
- 💾 Database operations (writes, filtered counts)
- ❌ Errors with retry information
- ✓ System status updates

## 🎯 Best Practices

1. **Start with 1000ms scan rate** - adjust based on needs
2. **Monitor "Skipped" counter** - shows filtering effectiveness
3. **Select critical tags for trending** - don't overload UI
4. **Use forced writes for audit trails** - maintains data continuity
5. **Check response times** - should be < 100ms for good performance

## 📞 Support
Developed by: **Cereveate Tech | Shahnawaz Mustafa**
Version: **2.0 - Professional UI**

---

**Enjoy your professional PLC monitoring experience!** 🚀
