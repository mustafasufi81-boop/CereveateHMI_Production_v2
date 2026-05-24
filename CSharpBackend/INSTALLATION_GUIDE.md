# Cereveate_Praxis OPC Server - Installation Guide

## System Requirements
- Windows 10/11 or Windows Server 2016+
- Administrator rights
- .NET 8.0 Runtime (included in self-contained build)
- 200 MB disk space
- Network connectivity for remote OPC server access

## Installation Steps

1. **Extract Files**
   - Extract all files from the installation package to a temporary folder

2. **Run Installer**
   - Right-click `INSTALLER.bat`
   - Select "Run as Administrator"
   - Follow the on-screen prompts

3. **Installation Process**
   The installer will automatically:
   - Install application to `C:\Program Files\CereveateOPC`
   - Create log directories at `D:\OpcLogs`
   - Configure DCOM for remote OPC access
   - Add Windows Firewall rules (ports 135, 10000-10100)
   - Set up auto-start on Windows boot
   - Start the application immediately
   - Create desktop shortcut

4. **Access the Application**
   - Web interface opens automatically at http://localhost:6001
   - Or click the desktop shortcut "Cereveate OPC Server"

## Default Login Credentials

### Administrator Account (Full Access)
- Username: `opcadmin`
- Password: `Cereveate@2025`
- Permissions: Full control, user management, password changes, all features

### Viewer Account (Read-Only)
- Username: `admin`
- Password: `admin123`
- Permissions: Log viewer only, CSV download

**⚠️ IMPORTANT: Change default passwords after first login!**

## Configuration

### Log Directories
- **Data Logs:** `D:\OpcLogs\Data` (OPC tag data in Parquet format)
- **Application Logs:** `D:\OpcLogs\Application` (system logs)
- **Backups:** `D:\BackupFile\OpcLogs` (automatic backups every 5 minutes)

### Modifying Paths
1. Edit `logging-config.json` in installation folder
2. Change paths under `LoggingPaths` section
3. Configuration auto-reloads (no restart needed)

### License
- Trial period: 4 months from installation
- Hardware-locked to this machine
- License file: `.license` (encrypted, hidden)

## Connecting to OPC Servers

### Local OPC Server
1. Leave "Remote Server" blank or enter `localhost`
2. Click "Discover Servers"
3. Select OPC server from list (e.g., Matrikon.OPC.Simulation.1)

### Remote OPC Server
1. Enter remote machine IP address (e.g., 192.168.1.100)
2. Click "Discover Servers"
3. Ensure remote machine has:
   - OPC server software installed (Matrikon, Kepware, etc.)
   - Windows Firewall allows OPC ports
   - DCOM configured (installer does this automatically)

## Auto-Start Configuration
- Application starts automatically on Windows boot
- Runs as SYSTEM user for maximum permissions
- Task name: `CereveateOPCServer`
- Manage via Task Scheduler or installer

## Troubleshooting

### Application Won't Start
- Check logs: `D:\OpcLogs\Application\app-YYYYMMDD.log`
- Verify Task Scheduler entry exists: `CereveateOPCServer`
- Run manually from: `C:\Program Files\CereveateOPC\OpcDaWebBrowser.exe`

### Cannot Connect to Remote OPC Server
- Verify OPC server is running on remote machine
- Check network connectivity (ping remote IP)
- Ensure firewall allows ports 135 and 10000-10100
- Verify DCOM is enabled (installer configures this)

### "No Server Found" Error
- Confirm OPC server software is installed and running
- Use correct IP address or hostname
- For local servers, use `localhost` or leave blank
- Check Windows Event Viewer for DCOM errors

### License Expired
- Contact Cereveate_Praxis for license renewal
- Trial period is 4 months from first installation
- License is hardware-locked and cannot be transferred

## Uninstallation

1. Right-click `UNINSTALLER.bat`
2. Select "Run as Administrator"
3. Confirm uninstallation

**Note:** Log files are preserved and must be deleted manually if needed.

## Support

- Application logs: `D:\OpcLogs\Application`
- Configuration file: `C:\Program Files\CereveateOPC\logging-config.json`
- Port: 6001 (configurable in code)

## Security Notes

- Application runs with SYSTEM privileges
- All credentials encrypted with AES-256 + hardware binding
- OPC connections encrypted and hardware-locked
- Backup directory has restrictive permissions (SYSTEM + Administrators only)
- Session timeout: 24 hours

## Features

✅ Real-time OPC DA tag monitoring
✅ Data logging to Parquet files (5-second intervals)
✅ Automatic backups every 5 minutes
✅ CSV export for data analysis
✅ Two-tier role system (Administrator/Viewer)
✅ User management (password changes, enable/disable accounts)
✅ Auto-reload configuration (no restart needed)
✅ Support for local and remote OPC servers
✅ Dynamic server switching (Matrikon, Kepware, etc.)
✅ 4-month trial license
✅ Hardware-locked security

---

© 2025 Cereveate_Praxis - Professional OPC Server Solution
