# Linux Compatibility Guide - PLC Scanner

## ✅ Current Status: **FULLY LINUX COMPATIBLE**

Both `plc_scanner_enhanced.py` and `PLC_Scanner/professional_plc_scanner.py` are now cross-platform compatible.

---

## 🐧 Running on Linux

### **Prerequisites:**
```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install python3 python3-pip python3-tk

# RHEL/CentOS/Fedora
sudo yum install python3 python3-pip python3-tkinter

# Arch Linux
sudo pacman -S python python-pip tk
```

### **Install Python Dependencies:**
```bash
pip3 install pycomm3 psycopg2-binary
```

### **Run the Scanner:**
```bash
# Enhanced version
python3 plc_scanner_enhanced.py

# Professional UI version
cd PLC_Scanner
python3 professional_plc_scanner.py
```

---

## 🪟 Running on Windows

### **Prerequisites:**
- Python 3.8+ (includes tkinter)
- Install dependencies:
```cmd
pip install pycomm3 psycopg2-binary
```

### **Run the Scanner:**
```cmd
python plc_scanner_enhanced.py

REM Or use the launcher
cd PLC_Scanner
START_PLC_SCANNER.bat
```

---

## 🔧 Linux-Specific Configurations

### **1. DISPLAY Environment Variable**
The code automatically handles missing DISPLAY:
```python
if 'DISPLAY' not in os.environ:
    os.environ['DISPLAY'] = ':0'
```

### **2. Headless Mode (No GUI)**
If X11/display not available, runs in console mode:
```python
HEADLESS_MODE = True  # Auto-detected
# Logs go to console instead of GUI
```

### **3. File Permissions**
Ensure write permissions for logs:
```bash
chmod +x plc_scanner_enhanced.py
chmod 755 PLC_Scanner/
```

---

## 📊 Feature Parity

| Feature | Windows | Linux | Notes |
|---------|---------|-------|-------|
| **PLC Scanning** | ✅ | ✅ | pycomm3 works on both |
| **Database Writes** | ✅ | ✅ | PostgreSQL client |
| **GUI (Tkinter)** | ✅ | ✅ | Requires X11 on Linux |
| **Headless Mode** | ✅ | ✅ | Console logging |
| **Cache Management** | ✅ | ✅ | Thread-safe |
| **Emergency Cleanup** | ✅ | ✅ | Memory protection |
| **Change Detection** | ✅ | ✅ | PLC-level filtering |
| **Forced Writes** | ✅ | ✅ | 2-minute interval |

---

## 🚀 Running as Linux Service

### **SystemD Service File (`/etc/systemd/system/plc-scanner.service`):**
```ini
[Unit]
Description=PLC Tag Scanner Service
After=network.target postgresql.service

[Service]
Type=simple
User=cereveate
WorkingDirectory=/opt/plc_scanner
Environment="DISPLAY=:0"
ExecStart=/usr/bin/python3 /opt/plc_scanner/plc_scanner_enhanced.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### **Enable and Start:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable plc-scanner
sudo systemctl start plc-scanner
sudo systemctl status plc-scanner
```

---

## 🐋 Docker Support

### **Dockerfile:**
```dockerfile
FROM python:3.11-slim

# Install dependencies
RUN apt-get update && apt-get install -y \
    python3-tk \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages
RUN pip install --no-cache-dir pycomm3 psycopg2-binary

# Copy application
WORKDIR /app
COPY plc_scanner_enhanced.py .

# Run in headless mode
CMD ["python3", "plc_scanner_enhanced.py"]
```

### **Build and Run:**
```bash
docker build -t plc-scanner .
docker run -d --name plc-scanner \
  --network host \
  plc-scanner
```

---

## ✅ **SUMMARY:**

**The PLC Scanner is NOW:**
- ✅ Cross-platform (Windows/Linux)
- ✅ Auto-detects display availability
- ✅ Falls back to headless mode
- ✅ Fully functional on both OSes
- ✅ Service-ready for Linux
- ✅ Docker-compatible

**All logic improvements applied:**
- ✅ PLC-level change detection
- ✅ Emergency cache cleanup (50K threshold)
- ✅ Per-tag forced write (2-min)
- ✅ No duplicate key errors
- ✅ Memory-safe operation

**Ready for production deployment on Linux servers! 🎉**
