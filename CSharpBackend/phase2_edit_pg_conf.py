"""
Phase 2: Edit postgresql.conf — tune shared_buffers, work_mem, max_wal_size.
Reads current file, applies changes with backup, shows diff.
PostgreSQL restart is required after this script.
"""
import re
import shutil
from datetime import datetime

conf_path = r"C:\Program Files\PostgreSQL\17\data\postgresql.conf"
backup_path = conf_path + f".bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

# Settings to apply
CHANGES = {
    "shared_buffers":               "512MB",
    "work_mem":                     "32MB",
    "max_wal_size":                 "2048MB",
    "checkpoint_completion_target": "0.9",
}

# Backup first
shutil.copy2(conf_path, backup_path)
print(f"✅ Backup saved: {backup_path}")

with open(conf_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

new_lines = []
applied = set()

for line in lines:
    stripped = line.strip()
    # Skip full comments
    if stripped.startswith("#") and "=" not in stripped:
        new_lines.append(line)
        continue

    for key, val in CHANGES.items():
        # Match: optional #, optional spaces, key, optional spaces, =
        pattern = re.compile(rf"^#?\s*{re.escape(key)}\s*=", re.IGNORECASE)
        if pattern.match(stripped):
            old = line.rstrip()
            new_line = f"{key} = {val}\n"
            new_lines.append(new_line)
            applied.add(key)
            print(f"  CHANGED: {old!r}")
            print(f"       TO: {new_line.rstrip()!r}")
            break
    else:
        new_lines.append(line)

# If any setting wasn't found in the file, append it
for key, val in CHANGES.items():
    if key not in applied:
        new_lines.append(f"\n{key} = {val}   # Added by phase2 tuning script\n")
        print(f"  ADDED: {key} = {val}")

with open(conf_path, "w", encoding="utf-8") as f:
    f.writelines(new_lines)

print(f"\n✅ postgresql.conf updated.")
print(f"\n⚠️  RESTART PostgreSQL service now:")
print(f"   Run as Administrator in PowerShell:")
print(f"   Restart-Service -Name 'postgresql-x64-17' -Force")
print(f"\n   After restart, run: .venv\\Scripts\\python.exe phase2_verify_after_restart.py")
