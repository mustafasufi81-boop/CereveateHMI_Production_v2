# How to Start All Services — Cereveate OPC Platform

**Root path (use this in every command):**
```
c:\MQTT_Implemented_OPC\Copied_MQTT\BACKUP_BEFORE_HISTORICAL_20251117_225747 - Copy_backup_20251206
```

---

## Service Summary

| # | Service | Port | Folder | Start Command |
|---|---------|------|--------|---------------|
| 1 | C# OPC Backend | 5001 | `bin\Release\net8.0\win-x86\` | Run `.exe` directly |
| 2 | Flask HMI Backend | 6001 | `WEB_HMI_MFA\HMI\` | `python app.py` |
| 3 | React Vite HMI | 8090 | `WEB_HMI_MFA\HMI\apex-hmi\` | `npm run dev` |
| 4 | Analytics (HistoricalTrends) | 6004 | `HistoricalTrends\` | `python app.py` |

---

## Step-by-Step Start (PowerShell)

### 1 — C# OPC Backend (Port 5001)
```powershell
$ROOT = "c:\MQTT_Implemented_OPC\Copied_MQTT\BACKUP_BEFORE_HISTORICAL_20251117_225747 - Copy_backup_20251206"
Start-Process -FilePath "$ROOT\bin\Release\net8.0\win-x86\OpcDaWebBrowser.exe" `
              -WorkingDirectory "$ROOT\bin\Release\net8.0\win-x86" `
              -WindowStyle Minimized
Start-Sleep -Seconds 6
netstat -ano | findstr ":5001" | findstr LISTENING
# Expected: TCP 0.0.0.0:5001 ... LISTENING <PID>
```

### 2 — Flask HMI Backend (Port 6001)
```powershell
$ROOT = "c:\MQTT_Implemented_OPC\Copied_MQTT\BACKUP_BEFORE_HISTORICAL_20251117_225747 - Copy_backup_20251206"
Start-Process -FilePath python -ArgumentList "app.py" `
              -WorkingDirectory "$ROOT\WEB_HMI_MFA\HMI" `
              -WindowStyle Minimized
Start-Sleep -Seconds 6
netstat -ano | findstr ":6001" | findstr LISTENING
# Expected: TCP 0.0.0.0:6001 ... LISTENING <PID>
```

### 3 — React Vite HMI (Port 8090)
```powershell
$ROOT = "c:\MQTT_Implemented_OPC\Copied_MQTT\BACKUP_BEFORE_HISTORICAL_20251117_225747 - Copy_backup_20251206"
Start-Process -FilePath "cmd.exe" -ArgumentList "/c npm run dev" `
              -WorkingDirectory "$ROOT\WEB_HMI_MFA\HMI\apex-hmi" `
              -WindowStyle Minimized
Start-Sleep -Seconds 10
netstat -ano | findstr ":8090" | findstr LISTENING
# Expected: TCP 0.0.0.0:8090 ... LISTENING <PID>
# VERIFY: Get-Process -Id <PID> → ProcessName must be "node" (not WsToastNotification)
```

### 4 — Analytics / HistoricalTrends (Port 6004)
```powershell
$ROOT = "c:\MQTT_Implemented_OPC\Copied_MQTT\BACKUP_BEFORE_HISTORICAL_20251117_225747 - Copy_backup_20251206"
Start-Process -FilePath python -ArgumentList "app.py" `
              -WorkingDirectory "$ROOT\HistoricalTrends" `
              -WindowStyle Minimized
Start-Sleep -Seconds 8
netstat -ano | findstr ":6004" | findstr LISTENING
# Expected: TCP 0.0.0.0:6004 ... LISTENING <PID>
```

---

## Final Verification (all 4 must show)
```powershell
netstat -ano | findstr "5001 6001 8090 6004" | findstr LISTENING
```
Expected output — 4 lines (one per port).

---

## Login
- **URL:** http://localhost:8090
- **Username:** `Mustafa`
- **Password:** `Admin@123`

---

## Stop a Service
```powershell
# Replace <PORT> with 5001 / 6001 / 8090 / 6004
$pid = (netstat -ano | Select-String ":<PORT>.*LISTENING" | Select-Object -First 1) -replace '.*\s+(\d+)$','$1'
Stop-Process -Id ([int]$pid.Trim()) -Force
```

---

## ⚠️ Important Rules
1. **NEVER use `RESTART_SERVER.bat`** — runs `dotnet build`, takes minutes.
2. **NEVER use `dotnet run`** — always use the pre-built exe at `bin\Release\net8.0\win-x86\OpcDaWebBrowser.exe`.
3. **Always use system `python`** (not venv path) for Flask and Analytics — `Start-Process -FilePath python`.
4. **Port 8090 check**: After Vite starts, run `Get-Process -Id <PID>` and confirm `ProcessName = node`. If it shows `WsToastNotification`, kill it and restart Vite.
5. **Start order**: OPC Backend (5001) → Flask (6001) → Analytics (6004) → Vite (8090).
