# Dynamic Log Path Configuration

## Overview
The application now supports **fully configurable log paths** that can be changed at any time by editing the `logging-config.json` file. This allows you to control where application logs and data logs are stored without recompiling the application.

## Configuration File: `logging-config.json`

### Location
The configuration file is located in the same directory as the application executable:
```
C:\Program Files\Cereveate_Praxis\OPC Server\logging-config.json
```

### Configuration Structure

```json
{
  "LoggingPaths": {
    "BaseDirectory": "Logs",
    "DataLogDirectory": "Logs",
    "ApplicationLogDirectory": "Logs"
  },
  "DataLogging": {
    "Enabled": true,
    "IntervalSeconds": 5,
    "FileNamePrefix": "OpcData"
  },
  "Serilog": {
    "MinimumLevel": "Information",
    "RollingInterval": "Day",
    "OutputTemplate": "{Timestamp:yyyy-MM-dd HH:mm:ss.fff} [{Level}] {Message}{NewLine}{Exception}"
  }
}
```

## Log Path Settings

### LoggingPaths Section

| Setting | Description | Default | Example |
|---------|-------------|---------|---------|
| `BaseDirectory` | Base directory for all logs (future use) | `"Logs"` | `"D:\\OPC_Logs"` |
| `DataLogDirectory` | Directory for OPC data logs (Parquet files) | `"Logs"` | `"C:\\ProgramData\\OPC\\Data"` |
| `ApplicationLogDirectory` | Directory for application logs (Serilog) | `"Logs"` | `"C:\\ProgramData\\OPC\\AppLogs"` |

### Path Types

**Relative Paths** (default):
- Paths without a drive letter (e.g., `"Logs"`)
- Created relative to the application installation directory
- Example: `"Logs"` → `C:\Program Files\Cereveate_Praxis\OPC Server\Logs`

**Absolute Paths** (custom):
- Full paths with drive letter (e.g., `"D:\\MyLogs"`)
- Created exactly where specified
- Example: `"D:\\OPC_Logs"` → `D:\OPC_Logs`

## Usage Examples

### Example 1: Default Configuration (Relative Path)
```json
"LoggingPaths": {
  "DataLogDirectory": "Logs",
  "ApplicationLogDirectory": "Logs"
}
```
**Result:**
- Data logs: `C:\Program Files\Cereveate_Praxis\OPC Server\Logs\OpcData_*.parquet`
- App logs: `C:\Program Files\Cereveate_Praxis\OPC Server\Logs\app-*.log`

### Example 2: Separate Directories (Relative Paths)
```json
"LoggingPaths": {
  "DataLogDirectory": "DataLogs",
  "ApplicationLogDirectory": "AppLogs"
}
```
**Result:**
- Data logs: `C:\Program Files\Cereveate_Praxis\OPC Server\DataLogs\OpcData_*.parquet`
- App logs: `C:\Program Files\Cereveate_Praxis\OPC Server\AppLogs\app-*.log`

### Example 3: Custom Absolute Paths
```json
"LoggingPaths": {
  "DataLogDirectory": "D:\\OPC_DataLogs",
  "ApplicationLogDirectory": "C:\\ProgramData\\CereveateOPC\\Logs"
}
```
**Result:**
- Data logs: `D:\OPC_DataLogs\OpcData_*.parquet`
- App logs: `C:\ProgramData\CereveateOPC\Logs\app-*.log`

### Example 4: Network Share (Advanced)
```json
"LoggingPaths": {
  "DataLogDirectory": "\\\\SERVER\\OPC_Logs\\Data",
  "ApplicationLogDirectory": "\\\\SERVER\\OPC_Logs\\Application"
}
```
**Result:**
- Data logs: `\\SERVER\OPC_Logs\Data\OpcData_*.parquet`
- App logs: `\\SERVER\OPC_Logs\Application\app-*.log`

## Important Notes

### Path Formatting
- **Windows paths**: Use double backslashes `\\` in JSON
  - Correct: `"D:\\Logs"`
  - Incorrect: `"D:\Logs"` (single backslash)
- **Forward slashes**: Also supported
  - `"D:/Logs"` works too

### Permissions
- The application must have **write permissions** to the configured directories
- If using network shares, ensure the Windows Service account has access
- The application will attempt to create directories if they don't exist

### Auto-Reload
- Changes to `logging-config.json` are detected automatically
- **Application logs (Serilog)**: Requires application restart to change path
- **Data logs**: Path changes are detected on next logging cycle (configurable interval)

### Directory Creation
- Directories are created automatically if they don't exist
- Creation is logged to the application log
- If creation fails (permissions issue), an error is logged

## File Types

### Data Log Files (OPC Data)
- **Format**: Parquet (columnar binary format)
- **Naming**: `OpcData_YYYYMMDD_HHMMSS.parquet`
- **Location**: `{DataLogDirectory}`
- **Contains**: Tag values, timestamps, quality codes
- **Size**: Automatically rotates at 2 MB per file

### Application Log Files (Serilog)
- **Format**: Plain text
- **Naming**: `app-YYYYMMDD.log`
- **Location**: `{ApplicationLogDirectory}`
- **Contains**: Application events, errors, diagnostics
- **Rotation**: Daily (configurable via `RollingInterval`)

## Serilog Configuration

### Minimum Log Level
Controls which messages are logged:
- `"Verbose"` - Everything (very detailed)
- `"Debug"` - Debugging information
- `"Information"` - Normal operational messages (default)
- `"Warning"` - Warning messages only
- `"Error"` - Errors only
- `"Fatal"` - Critical errors only

Example:
```json
"Serilog": {
  "MinimumLevel": "Debug"
}
```

### Output Template
Customize log message format:
```json
"Serilog": {
  "OutputTemplate": "{Timestamp:yyyy-MM-dd HH:mm:ss.fff} [{Level}] {Message}{NewLine}{Exception}"
}
```

## Data Logging Configuration

### DataLogging Section

| Setting | Description | Default |
|---------|-------------|---------|
| `Enabled` | Enable/disable OPC data logging | `true` |
| `IntervalSeconds` | Seconds between data samples | `5` |
| `FileNamePrefix` | Prefix for data log files | `"OpcData"` |

### Example - Change Logging Interval
```json
"DataLogging": {
  "Enabled": true,
  "IntervalSeconds": 1,
  "FileNamePrefix": "OpcData"
}
```
This will log data every 1 second instead of 5.

## Troubleshooting

### Logs Not Being Created
1. Check file permissions on the configured directory
2. Verify the path is correctly formatted (double backslashes)
3. Check application logs for "Created log directory" messages
4. Ensure the parent directory exists (for network shares)

### "Access Denied" Errors
- The Windows Service doesn't have permission to write to the directory
- Solution: Grant write permissions to `NT AUTHORITY\SYSTEM`
- Or change to a directory the service can access (e.g., `C:\ProgramData`)

### Configuration Not Taking Effect
- **Application logs**: Restart the application/service
- **Data logs**: Wait for next logging interval
- Verify JSON syntax is correct (no missing commas, quotes)
- Check for typos in setting names

## Best Practices

1. **Use ProgramData for production**:
   ```json
   "DataLogDirectory": "C:\\ProgramData\\CereveateOPC\\Data"
   ```
   This avoids permission issues in `Program Files`.

2. **Separate data and application logs**:
   ```json
   "DataLogDirectory": "C:\\ProgramData\\CereveateOPC\\Data",
   "ApplicationLogDirectory": "C:\\ProgramData\\CereveateOPC\\Logs"
   ```

3. **For large data volumes, use dedicated drive**:
   ```json
   "DataLogDirectory": "D:\\OPC_Data"
   ```

4. **Keep relative paths for portability**:
   ```json
   "DataLogDirectory": "Logs"
   ```
   This makes the installation portable across different machines.

## Testing Your Configuration

1. Edit `logging-config.json` with your desired paths
2. Restart the application/service
3. Check the application log for these messages:
   ```
   Data log files will be saved to: [your path]
   Created log directory: [your path]
   Log file reader using directory: [your path]
   ```
4. Connect to an OPC server and enable data logging
5. Verify files are created in your configured directories

## Support

If you need to reset to default configuration, replace `logging-config.json` with:
```json
{
  "LoggingPaths": {
    "BaseDirectory": "Logs",
    "DataLogDirectory": "Logs",
    "ApplicationLogDirectory": "Logs"
  },
  "DataLogging": {
    "Enabled": true,
    "IntervalSeconds": 5,
    "FileNamePrefix": "OpcData"
  },
  "Serilog": {
    "MinimumLevel": "Information",
    "RollingInterval": "Day",
    "OutputTemplate": "{Timestamp:yyyy-MM-dd HH:mm:ss.fff} [{Level}] {Message}{NewLine}{Exception}"
  }
}
```
