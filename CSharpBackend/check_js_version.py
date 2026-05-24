#!/usr/bin/env python3
"""
Check if dashboard.js has the null check fixes
"""
import os

js_file = r"d:\Development\BACKUP_BEFORE_HISTORICAL_20251117_225747 - Copy_backup_20251206\HMI\static\js\dashboard.js"

print("=" * 80)
print("CHECKING JAVASCRIPT FILE FOR FIXES")
print("=" * 80)

with open(js_file, 'r', encoding='utf-8') as f:
    content = f.read()

# Check for key fixes
fixes = {
    "Chart null check": "const canvas = document.getElementById('main-chart');",
    "Chart mode null check": "const chartModeEl = document.getElementById('chart-mode');",
    "Update rate null check": "const updateRate = document.getElementById('update-rate');",
    "Polling code": "// ALWAYS poll OPC service for live values"
}

print("\n✅ Checking for applied fixes:\n")
all_fixed = True
for fix_name, search_string in fixes.items():
    if search_string in content:
        print(f"   ✅ {fix_name}: FOUND")
    else:
        print(f"   ❌ {fix_name}: MISSING")
        all_fixed = False

# Check file size and modification time
stat = os.stat(js_file)
print(f"\n📄 File info:")
print(f"   Size: {stat.st_size:,} bytes")
print(f"   Modified: {os.path.getmtime(js_file)}")

# Check for problematic lines that should be fixed
problems = []
lines = content.split('\n')
for i, line in enumerate(lines, 1):
    if "document.getElementById('chart-mode').addEventListener" in line and "const chartModeEl" not in lines[i-2]:
        problems.append(f"Line {i}: Missing null check before chart-mode access")
    if "document.getElementById('chart-mode').value = " in line and "if (chart" not in lines[i-1]:
        problems.append(f"Line {i}: Missing null check before chart-mode value set")

if problems:
    print(f"\n⚠️  Potential issues found:")
    for p in problems:
        print(f"   {p}")
else:
    print(f"\n✅ No obvious issues found")

if all_fixed:
    print("\n" + "=" * 80)
    print("✅ ALL FIXES APPLIED TO JAVASCRIPT FILE")
    print("=" * 80)
    print("\n💡 If browser still shows issues:")
    print("   1. Press Ctrl+Shift+R for hard refresh")
    print("   2. OR open Incognito window (Ctrl+Shift+N)")
    print("   3. OR clear all cache: F12 → Application → Clear storage")
else:
    print("\n" + "=" * 80)
    print("❌ SOME FIXES ARE MISSING")
    print("=" * 80)
