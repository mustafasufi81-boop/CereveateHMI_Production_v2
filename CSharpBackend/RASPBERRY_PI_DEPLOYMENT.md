# Raspberry Pi Deployment Guide for testing_app_FIXED.py

## Prerequisites
- Raspberry Pi with Python 3.7 or higher
- Network connectivity to PLC (192.168.0.20)
- Network connectivity to PostgreSQL server (192.168.0.120)

## Installation Steps

### 1. Create directory structure
```bash
sudo mkdir -p /home/cereveate/login
sudo chown -R $USER:$USER /home/cereveate
chmod 755 /home/cereveate/login
```

### 2. Copy application files
```bash
# Copy testing_app_FIXED.py to Raspberry Pi
scp testing_app_FIXED.py pi@raspberrypi:/home/cereveate/
scp requirements.txt pi@raspberrypi:/home/cereveate/
```

### 3. Install Python dependencies
```bash
cd /home/cereveate
pip3 install -r requirements.txt
```

### 4. Test the application
```bash
# Run in foreground to see logs
python3 testing_app_FIXED.py
```

### 5. Run as background service
```bash
# Run in background
nohup python3 testing_app_FIXED.py > /tmp/plc_monitor.log 2>&1 &

# Check if running
ps aux | grep testing_app

# View logs
tail -f /tmp/plc_monitor.log
```

### 6. Auto-start on boot (optional)
Create systemd service:
```bash
sudo nano /etc/systemd/system/plc-monitor.service
```

Add content:
```ini
[Unit]
Description=PLC Monitor Application
After=network.target

[Service]
Type=simple
User=cereveate
WorkingDirectory=/home/cereveate
ExecStart=/usr/bin/python3 /home/cereveate/testing_app_FIXED.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable plc-monitor
sudo systemctl start plc-monitor
sudo systemctl status plc-monitor
```

## Features

### Database Logging (PostgreSQL)
- Connects to: 192.168.0.120:5432
- Database: Cereveate
- Tables: 
  - historian_raw.historian_latest_value
  - historian_raw.historian_timeseries

### Parquet File Logging
- Location: /home/cereveate/login/
- Format: ddMMyyHHmmss.parquet (e.g., 10122507153045.parquet)
- Timezone: Indian Standard Time (IST)
- Rotation: New file created each day at midnight IST
- Schema: Timestamp (IST), TagId, Value, Quality, Type

### PLC Connection
- IP: 192.168.0.20
- Path: 192.168.0.20/1,0
- Scan Interval: 1.0 second

### GUI / Headless Mode
- Auto-detects display availability
- GUI mode: Shows live tag values, system log, statistics
- Headless mode: Console logging only (ideal for Raspberry Pi without display)

## Monitoring

### Check parquet files
```bash
ls -lh /home/cereveate/login/
```

### View parquet file content
```python
import pyarrow.parquet as pq
table = pq.read_table('/home/cereveate/login/10122507153045.parquet')
print(table.to_pandas())
```

### Check database records
```bash
psql -h 192.168.0.120 -U cereveate -d Cereveate -c "SELECT COUNT(*) FROM historian_raw.historian_timeseries;"
```

## Troubleshooting

### No parquet files created
- Check permissions: `ls -la /home/cereveate/login/`
- Check disk space: `df -h`
- View logs for errors

### Database connection failed
- Test connectivity: `ping 192.168.0.120`
- Test port: `telnet 192.168.0.120 5432`
- Check PostgreSQL pg_hba.conf allows connection from Raspberry Pi IP

### PLC connection failed
- Test connectivity: `ping 192.168.0.20`
- Verify PLC is online
- Check firewall rules

### Garbage values (scientific notation)
- Application filters values < 1e-10 automatically
- These are stored as 0 in both database and parquet files

## Performance

- Memory usage: ~50-100 MB
- CPU usage: <5% on Raspberry Pi 4
- Parquet file size: ~1-2 MB per day (depends on tag count)
- Database writes: 2 operations per scan (latest_value + timeseries)

## File Naming Convention

Parquet files use format: ddMMyyHHmmss.parquet
- dd: Day (01-31)
- MM: Month (01-12)
- yy: Year (last 2 digits)
- HH: Hour (00-23) IST
- mm: Minute (00-59)
- ss: Second (00-59)

Example: 10122507153045.parquet = Dec 10, 2025, 07:15:30 AM IST

## Log Messages

**Startup:**
- "System Starting - ControlLogix Live Monitor v2.0"
- "PLC Target: 192.168.0.20"
- "Database: 192.168.0.120:5432/Cereveate"
- "Parquet Logging: /home/cereveate/login (IST timezone)"

**Normal Operation:**
- "PLC connected: 192.168.0.20"
- "Started monitoring X tags from PLC"
- "PLC Scan #10: Read 12 tag values" (every 10 scans)
- "Database: Wrote 12 tag values"
- "Wrote 120 records to ddMMyyHHmmss.parquet"

**Errors:**
- "PLC connection lost"
- "Database connection failed"
- "Latest-value insert error: <details>"
