# ⚠️ CRITICAL: Configuration File Location

## PROBLEM DISCOVERED: December 8, 2025

**ROOT CAUSE OF DATA LOGGING FAILURES:**

### The Issue
The application reads `logging-config.json` from **WHERE THE EXE IS RUNNING**, not from the source directory.

```csharp
// LoggingConfigService.cs line 24
_configPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "logging-config.json");
```

### Multiple Config Files Exist
1. **Source**: `d:\Development\BACKUP_BEFORE_HISTORICAL_20251117_225747 - Copy_backup_20251206\logging-config.json`
2. **Debug Build**: `d:\Development\BACKUP_BEFORE_HISTORICAL_20251117_225747 - Copy_backup_20251206\bin\Debug\net8.0\win-x86\logging-config.json`
3. **Release Build**: `d:\Development\BACKUP_BEFORE_HISTORICAL_20251117_225747 - Copy_backup_20251206\bin\x86\Release\net8.0\win-x86\logging-config.json`

### ⚠️ CRITICAL RULES

1. **ALWAYS CHECK WHICH EXE IS RUNNING FIRST**
   ```cmd
   netstat -ano | findstr ":5001"
   wmic process where "ProcessId=XXXXX" get ExecutablePath
   ```

2. **EDIT THE CORRECT CONFIG FILE**
   - If running from `bin\x86\Release\net8.0\win-x86\` → Edit config THERE
   - If running from `bin\Debug\net8.0\win-x86\` → Edit config THERE
   - **DO NOT** edit source config - it's not used by running app!

3. **THE FILE HAS AUTO-RELOAD**
   - FileSystemWatcher monitors config changes
   - Edits take effect within ~500ms
   - No server restart needed

### What Went Wrong Today

1. Server was running from **Release** folder (`bin\x86\Release\net8.0\win-x86\`)
2. Release config had `"IsEnabled": false` 
3. We edited source config thinking it would fix it
4. Data kept failing because **wrong file was edited**
5. Fixed by editing the **actual config file in Release folder**

### Verification Commands

```powershell
# Find running server
netstat -ano | findstr ":5001"
wmic process where "ProcessId=XXXXX" get ExecutablePath

# Check which config is being used
# The ExecutablePath directory contains the active config!
```

### Database Data Flow Confirmed Working

After fixing the **correct** config file:
- ✅ `IsEnabled: true`
- ✅ `ServerProgId: "Matrikon.OPC.Simulation.1"`
- ✅ `ServerHost: "localhost"`
- ✅ 37 selected tags
- ✅ Data flowing: Latest timestamp advancing every 2 seconds
- ✅ Historian writing to `historian_raw.historian_timeseries`

### Build Process Impact

When you run `dotnet build`, the source `logging-config.json` is **COPIED** to the build output folder. This means:
- Source changes are copied to build folder on next build
- But **running application uses build folder copy, not source**
- FileSystemWatcher monitors **build folder**, not source

### Prevention

**ALWAYS:**
1. Check which exe is running (netstat + wmic)
2. Edit config in THAT folder
3. Or restart server after editing source + rebuilding

**NEVER:**
1. Assume source config is being used
2. Edit source config when server is running (unless rebuilding)
3. Edit wrong build folder (Debug vs Release)
