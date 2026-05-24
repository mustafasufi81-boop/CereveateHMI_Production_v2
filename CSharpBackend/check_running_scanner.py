#!/usr/bin/env python3
"""Check running Python scanner process and estimate cache size"""

import psutil
import sys

def format_bytes(bytes_value):
    """Convert bytes to human-readable format"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_value < 1024.0:
            return f"{bytes_value:.2f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.2f} TB"

print("=" * 80)
print("🔍 CHECKING RUNNING PLC SCANNER PROCESSES")
print("=" * 80)

found_scanner = False
python_procs = []

for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'memory_info', 'create_time']):
    try:
        if proc.info['name'] and 'python' in proc.info['name'].lower():
            python_procs.append(proc)
            cmdline = proc.info.get('cmdline', [])
            
            # Check if it's a scanner process
            is_scanner = False
            if cmdline:
                cmdline_str = ' '.join(cmdline)
                if 'plc_scanner' in cmdline_str.lower() or 'professional_plc_scanner' in cmdline_str.lower():
                    is_scanner = True
                    found_scanner = True
            
            mem_info = proc.info.get('memory_info')
            if mem_info:
                rss = mem_info.rss  # Resident Set Size
                
                print(f"\n{'🎯 ' if is_scanner else ''}PID: {proc.info['pid']}")
                if is_scanner:
                    print("  Type: PLC SCANNER PROCESS ✅")
                print(f"  Command: {' '.join(cmdline[:2]) if cmdline else 'N/A'}")
                print(f"  Memory (RSS): {format_bytes(rss)} ({rss:,} bytes)")
                
                # Estimate cache size based on memory
                # Base Python + libs ~ 50-100 MB
                # Each cached value ~ 100 bytes
                cache_memory = max(0, rss - (80 * 1024 * 1024))  # Subtract 80MB base
                estimated_cache_values = cache_memory // 100
                
                print(f"  Estimated Cache Memory: {format_bytes(cache_memory)}")
                print(f"  Estimated Cache Values: ~{estimated_cache_values:,}")
                
                if is_scanner:
                    # Cache thresholds
                    print(f"\n  📊 Cache Status:")
                    usage_percent = (estimated_cache_values / 50000) * 100
                    print(f"    Current: {estimated_cache_values:,} values ({usage_percent:.1f}% of 50K limit)")
                    print(f"    Per-Tag Limit: 10,000 values")
                    print(f"    Emergency Threshold: 50,000 values")
                    
                    if estimated_cache_values < 5000:
                        print(f"    Status: ✅ EXCELLENT (well under limit)")
                    elif estimated_cache_values < 20000:
                        print(f"    Status: ✅ GOOD (normal operation)")
                    elif estimated_cache_values < 40000:
                        print(f"    Status: ⚠ CAUTION (monitor closely)")
                    else:
                        print(f"    Status: 🚨 WARNING (approaching emergency threshold)")
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        pass

if not found_scanner and python_procs:
    print("\n⚠ No PLC scanner process found, but Python processes detected:")
    print("  Possible reasons:")
    print("    • Scanner stopped")
    print("    • Running different Python script")
    print("    • Check with: tasklist | findstr python")

if not python_procs:
    print("\n❌ No Python processes found running")
    print("  To start scanner: python plc_scanner_enhanced.py")

print("\n" + "=" * 80)
print("💡 TO VIEW LIVE CACHE STATS:")
print("=" * 80)
print("  1. Start scanner: python plc_scanner_enhanced.py")
print("  2. GUI shows real-time cache statistics")
print("  3. Or add periodic logging: tag_cache.get_stats()")
print("=" * 80)
