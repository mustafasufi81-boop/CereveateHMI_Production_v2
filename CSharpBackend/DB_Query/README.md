# 🏭 Cereveate Historian Query Tool

Professional database query tool to demonstrate industrial-grade historian capabilities **WITHOUT** exposing database credentials.

## 🎯 Features

### 1. **Real-Time Statistics Dashboard**
- Total records in historian
- Current insertion rate (records/second)
- Active tags count
- Database size

### 2. **Data Query Interface**
- Multi-tag selection
- Time range filtering
- Configurable result limits (up to 100,000 records)
- Export to CSV

### 3. **Performance Demonstration**
- Query speed for 1 million records
- Aggregation performance (1 hour data)
- Time-series compression efficiency
- Real-time query speed (sub-millisecond)

### 4. **Compression Analysis**
- Shows how deadband filtering reduces storage
- Per-tag compression ratios
- Storage savings percentage
- Demonstrates value-change-only logging

### 5. **Insertion Rate Monitoring**
- **Per-Tag Statistics**: Shows how many records inserted per tag per second
- **Total Records Per Second**: Overall system throughput
- **Real-Time Charts**: Live visualization of insertion rates
- **Second-by-Second Breakdown**: Shows multiple records for same tag in one second

## 🚀 Quick Start

1. **Install Dependencies**:
   ```bash
   pip install flask flask-cors psycopg2-binary
   ```

2. **Configure Database** (edit `config.json`):
   ```json
   {
     "database": {
       "host": "192.168.0.120",
       "port": 5432,
       "database": "Cereveate",
       "user": "postgres",
       "password": "bpcl@1234"
     }
   }
   ```

3. **Start Server**:
   ```bash
   START_QUERY_TOOL.bat
   ```
   OR
   ```bash
   python historian_query_tool.py
   ```

4. **Open Browser**:
   ```
   http://localhost:8080
   ```

## 📊 What This Tool Demonstrates

### Industrial-Grade Performance
- **Fast Queries**: Retrieve millions of records in milliseconds
- **Efficient Aggregations**: Process hours of data instantly
- **Time-Series Optimization**: TimescaleDB hypertables with automatic partitioning
- **Real-Time Access**: Sub-millisecond queries for live data

### Data Compression Power
Shows how historian stores **ONLY value changes** instead of all samples:

**Example:**
- PLC scans at 1000ms (1 sample/second)
- Value stays constant for 10 seconds = 10 samples
- Historian stores only 1 record (when value changed)
- **Compression Ratio: 10:1**
- **Storage Saved: 90%**

### Multi-Record Per Second Demonstration
The tool specifically shows:
- How many times SAME tag was written in ONE second
- Per-tag insertion rates
- System-wide throughput (total records/second)
- Real-time visualization of insertion patterns

## 🔒 Security Features

- Database credentials stored in `config.json` (NOT exposed to web interface)
- No SQL injection vulnerabilities (parameterized queries)
- Read-only queries (no data modification)
- Configurable query limits to prevent abuse

## 📈 API Endpoints

### `/api/tags/list`
Get all enabled tags from `historian_meta.tag_master`

### `/api/data/query`
Query time-series data with filters:
- `tag_id[]`: Array of tag IDs
- `start_time`: ISO timestamp
- `end_time`: ISO timestamp
- `limit`: Max records (default 1000, max 100000)

### `/api/stats/insertion_rate`
Real-time insertion statistics:
- Overall records/second
- Per-tag breakdown
- Last 60 seconds analysis

### `/api/stats/compression`
Compression analysis:
- Per-tag compression ratios
- Storage savings percentage
- Records per second vs stored records

### `/api/stats/total`
Overall historian statistics:
- Total records
- Database size
- Time span covered
- Top tags by record count

### `/api/demo/performance`
Run performance benchmarks:
- Query 1M records
- Aggregation speed
- Compression efficiency
- Real-time query speed

## 🎨 UI Features

### Dashboard Tabs

1. **Overview**
   - Real-time insertion rate chart
   - Per-tag statistics table
   - Auto-refresh every 2 seconds

2. **Query Data**
   - Multi-tag selector
   - Time range picker
   - Result table with pagination
   - CSV export

3. **Performance**
   - Run performance tests
   - Display query speeds
   - Show system capabilities

4. **Compression**
   - Compression ratio charts
   - Per-tag analysis
   - Storage savings visualization

## 💡 Use Cases

### For Demonstrations
- Show clients the historian is **WORKING** and has **REAL DATA**
- Demonstrate industrial-grade performance
- Prove data compression efficiency
- Show multiple records per second capability

### For Debugging
- Verify data is being written correctly
- Check insertion rates per tag
- Analyze time gaps
- Identify performance bottlenecks

### For Reporting
- Export historical data to CSV
- Generate custom time-range reports
- Analyze trends across multiple tags
- Compare compression ratios

## 🛡️ Best Practices

1. **Limit Query Results**: Default 1000, max 100000 to prevent memory issues
2. **Use Time Ranges**: Always specify start/end times for large datasets
3. **Monitor Performance**: Check query execution times
4. **Export Data**: Use CSV export for external analysis

## 🔧 Troubleshooting

### Connection Errors
- Check `config.json` database settings
- Verify PostgreSQL is running
- Test network connectivity: `ping 192.168.0.120`

### Slow Queries
- Reduce time range
- Lower limit value
- Check database indexes

### No Data Showing
- Verify historian is writing data
- Check tag_master table has enabled tags
- Ensure time range includes recent data

## 📝 Notes

- **Database Credentials**: Stored server-side, never sent to browser
- **Read-Only**: Tool cannot modify historian data
- **Performance**: Optimized for TimescaleDB hypertables
- **Auto-Refresh**: Statistics update every 2 seconds

## 🎯 Future Enhancements

- [ ] Add trend visualization for individual tags
- [ ] Implement data quality reports
- [ ] Add alarm/event history viewer
- [ ] Create automated PDF reports
- [ ] Add user authentication
- [ ] Implement WebSocket for real-time updates

---

**Built for Cereveate Industrial Historian** | TimescaleDB + Flask + Bootstrap 5
