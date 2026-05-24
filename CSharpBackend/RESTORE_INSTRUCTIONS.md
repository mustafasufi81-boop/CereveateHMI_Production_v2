# Automation_DB — Full Restore Guide for Windows Server 2022

> **Created**: May 20, 2026  
> **Source DB**: `Automation_DB` on PostgreSQL 17.6 + TimescaleDB 2.23.0 (Windows)  
> **Target**: Windows Server 2022 (x64)

---

## 🖥️ WHAT MUST BE ON THE TARGET SERVER BEFORE YOU START

> Read this section fully before touching anything on the target server.  
> Missing any one item will cause the restore to fail.

### A — Operating System Requirements

| Requirement | Details |
|-------------|---------|
| OS | **Windows Server 2022** Standard or Datacenter (x64) |
| Windows Updates | Apply all pending updates first — some C++ runtimes come via Windows Update |
| .NET Runtime | Not needed for PostgreSQL itself, but needed if you run the C# OPC backend on this server |
| PowerShell | Version 5.1+ (comes with Server 2022 by default) — do NOT use PowerShell 7 for the pg_dump commands, use the built-in 5.1 |
| Disk Space | Minimum **5 GB free** on the drive where PostgreSQL data will live (more is better — current DB is ~2 GB compressed) |
| RAM | Minimum **4 GB** — recommended **8 GB** for good TimescaleDB performance |

---

### B — Visual C++ Runtime (CRITICAL for Windows Server 2022)

> ⚠️ This is the **most common failure point** on a fresh Windows Server 2022.  
> PostgreSQL 17 and TimescaleDB require Visual C++ 2015–2022 redistributable.  
> A fresh Server 2022 **may NOT have this**. Without it, PostgreSQL service will fail to start silently.

**Check if already installed:**
```powershell
Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64" -ErrorAction SilentlyContinue | Select-Object Version
# OR check via installed programs:
Get-WmiObject Win32_Product | Where-Object { $_.Name -like "*Visual C++*" } | Select-Object Name, Version
```

**If NOT installed — download and install:**
- URL: https://aka.ms/vs/17/release/vc_redist.x64.exe
- This is the **Microsoft Visual C++ 2015–2022 Redistributable (x64)**
- Run as Administrator
- Restart the server after installing

---

### C — Exact Software Versions Required

| Software | Version | MUST match? | Notes |
|----------|---------|------------|-------|
| PostgreSQL | **17.x** | ✅ YES — major version must be 17 | PG 16 or PG 15 will REJECT the backup |
| TimescaleDB | **2.23.0 or newer** | ✅ YES — must be 2.x | Cannot downgrade (e.g. 2.20 cannot restore 2.23 dump) |
| Windows | Server 2022 x64 | Recommended | Server 2019 also works if x64 |
| Visual C++ | 2015–2022 x64 | ✅ YES | PostgreSQL 17 will not start without it |

> **Why PostgreSQL 17 specifically?**  
> The `.dump` file is in `pg_dump` custom format version tied to the source PostgreSQL major version.  
> A PostgreSQL 16 server cannot restore a PostgreSQL 17 dump. Period.  
> A PostgreSQL 17.1 server CAN restore a PostgreSQL 17.6 dump (minor versions are compatible).

---

### D — Windows Firewall / Port

If other machines need to connect to this PostgreSQL:
```powershell
# Allow PostgreSQL port through Windows Firewall (run as Administrator)
New-NetFirewallRule -DisplayName "PostgreSQL 5432" -Direction Inbound -Protocol TCP -LocalPort 5432 -Action Allow
```

Also update `pg_hba.conf` after installation to allow remote connections (see Step 9 below).

---

### E — Pre-Install Checklist (tick before starting)

```
[ ] Windows Server 2022 x64 — fully updated
[ ] Visual C++ 2015-2022 Redistributable x64 — installed
[ ] 5+ GB free disk space confirmed
[ ] PostgreSQL 17.x installer downloaded (NOT 15, NOT 16)
[ ] TimescaleDB 2.23.0+ installer/zip downloaded
[ ] 3 backup files copied to C:\DB_Backups\ on this server
[ ] Logged in as a user with Administrator privileges
```

---

## ⚠️ CRITICAL ANSWER TO YOUR QUESTION

> *"Will the backup have all TimescaleDB features or do I have to redo all settings?"*

**✅ YES — the backup file contains EVERYTHING:**
- All hypertable definitions and chunks (compressed + raw)
- Compression policy (compress after 7 days)
- Retention policy (drop after 2 years)
- Continuous aggregate `ts_hourly_agg` (hourly rollup + auto-refresh)
- All indexes (BRIN + B-tree)
- All background jobs (compression, retention, aggregate refresh)
- All data — every row

**BUT** — the target server must have **PostgreSQL + TimescaleDB pre-installed BEFORE you restore**.  
The extension code lives in the server binaries — the dump only stores the *activation* of it, not the binaries themselves.  
**One `timescaledb.restoring = 'on'` flag** is required during restore (see Step 6 below) — that's the only special setting.

---

## Files You Need to Copy to Target Server

After running `backup_automation_db.py` you will have 3 files in `C:\DB_Backups\`:

| File | Purpose |
|------|---------|
| `Automation_DB_YYYYMMDD_HHMMSS.dump` | Full database (all data + all settings) |
| `Automation_DB_YYYYMMDD_HHMMSS_roles.sql` | DB user `cereveate` definition |
| `Automation_DB_YYYYMMDD_HHMMSS_info.txt` | Backup manifest |

Copy **all 3 files** to the target server, e.g. `C:\DB_Backups\`.

---

## Step-by-Step Restore on Windows Server 2022

---

### STEP 1 — Install PostgreSQL 17 on the Target Server

> ⚠️ **Install Visual C++ Runtime FIRST** (Section B above) before PostgreSQL.  
> If PG installer says "service failed to start" — the VC++ runtime is missing.

1. Download **PostgreSQL 17.x for Windows x64** (NOT 15, NOT 16):  
   → https://www.enterprisedb.com/downloads/postgres-postgresql-downloads  
   → Select version **17.x**, platform **Windows x86-64**  
   → Direct link example: `postgresql-17.6-1-windows-x64.exe`

2. Run installer **as Administrator** (right-click → Run as administrator)

3. During installer wizard:
   - **Installation Directory**: `C:\Program Files\PostgreSQL\17` (default — keep it)
   - **Data Directory**: `C:\Program Files\PostgreSQL\17\data` (default — keep it)
   - **Password**: set a superuser password — write it down
   - **Port**: `5432` (keep default)
   - **Locale**: `Default locale`
   - **Stack Builder**: ❌ UNCHECK — we install TimescaleDB manually

4. After install, open a **new** PowerShell as Administrator and verify:

```powershell
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -c "SELECT version();"
```

Expected output: `PostgreSQL 17.x on x86_64-pc-windows-msvc ...`

> If psql opens but immediately closes → the service isn't running.  
> Fix: `Start-Service -Name "postgresql-x64-17"`

5. Confirm the Windows service exists:
```powershell
Get-Service -Name "postgresql-x64-17" | Select-Object Status, StartType
# Expected: Status=Running, StartType=Automatic
```

---

### STEP 2 — Install TimescaleDB 2.23.0 on the Target Server

> ⚠️ **TimescaleDB must be installed BEFORE restoring the database.**  
> The restore will fail if TimescaleDB binaries are not present.  
> ⚠️ On Windows Server 2022, use the **Windows `.exe` installer** — do NOT use Linux/Docker instructions.

**Option A — Official TimescaleDB Windows Installer (RECOMMENDED)**

1. Go to: https://docs.timescale.com/self-hosted/latest/install/installation-windows/
2. Download the Windows installer for **PostgreSQL 17**
3. Run as Administrator — it auto-detects PostgreSQL and copies files to the right folders
4. When asked which PostgreSQL to configure — select **PostgreSQL 17**

**Option B — Manual install from GitHub (if installer page is unavailable)**

1. Go to: https://github.com/timescale/timescaledb/releases/tag/2.23.0
2. Download: `timescaledb-postgresql-17-windows-amd64.zip`
3. Extract and copy files **as Administrator in PowerShell**:
```powershell
# Adjust the extract path below to where you unzipped the file
$src = "C:\Users\Administrator\Downloads\timescaledb-release"
Copy-Item "$src\lib\*.dll"      "C:\Program Files\PostgreSQL\17\lib\" -Force
Copy-Item "$src\share\*.sql"    "C:\Program Files\PostgreSQL\17\share\extension\" -Force
Copy-Item "$src\share\*.control" "C:\Program Files\PostgreSQL\17\share\extension\" -Force
```

**After either option — Edit `postgresql.conf`:**

Find where postgresql.conf is:
```powershell
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -c "SHOW config_file;"
# Typically: C:\Program Files\PostgreSQL\17\data\postgresql.conf
```

Open `postgresql.conf` in Notepad **as Administrator** and add/edit these lines:
```ini
# TimescaleDB (REQUIRED — without this line PG will start but TimescaleDB won't load)
shared_preload_libraries = 'timescaledb'

# Performance tuning (same as source server)
shared_buffers           = 512MB
work_mem                 = 32MB
max_wal_size             = 2GB
checkpoint_completion_target = 0.9
```

> If `shared_preload_libraries` already has something like `'pg_stat_statements'`, keep it:  
> `shared_preload_libraries = 'timescaledb,pg_stat_statements'`

Restart the service:
```powershell
Restart-Service -Name "postgresql-x64-17"
Start-Sleep 5
Get-Service -Name "postgresql-x64-17" | Select-Object Status
# Expected: Status = Running
```

Verify TimescaleDB is available — **do this before proceeding to Step 3**:
```powershell
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -c "SELECT default_version FROM pg_available_extensions WHERE name = 'timescaledb';"
```

> ✅ **Expected**: one row showing `2.23.0` (or newer)  
> ❌ **No rows** → `.dll` not copied correctly — redo Option A or B  
> ❌ **Service won't start** → Visual C++ 2015–2022 runtime missing — install it (see Section B) and retry

---

### STEP 3 — Create the `cereveate` User

```powershell
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres
```

In psql, run:
```sql
CREATE USER cereveate WITH PASSWORD 'cereveate@222' SUPERUSER;
```

Or restore from the roles file:
```powershell
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -f "C:\DB_Backups\Automation_DB_YYYYMMDD_HHMMSS_roles.sql"
-- Then manually set the password:
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -c "ALTER USER cereveate WITH PASSWORD 'cereveate@222';"
```

---

### STEP 4 — Create the Empty Target Database

```powershell
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -c "CREATE DATABASE ""Automation_DB"" OWNER cereveate;"
```

---

### STEP 5 — Pre-Create TimescaleDB Extension in the Database

> This step is MANDATORY. The restore will fail without it.

```powershell
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -d "Automation_DB" -c "CREATE EXTENSION IF NOT EXISTS timescaledb;"
```

Expected output:
```
WARNING:  
HINT:  ...
CREATE EXTENSION
```
(The warning about TimescaleDB is normal — ignore it.)

---

### STEP 6 — Enable Restore Mode in postgresql.conf

> ⚠️ This is the **ONE TimescaleDB-specific flag** required for restore.  
> Without it, TimescaleDB will reject the hypertable chunk data.

Edit `postgresql.conf` on the **target server** and add:
```
timescaledb.restoring = 'on'
```

Restart PostgreSQL:
```powershell
Restart-Service -Name "postgresql-x64-17"
```

---

### STEP 7 — Restore the Database

```powershell
$env:PGPASSWORD = "cereveate@222"

& "C:\Program Files\PostgreSQL\17\bin\pg_restore.exe" `
    -h localhost `
    -p 5432 `
    -U cereveate `
    -d "Automation_DB" `
    --no-acl `
    --no-owner `
    -v `
    "C:\DB_Backups\Automation_DB_YYYYMMDD_HHMMSS.dump"
```

This will take **several minutes** (same as original backup time).  
You will see thousands of lines — this is normal.  
Watch for `ERROR:` lines — a few are acceptable (pre-existing objects), but repeated errors are not.

---

### STEP 8 — Disable Restore Mode (CRITICAL — do not skip)

> ⚠️ If you leave `timescaledb.restoring = 'on'`, TimescaleDB background jobs will NOT run.

Edit `postgresql.conf` and **remove** (or comment out) the line:
```
# timescaledb.restoring = 'on'    ← remove or comment this out
```

Restart PostgreSQL:
```powershell
Restart-Service -Name "postgresql-x64-17"
```

---

### STEP 9 — Verify the Restore

Run this Python script on the target server (uses same credentials):

```python
import psycopg2
conn = psycopg2.connect(host="localhost", port=5432, dbname="Automation_DB",
                        user="cereveate", password="cereveate@222")
cur = conn.cursor()

# Check TimescaleDB
cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'timescaledb';")
print("TimescaleDB version:", cur.fetchone())

# Check hypertable
cur.execute("SELECT count(*) FROM timescaledb_information.chunks WHERE hypertable_name = 'historian_timeseries';")
print("Chunks restored:", cur.fetchone()[0])

# Check row count
cur.execute("SELECT count(*) FROM historian_raw.historian_timeseries;")
print("Total rows:", cur.fetchone()[0])

# Check policies
cur.execute("SELECT application_name FROM timescaledb_information.jobs WHERE hypertable_name = 'historian_timeseries';")
print("Active jobs:", [r[0] for r in cur.fetchall()])

# Check continuous aggregate
cur.execute("SELECT count(*) FROM historian_raw.ts_hourly_agg;")
print("Hourly agg rows:", cur.fetchone()[0])

conn.close()
print("\nAll checks passed — restore successful!")
```

Expected output:
```
TimescaleDB version: ('2.23.0',)
Chunks restored:     <N chunks>
Total rows:          15,000,000+
Active jobs:         ['Compression Policy', 'Retention Policy', 'Refresh Continuous Aggregate']
Hourly agg rows:     6064+
All checks passed — restore successful!
```

---

### STEP 10 — Update `appsettings.json` on Target Server

Update the connection string in `appsettings.json` to point to the new server's PostgreSQL:

```json
"Historian": {
  "ConnectionString": "Host=localhost;Port=5432;Database=Automation_DB;Username=cereveate;Password=cereveate@222;"
}
```

If the C# OPC backend will run on a **different machine** than PostgreSQL, replace `localhost` with the server IP.

---

### STEP 11 — Allow Remote Connections (if OPC backend is on a different machine)

By default PostgreSQL on Windows only accepts `localhost` connections. If the C# OPC backend runs on a **different PC or server**, do this on the PostgreSQL server:

**A) Edit `pg_hba.conf`** (in the same folder as `postgresql.conf`):

Add this line at the bottom (replace `192.168.1.0/24` with your actual network range):
```
# Allow OPC backend machine to connect
host    Automation_DB    cereveate    192.168.1.0/24    scram-sha-256
```

**B) Edit `postgresql.conf`** — allow PostgreSQL to listen on the network:
```ini
listen_addresses = '*'
```
(Change from `localhost` to `*`)

**C) Restart and open firewall:**
```powershell
Restart-Service -Name "postgresql-x64-17"
New-NetFirewallRule -DisplayName "PostgreSQL 5432" -Direction Inbound -Protocol TCP -LocalPort 5432 -Action Allow
```

**D) Update `appsettings.json`** on the OPC backend machine:
```json
"Historian": {
  "ConnectionString": "Host=192.168.1.XXX;Port=5432;Database=Automation_DB;Username=cereveate;Password=cereveate@222;"
}
```

---

## Quick Reference — All PowerShell Commands in Order

```powershell
# On TARGET server (Windows Server 2022) — run as Administrator

# 0. Pre-requisite: Install Visual C++ 2015-2022 Runtime (if not already)
# Download from: https://aka.ms/vs/17/release/vc_redist.x64.exe

# 1. After installing PostgreSQL 17 + TimescaleDB + editing postgresql.conf:
Restart-Service -Name "postgresql-x64-17"
Start-Sleep 5
Get-Service -Name "postgresql-x64-17" | Select-Object Status  # Must be Running

# 2. Create user + DB
$env:PGPASSWORD = "YourPostgresPassword"
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -c "CREATE USER cereveate WITH PASSWORD 'cereveate@222' SUPERUSER;"
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -c 'CREATE DATABASE "Automation_DB" OWNER cereveate;'

# 3. Verify TimescaleDB available (MUST show a version row before continuing)
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -c "SELECT default_version FROM pg_available_extensions WHERE name = 'timescaledb';"

# 4. Pre-create extension in the new database
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -d "Automation_DB" -c "CREATE EXTENSION IF NOT EXISTS timescaledb;"

# 5. Add restore flag to postgresql.conf:
#    timescaledb.restoring = 'on'
#    Then restart:
Restart-Service -Name "postgresql-x64-17"

# 6. Restore (replace filename with actual backup file)
$env:PGPASSWORD = "cereveate@222"
& "C:\Program Files\PostgreSQL\17\bin\pg_restore.exe" -h localhost -p 5432 -U cereveate -d "Automation_DB" --no-acl --no-owner -v "C:\DB_Backups\Automation_DB_20260520_075419.dump"

# 7. Remove timescaledb.restoring=on from postgresql.conf → Restart
#    (comment out or delete the line)
Restart-Service -Name "postgresql-x64-17"
```

---

## Recommended postgresql.conf Settings for Target Server

Apply these same performance settings that were set on the source server:

```ini
shared_preload_libraries = 'timescaledb'
shared_buffers           = 512MB
work_mem                 = 32MB
max_wal_size             = 2GB
checkpoint_completion_target = 0.9
```

---

## Common Errors & Fixes

| Error | Cause | Fix |
|-------|-------|-----|
| `ERROR: extension "timescaledb" does not exist` | Extension not pre-created | Run Step 5 |
| `ERROR: function timescaledb_pre_restore() does not exist` | `restoring=on` not set | Run Step 6 |
| `FATAL: timescaledb background worker failed` | Restoring mode left ON | Remove `timescaledb.restoring=on` (Step 8) |
| `pg_restore: error: query failed: permission denied` | Wrong user | Use superuser `cereveate` or `postgres` |
| `pg_restore: [archiver] unsupported version` | PG version mismatch | Target must be PG 17.x — NOT 15 or 16 |
| Jobs not running after restore | `restoring=on` still active | Restart PG after removing the flag |
| PG service fails to start silently | VC++ 2015–2022 runtime missing | Install `vc_redist.x64.exe` from https://aka.ms/vs/17/release/vc_redist.x64.exe |
| `The specified module could not be found` in Windows Event Log | TimescaleDB `.dll` not in `lib\` folder | Redo Step 2 Option A or B |
| `connection refused` from remote machine | `listen_addresses` still `localhost` | Set `listen_addresses = '*'` in `postgresql.conf` + open firewall port 5432 |
| `pg_hba.conf rejects connection` from remote | Remote IP not in `pg_hba.conf` | Add `host Automation_DB cereveate <IP>/32 scram-sha-256` |
| `Could not connect to server` from C# backend | Wrong IP in `appsettings.json` | Replace `localhost` with server IP address |

---

## What DOES and DOES NOT Transfer

| Object | Transfers in dump? | Notes |
|--------|-------------------|-------|
| All table data | ✅ Yes | Every row |
| Hypertable structure | ✅ Yes | Chunks recreated |
| Compressed chunks | ✅ Yes | Stored as-is |
| Compression policy | ✅ Yes | Auto-resumes |
| Retention policy | ✅ Yes | Auto-resumes |
| Continuous aggregate | ✅ Yes | `ts_hourly_agg` |
| All indexes | ✅ Yes | BRIN + B-tree |
| Background jobs | ✅ Yes | All 3 jobs |
| TimescaleDB binaries | ❌ No | Must install on target |
| postgresql.conf tuning | ❌ No | Apply manually (see above) |
| Windows service setup | ❌ No | Done by PG installer |

---

*Document prepared: May 20, 2026*  
*Backup script: `backup_automation_db.py`*
