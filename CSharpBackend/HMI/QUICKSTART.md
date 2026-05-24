# 🚀 QUICK START GUIDE

## ✅ HMI Works in 3 Modes

| Mode | C# Backend | Database | Features |
|------|-----------|----------|----------|
| **FULL** | ✅ Running | ✅ Connected | Live + Historical data |
| **HISTORICAL** | ❌ Not running | ✅ Connected | Historical trends only |
| **DEMO** | ❌ Not running | ❌ Not connected | UI exploration |

**You can start HMI immediately without any prerequisites!**

---

## Prerequisites (Optional)

### For Live Data (Optional):
- C# Backend (OpcDaWebBrowser.exe) running on port 5000

### For Historical Trends (Optional):
- PostgreSQL with historian_raw.historian_timeseries table

## Installation (One Time)

```bash
cd HMI
pip install -r requirements.txt
```

## Start HMI Dashboard

### Option 1: Batch File (Recommended)
```bash
START_HMI.bat
```

### Option 2: Manual
```bash
python app.py
```

## Access Dashboard

Open browser: **http://localhost:5002**

### What You'll See:

**Connection Status Indicators:**
- 🟢 **GREEN** = Connected
- 🔴 **RED** = Not connected (HMI still works!)

**Mode Banner:**
- Shows current mode (FULL / HISTORICAL / DEMO)
- Explains available features

---

## Usage by Mode

### DEMO MODE (No connections)
- ✅ Explore UI
- ✅ Test controls
- ✅ Save/load dashboard layouts
- ❌ No live data
- ❌ No historical data

### HISTORICAL MODE (Database only)
- ✅ All DEMO features
- ✅ Query historical trends
- ✅ View past data
- ✅ Statistical analysis
- ❌ No live updates

### FULL MODE (Both connected)
- ✅ All features enabled
- ✅ Live streaming data
- ✅ Historical trends
- ✅ Real-time charts
- ✅ Complete functionality
   - Click **"+ Chart"** button next to any tag
   - Chart should appear on the right panel
   - Watch it update in real-time

4. **Load Historical Data**
   - Switch Chart Mode to "Historical"
   - Select time range (1h, 6h, 24h, 7d)
   - Click "Load Historical"
   - Historical trend should overlay

5. **Save Dashboard**
   - Click "💾 Save Dashboard"
   - Refresh page - layout should restore

## Enabling Full Mode

### To Enable Live Data:

1. **Start C# Backend:**
   ```bash
   cd ..
   dotnet run
   # OR
   bin\Release\net8.0\win-x86\OpcDaWebBrowser.exe
   ```

2. **Connect to OPC Server:**
   - Open `http://localhost:5000`
   - Go to "Server Browser"
   - Connect to OPC server

3. **Refresh HMI Dashboard:**
   - Status should turn GREEN
   - Live data appears automatically

### To Enable Historical Data:

1. **Update database credentials** in `config.json`:
   ```json
   {
     "database": {
       "host": "localhost",
       "port": 5432,
       "database": "historian",
       "user": "postgres",
       "password": "your_password"
     }
   }
   ```

2. **Restart HMI:**
   ```bash
   # Press Ctrl+C to stop
   python app.py
   ```

---

## Quick Test (Any Mode)

1. **Create Chart**
**Fix:** Install dependencies
```bash
pip install -r requirements.txt
```

## Troubleshooting

### Problem: Import Errors

Edit `config.json` before starting:

```json
{
  "csharp_backend": {
    "host": "localhost",      ← C# backend host
    "port": 5000,             ← C# backend port
    "signalr_hub": "/opcHub"  ← SignalR endpoint
  },
  "hmi_server": {
    "host": "0.0.0.0",        ← HMI host (0.0.0.0 = all interfaces)
    "port": 5002,             ← HMI port
    "debug": true             ← Debug mode (false for production)
  }
}
```

## Verification

Run pre-flight check:
```bash
python test_setup.py
```

**HMI starts regardless of check results!**

Expected modes:
```
❌ C# Backend      FAIL  → HISTORICAL or DEMO mode
❌ Database        FAIL  → DEMO mode only
✅ C# + Database   PASS  → FULL mode
```

---

## Key Points

✅ **HMI always starts** - no dependencies required
✅ **Graceful degradation** - works in any mode
✅ **Add connections later** - upgrade from DEMO → HISTORICAL → FULL
✅ **Independent operation** - doesn't require OpcDaWebBrowser.exe

---

## Configuration

| Service | Port | URL |
|---------|------|-----|
| C# Backend | 5000 | http://localhost:5000 |
| HMI Dashboard | 5002 | http://localhost:5002 |
| PostgreSQL | 5432 | (internal) |

## Default Credentials

Database (update in config.json):
- **User:** postgres
- **Password:** your_password
- **Database:** historian

## Stop Services

Press `Ctrl+C` in terminal running Python

## Full Documentation

See `README.md` for complete documentation

---

**Need help?** Check `IMPLEMENTATION_SUMMARY.md` for architecture details.
