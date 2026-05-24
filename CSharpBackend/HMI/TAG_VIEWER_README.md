# Tag Trend Viewer - Historical Data Query UI

## Overview
A standalone Python UI application for querying and visualizing historical tag data from the OPC DA Historian database. Shows **ALL data points** in an interactive trend chart with customizable date ranges.

## Features

### 📊 Data Visualization
- **Interactive trend chart** with zoom/pan capabilities
- **Date axis** showing timestamps accurately
- Option to show/hide data points on the trend line
- Automatic downsampling for large datasets (maintains data integrity)

### 🔍 Query Controls
- **Tag selection** dropdown with all enabled tags from database
- **Flexible date range** picker (start/end timestamps)
- **Quick range buttons**: 1 hour, 6 hours, 24 hours, 7 days
- **Max points limiter** to control display performance (100-100,000 points)

### 📈 Data Display
- **Real-time statistics**: Average, Min, Max values
- **Data point count**: Shows total records vs. displayed points
- **Data table**: Last 100 rows with timestamp, value, quality details
- **CSV Export**: Export all queried data to CSV file

### ⚙️ Smart Sampling
- If data exceeds max points, uses **time-bucket averaging** to maintain trend accuracy
- Preserves data distribution across the entire time range
- Shows sampling status in display message

## Installation

### Prerequisites
1. Python 3.11+ with virtual environment
2. PostgreSQL/TimescaleDB with historian data
3. Required packages (auto-installed):
   - PyQt5 (UI framework)
   - pyqtgraph (charting)
   - psycopg2 (database)
   - numpy (calculations)

### Setup
```bash
cd HMI
.\venv\Scripts\pip.exe install PyQt5 pyqtgraph numpy
```

## Usage

### Method 1: Batch File (Recommended)
```bash
START_TAG_VIEWER.bat
```

### Method 2: Python Direct
```bash
cd HMI
.\venv\Scripts\python.exe tag_trend_viewer.py
```

## How to Use

1. **Launch the application**
   - UI opens showing all available tags from `historian_meta.tag_master`

2. **Select a tag**
   - Choose from dropdown (shows Tag ID, Name, and Engineering Unit)

3. **Set date range**
   - Use date/time picker OR click quick range buttons
   - Default: Last 24 hours

4. **Configure display**
   - Check "Show Data Points" to display markers on trend
   - Set "Max Points" to balance detail vs. performance (default: 10,000)

5. **Query data**
   - Click "Query Historical Data" button
   - View results in trend chart and data table

6. **Analyze trends**
   - **Zoom**: Mouse scroll or drag rectangle
   - **Pan**: Right-click and drag
   - **Reset**: Right-click → "View All"
   - Statistics shown in status bar

7. **Export data**
   - Click "Export to CSV" to save all queried data
   - File includes all columns: timestamp, value, quality, tag ID, OPC timestamp

## Database Query Logic

### Standard Query (< Max Points)
```sql
SELECT ingest_timestamp, value, quality_code, tag_id, opc_timestamp
FROM historian_raw.historian_timeseries
WHERE tag_id = 'selected_tag' 
AND opc_timestamp BETWEEN start_time AND end_time
ORDER BY opc_timestamp
```

### Sampled Query (> Max Points)
Uses TimescaleDB `time_bucket` for intelligent downsampling:
```sql
WITH time_buckets AS (
    SELECT 
        time_bucket('interval', opc_timestamp) AS bucket,
        AVG(value) as avg_value,
        MIN(opc_timestamp) as first_timestamp,
        MAX(quality_code) as quality_code
    FROM historian_raw.historian_timeseries
    WHERE tag_id = 'selected_tag' 
    AND opc_timestamp BETWEEN start_time AND end_time
    GROUP BY bucket, tag_id
    ORDER BY bucket
)
SELECT first_timestamp, avg_value, quality_code, tag_id, first_timestamp
FROM time_buckets
LIMIT max_points
```

## Configuration

The app reads database settings from `config.json`:
```json
{
  "database": {
    "host": "localhost",
    "port": 5432,
    "database": "opcda_historian",
    "user": "postgres",
    "password": "admin"
  }
}
```

## UI Components

### Control Panel
- **Tag Selection**: Dropdown with all enabled tags
- **Date Range**: Start/End datetime pickers
- **Quick Ranges**: Preset time range buttons
- **Display Options**: Point visibility, max points limiter
- **Action Buttons**: Query and Export

### Trend Chart
- **X-Axis**: Time (zoomable/pannable)
- **Y-Axis**: Tag value with auto-scaling
- **Legend**: Shows tag ID
- **Grid**: Major/minor gridlines for readability

### Data Table
- Shows last 100 data points
- Columns: Timestamp, Value, Quality, Tag ID, OPC Timestamp
- Scrollable for reviewing specific values

### Status Bar
- Connection status (green = connected, red = error)
- Query results summary
- Statistical information (Avg, Min, Max)

## Performance Tips

1. **Adjust Max Points**: Lower values = faster rendering
   - 1,000 points: Very fast, suitable for quick checks
   - 10,000 points: Balanced (default)
   - 100,000 points: Detailed but slower

2. **Use Quick Ranges**: Faster than custom date picking

3. **Sampling**: Automatically enabled for large datasets
   - Preserves trend shape and statistics
   - Uses time-bucket averaging (not random sampling)

4. **Data Table**: Only shows last 100 rows for performance
   - Use CSV export to get full dataset

## Troubleshooting

### "No database connection"
- Check if PostgreSQL is running
- Verify `config.json` database credentials
- Ensure `historian_meta.tag_master` table exists

### "No data found"
- Verify tag has data in selected time range
- Check if OPC DA system is writing to historian
- Try a wider date range (e.g., Last 7 Days)

### UI doesn't start
- Ensure PyQt5 is installed: `pip install PyQt5 pyqtgraph`
- Check Python version (3.8+)
- Review terminal output for error messages

### Chart not rendering
- Try reducing Max Points to 1,000
- Check if data contains NULL values
- Verify timestamp format in database

## Technical Details

### Dependencies
- **PyQt5**: Desktop UI framework (cross-platform)
- **pyqtgraph**: High-performance plotting library
- **psycopg2**: PostgreSQL adapter
- **numpy**: Numerical calculations

### Data Types Supported
- Numeric (float, int, double)
- Quality codes (0=Good, 1=Bad, 2=Uncertain)
- Timestamps (timezone-aware)

### Database Schema
Queries from `historian_raw.historian_timeseries` hypertable:
- `tag_id`: Unique tag identifier
- `opc_timestamp`: Time from OPC server
- `ingest_timestamp`: Time when data entered historian
- `value`: Numeric measurement
- `quality_code`: Data quality indicator

## Future Enhancements

- [ ] Multi-tag overlay (compare multiple tags)
- [ ] Y-axis dual scaling (different units)
- [ ] Export to Excel with formatting
- [ ] Alarm threshold lines
- [ ] Data gap detection
- [ ] Real-time mode (live updates)
- [ ] Custom aggregations (sum, count, stddev)
- [ ] Bookmark favorite queries

## Support

For issues or questions:
1. Check this README
2. Review `HMI/config.json` settings
3. Verify database connection via `check_recent_data.py`
4. Check OPC DA system is running and connected

---

**Created**: December 2025  
**Version**: 1.0  
**Python**: 3.11+  
**License**: Internal Use
