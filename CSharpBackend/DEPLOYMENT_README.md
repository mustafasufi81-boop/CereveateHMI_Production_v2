# Cereveate_Praxis OPC Server - Complete Setup Package

## 📦 Package Created Successfully!

**File:** `CereveateOPCServer_v1.0_Standalone.zip` (63.77 MB)  
**Created:** November 16, 2025  
**License Expiry:** March 16, 2026 (4 months)

---

## ✅ What's Included

### Main Application
- **OpcDaWebBrowser.exe** (87.3 MB)
  - Self-contained with .NET 8.0 runtime
  - Runs silently in background (no console window)
  - Web interface on http://localhost:5000

### License System
- **LicenseGenerator.exe** (59.89 MB)
  - Hardware-locked license generation
  - AES-256 encryption
  - Tamper-proof time tracking
  - **Pre-generated license.dat included**

### Installation Scripts
- **install-service.bat** - Install as Windows Service
- **launch-silent.bat** - Run as background process
- **logging-config.json** - Configuration file

### Documentation
- **INSTALLATION.txt** - Complete installation instructions

---

## 🔐 Security Features

### Hardware Binding
```
Hardware ID: BFEBFBFF000B06A2-R522NBCV00Y452MB-6C6E07115A78
```
- CPU ID: BFEBFBFF000B06A2
- Motherboard Serial: R522NBCV00Y452MB
- MAC Address: 6C6E07115A78

### Encryption
- **AES-256** with RFC2898 key derivation (10,000 iterations)
- **SHA-256** signature validation
- Independent time tracking (Environment.TickCount64)
- Backward clock detection

### License Expiry
- **Issued:** November 16, 2025
- **Expires:** March 16, 2026
- **Warning:** 7 days before expiry (logged to file, not shown to user)
- **No extension possible** - Hardware locked, tamper-proof

---

## 🚀 Installation Methods

### Method 1: Windows Service (Recommended)
```batch
1. Extract ZIP file
2. Right-click install-service.bat
3. Select "Run as Administrator"
4. Service starts automatically
5. Access: http://localhost:5000
```

**Service Details:**
- Name: `CereveateOPCServer`
- Display Name: `Cereveate_Praxis OPC Server`
- Auto-restart on failure (3 seconds delay)
- Starts automatically on system boot

### Method 2: Background Process
```batch
1. Extract ZIP file
2. Double-click launch-silent.bat
3. Runs silently (no window)
4. Access: http://localhost:5000
```

### Method 3: Direct Execution
```batch
1. Extract ZIP file
2. Double-click OpcDaWebBrowser.exe
3. Runs silently (no window)
4. Access: http://localhost:5000
```

---

## 📁 Distribution Contents

```
CereveateOPCServer_v1.0_Standalone.zip
├── OpcDaWebBrowser.exe          (87.3 MB - ALL DEPENDENCIES INCLUDED)
├── license.dat                  (Hardware-locked license - PRE-GENERATED)
├── wwwroot\                     (Web UI assets)
├── logging-config.json          (Configuration)
├── Logs\                        (Empty folder for logs)
├── LicenseGenerator\
│   ├── LicenseGenerator.exe     (59.89 MB - Standalone tool)
│   └── license.dat              (Generated license)
├── install-service.bat          (Windows Service installer)
├── launch-silent.bat            (Silent launcher)
└── INSTALLATION.txt             (Complete instructions)
```

---

## 🛠️ System Requirements

- **OS:** Windows 7/8/10/11 (32-bit or 64-bit)
- **Memory:** 2 GB RAM minimum
- **Disk:** 100 MB free space
- **.NET:** NO installation required (included)
- **Downloads:** NO additional downloads needed
- **Admin Rights:** Required for Windows Service installation only

---

## 📝 Logging & Monitoring

### Application Logs
- **Location:** `Logs\app-YYYYMMDD.log`
- **Format:** `YYYY-MM-DD HH:MM:SS.fff [Level] Message`
- **Rotation:** Daily at midnight
- **Levels:** Information, Warning, Error, Critical

### Data Logs
- **Location:** `Logs\OpcData_YYYYMMDD_HHMMSS.csv`
- **Format:** CSV (Timestamp, ItemId, Value, Quality, DataType)
- **Interval:** Every 5 seconds (configurable)
- **Rotation:** New file daily at midnight

---

## 🔧 Configuration

### logging-config.json
```json
{
  "DataLogging": {
    "Enabled": true,
    "IntervalSeconds": 5,
    "LogDirectory": "Logs",
    "FileNamePrefix": "OpcData"
  },
  "Serilog": {
    "MinimumLevel": "Information"
  }
}
```

---

## ⚠️ Important Notes

### DO NOT
- ❌ Copy license.dat to another machine (hardware-locked)
- ❌ Modify system clock to extend trial (tamper-proof)
- ❌ Delete .tdata file (time tracking)
- ❌ Edit license.dat file (signature validation)

### Silent Operation
- ✅ **NO console window** (WinExe output type)
- ✅ **NO startup messages** (file logging only)
- ✅ **NO error popups** (errors logged to file)
- ✅ **Completely invisible** background operation

### License Expiry
- Warning logged 7 days before expiry
- Application stops on expiry date
- No user-visible warnings (check logs)

---

## 📊 Build Information

### Build Configuration
- **Framework:** .NET 8.0
- **Runtime:** win-x86 (self-contained)
- **Output Type:** WinExe (no console)
- **Single File:** Yes (PublishSingleFile=true)
- **Build Date:** November 16, 2025

### Dependencies (Embedded)
- Parquet.Net 5.3.0
- Serilog.AspNetCore 8.0.0
- Serilog.Extensions.Logging.File 3.0.0
- System.Management 8.0.0
- OpcRcw.Da 3.0.3.0
- OpcRcw.Comn 1.10.2.0

---

## 🎯 Deployment Checklist

- [x] Build completed successfully
- [x] Self-contained executable created (87.3 MB)
- [x] LicenseGenerator built (59.89 MB)
- [x] License generated and included
- [x] Installation scripts created
- [x] Configuration files included
- [x] Documentation created
- [x] ZIP package created (63.77 MB)
- [x] All dependencies embedded
- [x] No external downloads required

---

## 🚢 Ready for Deployment!

The complete setup package is ready to distribute:

**Package:** `CereveateOPCServer_v1.0_Standalone.zip`  
**Distribution:** Extract and run - NO installation required!  
**Support:** All logs in `Logs\` folder

### Next Steps
1. Distribute ZIP file to client
2. Client extracts to desired location
3. Client runs install-service.bat or launch-silent.bat
4. Application starts automatically
5. Access web interface at http://localhost:5000

---

**Note:** This is a hardware-locked trial version expiring on **March 16, 2026**. The license cannot be transferred to another machine or extended beyond the expiry date.
