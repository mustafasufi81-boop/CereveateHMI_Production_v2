"""
====================================================================
  Automation_DB — Full PostgreSQL + TimescaleDB Backup Script
  Target: Restore on Windows Server 2022
  Created: May 20, 2026
====================================================================

WHAT THIS BACKUP INCLUDES:
  - ALL schemas: historian_raw, historian_meta, public
  - Hypertable definition + ALL chunks (compressed + uncompressed)
  - Compression policies, retention policies
  - Continuous aggregate: ts_hourly_agg
  - All indexes (BRIN, B-tree)
  - All TimescaleDB jobs / background workers
  - All table data (every row)

WHAT THE TARGET SERVER NEEDS:
  - PostgreSQL 17.x  (same major version)
  - TimescaleDB 2.23.0 or newer
  See RESTORE_INSTRUCTIONS.md for step-by-step.
====================================================================
"""

import subprocess
import os
import sys
import time
from datetime import datetime

# ─── CONFIG ──────────────────────────────────────────────────────
PG_BIN     = r"C:\Program Files\PostgreSQL\17\bin"
DB_NAME    = "Automation_DB"
DB_USER    = "cereveate"
DB_HOST    = "localhost"
DB_PORT    = "5432"
DB_PASS    = "cereveate@222"

# Backup output folder — change if you want it on a different drive
BACKUP_DIR = r"C:\DB_Backups"
# ─────────────────────────────────────────────────────────────────

def run_backup():
    os.makedirs(BACKUP_DIR, exist_ok=True)

    timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
    dump_file  = os.path.join(BACKUP_DIR, f"Automation_DB_{timestamp}.dump")
    roles_file = os.path.join(BACKUP_DIR, f"Automation_DB_{timestamp}_roles.sql")
    info_file  = os.path.join(BACKUP_DIR, f"Automation_DB_{timestamp}_info.txt")

    env = os.environ.copy()
    env["PGPASSWORD"] = DB_PASS

    print("=" * 60)
    print("  Automation_DB — TimescaleDB Full Backup")
    print(f"  Started : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Output  : {dump_file}")
    print("=" * 60)

    # ── STEP 1: Dump roles/users (needed on target) ──────────────
    print("\n[1/3] Dumping roles and users...")
    roles_cmd = [
        os.path.join(PG_BIN, "pg_dumpall.exe"),
        "-h", DB_HOST,
        "-p", DB_PORT,
        "-U", DB_USER,
        "--globals-only",
        "--no-role-passwords",   # passwords must be set manually on target
        "-f", roles_file
    ]
    r = subprocess.run(roles_cmd, env=env, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  WARNING: roles dump failed (non-fatal): {r.stderr.strip()}")
    else:
        size = os.path.getsize(roles_file) / 1024
        print(f"  OK  →  {roles_file}  ({size:.1f} KB)")

    # ── STEP 2: Full DB dump (custom format = compressed, fast restore) ──
    print("\n[2/3] Dumping full database (custom format)...")
    print("      This may take several minutes depending on data size...")

    # --no-acl    = skip GRANT/REVOKE (simpler restore on new server)
    # --no-owner  = skip SET OWNER (restore as any superuser)
    # -Fc         = custom format (compressed, supports parallel restore)
    # -Z 5        = compression level 5 (balance of speed vs size)
    dump_cmd = [
        os.path.join(PG_BIN, "pg_dump.exe"),
        "-h", DB_HOST,
        "-p", DB_PORT,
        "-U", DB_USER,
        "-d", DB_NAME,
        "-Fc",          # custom binary format
        "-Z", "5",      # compression level
        "--no-acl",
        "--no-owner",
        "-v",           # verbose so you can see progress
        "-f", dump_file
    ]

    start = time.time()
    proc = subprocess.Popen(
        dump_cmd, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1
    )

    chunk_count = 0
    for line in proc.stdout:
        line = line.strip()
        if "chunk" in line.lower():
            chunk_count += 1
            if chunk_count % 10 == 0:
                print(f"  ... dumping chunks ({chunk_count} so far)")
        elif any(kw in line.lower() for kw in ["dumping", "reading", "saving", "error", "warning"]):
            print(f"  {line}")

    proc.wait()
    elapsed = time.time() - start

    if proc.returncode != 0:
        print(f"\n  ERROR: pg_dump failed (exit code {proc.returncode})")
        sys.exit(1)

    size_mb = os.path.getsize(dump_file) / (1024 * 1024)
    print(f"\n  OK  →  {dump_file}")
    print(f"  Size    : {size_mb:.1f} MB")
    print(f"  Elapsed : {elapsed:.0f}s")

    # ── STEP 3: Write info/manifest file ─────────────────────────
    print("\n[3/3] Writing backup manifest...")
    with open(info_file, "w") as f:
        f.write(f"Automation_DB Backup Manifest\n")
        f.write(f"{'='*50}\n")
        f.write(f"Backup Date    : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Source Host    : {DB_HOST}:{DB_PORT}\n")
        f.write(f"Database       : {DB_NAME}\n")
        f.write(f"PG Version     : 17.6\n")
        f.write(f"TimescaleDB    : 2.23.0\n")
        f.write(f"Dump File      : {os.path.basename(dump_file)}\n")
        f.write(f"Dump Size      : {size_mb:.1f} MB\n")
        f.write(f"Roles File     : {os.path.basename(roles_file)}\n")
        f.write(f"\nSchemas included:\n")
        f.write(f"  - historian_raw  (hypertable + chunks + agg)\n")
        f.write(f"  - historian_meta (tag_master, tag_dim, quality_codes)\n")
        f.write(f"  - public\n")
        f.write(f"\nTimescaleDB objects included:\n")
        f.write(f"  - historian_raw.historian_timeseries (hypertable)\n")
        f.write(f"  - Compression policy  (compress after 7 days)\n")
        f.write(f"  - Retention policy    (drop after 2 years)\n")
        f.write(f"  - Continuous agg      (ts_hourly_agg, 1h refresh)\n")
        f.write(f"  - BRIN index          (idx_historian_ts_time_brin)\n")
        f.write(f"  - B-tree index        (idx_historian_ts_tagid_time)\n")
        f.write(f"\nRESTORE REQUIREMENTS (target server):\n")
        f.write(f"  1. Windows Server 2022 (x64)\n")
        f.write(f"  2. PostgreSQL 17.x     (MUST match major version)\n")
        f.write(f"  3. TimescaleDB 2.23.0+ (MUST be installed before restore)\n")
        f.write(f"\nSee RESTORE_INSTRUCTIONS.md for full step-by-step guide.\n")

    print(f"  OK  →  {info_file}")

    # ── SUMMARY ──────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  BACKUP COMPLETE")
    print(f"  Dump file  : {dump_file}")
    print(f"  Roles file : {roles_file}")
    print(f"  Manifest   : {info_file}")
    print(f"  Total size : {(os.path.getsize(dump_file) + os.path.getsize(roles_file)) / (1024*1024):.1f} MB")
    print("=" * 60)
    print("\n  Next: Copy ALL 3 files to the target server")
    print("  Then follow RESTORE_INSTRUCTIONS.md exactly.\n")


if __name__ == "__main__":
    run_backup()
