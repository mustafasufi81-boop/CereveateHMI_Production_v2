# PostgresLogger UI Improvements

## Changes Made

### 1. **Inline Tag Editing** ✅
- **Before**: Clicking "Edit" opened multiple prompt dialogs
- **After**: All fields are directly editable in the table
- **Benefits**: 
  - No system dialogs interrupting workflow
  - Edit multiple tags quickly
  - See all values while editing
  - Just change values and click "Save"

### 2. **Disable Instead of Delete** ✅
- **Before**: "Delete" button removed tag mapping completely
- **After**: "Enable/Disable" toggle button
- **Benefits**:
  - Stops data import without losing configuration
  - Can re-enable later without re-entering all details
  - Disabled tags show with red background
  - Enabled tags show with green background
  - Button color changes: Red (Disable) / Green (Enable)

### 3. **Auto-Start Background Importer** ✅
- **Before**: Required manually starting importer in separate terminal
- **After**: Importer starts automatically with API server
- **Benefits**:
  - Single command to start everything: `uvicorn api.main:app --port 6001`
  - Importer runs in separate console window
  - Automatically stops when API server stops
  - No need to remember separate start commands

## User Interface

### Tag Configuration Table

| TagId | Tag Name | Plant | Asset | Subsystem | Unit | Frequency | Status | Actions |
|-------|----------|-------|-------|-----------|------|-----------|--------|---------|
| SHAFT_VIB._IP_REAR-X | [editable] | [editable] | [editable] | [editable] | [editable] | [dropdown] | Enabled | Save / Disable |

**Green Background** = Enabled tag (importing data)
**Red Background** = Disabled tag (not importing)
**Orange Background** = Not yet mapped

### Editing Workflow

1. **For Mapped Tags**:
   - Edit any field directly in the table
   - Click "Save" to update
   - Click "Disable" to stop importing (keeps configuration)
   - Click "Enable" to resume importing

2. **For Unmapped Tags**:
   - Fill in Tag Name, Plant, Asset fields (required)
   - Optionally fill Subsystem, Unit, Frequency
   - Click "Save" to start importing

## Starting the System

### Single Command (Recommended)
```powershell
cd PostgresLogger
.\venv\Scripts\python.exe -m uvicorn api.main:app --host 0.0.0.0 --port 6001
```

This automatically:
- Starts API server on port 6001
- Starts background importer in new console
- Begins monitoring parquet directory
- Refreshes tag catalog every 60 seconds

### What Happens Behind the Scenes

1. API server starts
2. Startup event triggers `start_importer()`
3. Background importer launches in separate process
4. Importer scans D:\OpcLogs\Data for parquet files
5. Updates tag_catalog table
6. Processes mapped tags every 10 seconds
7. Imports data to sensor_data table

### Accessing the UI

Open browser: http://localhost:6001

## Technical Details

### Files Modified

1. **templates/index.html**:
   - Replaced read-only mapped tag display with inline inputs
   - Changed `editTag()` → `updateTag()` (reads from inline fields)
   - Changed `deleteTag()` → `toggleTag()` (enables/disables)
   - Added visual feedback (background colors based on status)

2. **api/main.py**:
   - Added `subprocess` and `threading` imports
   - Added `start_importer()` and `stop_importer()` functions
   - Added `@app.on_event("startup")` to auto-start importer
   - Added `@app.on_event("shutdown")` to clean up

### Configuration

Tag enabled/disabled state stored in `config/app_config.json`:

```json
{
  "tag_mappings": [
    {
      "parquet_column": "SHAFT_VIB._IP_REAR-X",
      "tag_name": "SHAFT_VIB._IP_REAR-X",
      "plant": "t",
      "asset": "tur",
      "subsystem": "ip",
      "unit": "mm",
      "sampling_frequency_seconds": 0,
      "enabled": true  // ← Controls import
    }
  ]
}
```

When `enabled: false`, importer skips that tag during processing.

## Troubleshooting

### Importer Not Starting?
Check terminal output for:
```
Starting background importer: ...
Background importer started with PID: xxxxx
```

If missing, check:
- `services/background_importer_v2.py` exists
- Virtual environment activated
- Python executable path correct

### Data Not Importing?
1. Check tag is **Enabled** (green background)
2. Verify parquet file exists in D:\OpcLogs\Data
3. Check importer console for errors
4. Run `check_data.py` to verify database records

### Can't Edit Fields?
- Ensure JavaScript enabled in browser
- Check browser console for errors (F12)
- Refresh page to reload UI
