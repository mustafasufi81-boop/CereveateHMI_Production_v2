"""
Test script to browse Rockwell PLC tags using libplctag
Tests direct connection to PLC at 192.168.0.20:44818
"""

import ctypes
import time
import sys

# Try to use libplctag Python wrapper if available
try:
    from libplctag import Tag
    HAS_LIBPLCTAG = True
except ImportError:
    HAS_LIBPLCTAG = False
    print("libplctag Python package not installed. Install with: pip install libplctag")

def test_with_libplctag_python():
    """Test using Python libplctag wrapper"""
    print("\n" + "="*60)
    print("Testing with libplctag Python wrapper")
    print("="*60)
    
    # PLC Configuration
    PLC_IP = "192.168.0.20"
    PLC_PATH = "1,0"  # Slot 1, Connection 0
    
    # Test 1: Try to read @tags (tag listing)
    print(f"\nTest 1: Browsing tags from PLC at {PLC_IP}")
    print("-" * 40)
    
    try:
        # Create tag to list all tags
        tag_path = f"protocol=ab-eip&gateway={PLC_IP}&path={PLC_PATH}&plc=ControlLogix&name=@tags"
        print(f"Tag path: {tag_path}")
        
        tag = Tag(path=tag_path, timeout=5000)
        tag.read()
        
        print(f"Tag size: {tag.size} bytes")
        
        if tag.size > 0:
            # Parse the tag list
            raw_data = bytes([tag.get_uint8(i) for i in range(tag.size)])
            print(f"Raw data (first 100 bytes): {raw_data[:100].hex()}")
            
            # Parse tag entries
            offset = 0
            tags_found = []
            while offset < len(raw_data) - 8:
                try:
                    instance_id = int.from_bytes(raw_data[offset:offset+4], 'little')
                    tag_type = int.from_bytes(raw_data[offset+4:offset+6], 'little')
                    name_len = int.from_bytes(raw_data[offset+6:offset+8], 'little')
                    
                    if name_len > 0 and name_len < 200:
                        name = raw_data[offset+8:offset+8+name_len].decode('utf-8', errors='ignore')
                        tags_found.append({
                            'name': name,
                            'type': tag_type,
                            'instance_id': instance_id
                        })
                        offset += 8 + name_len
                        # Align to 4 bytes
                        if offset % 4 != 0:
                            offset += 4 - (offset % 4)
                    else:
                        offset += 1
                except Exception as e:
                    offset += 1
            
            print(f"\nFound {len(tags_found)} tags:")
            for t in tags_found[:20]:  # Show first 20
                print(f"  - {t['name']} (type: {t['type']})")
            if len(tags_found) > 20:
                print(f"  ... and {len(tags_found) - 20} more")
        else:
            print("No data returned from @tags")
            
    except Exception as e:
        print(f"ERROR reading @tags: {e}")
    
    # Test 2: Try known tag names
    print("\n" + "-" * 40)
    print("Test 2: Reading known test tags")
    print("-" * 40)
    
    test_tags = [
        "Pump_Flow",
        "Inlet_Pressure", 
        "Load_MW",
        "Pump_RPM",
        "Temperature",
        "Blastfurnace_Tuyer1_Pressure",  # From your search box
        "Program:MainProgram.Pump_Flow",
    ]
    
    for tag_name in test_tags:
        try:
            tag_path = f"protocol=ab-eip&gateway={PLC_IP}&path={PLC_PATH}&plc=ControlLogix&name={tag_name}"
            tag = Tag(path=tag_path, timeout=3000)
            tag.read()
            
            value = None
            if tag.size == 4:
                value = tag.get_float32(0)
            elif tag.size == 2:
                value = tag.get_int16(0)
            elif tag.size == 1:
                value = tag.get_uint8(0)
            
            print(f"  ✓ {tag_name}: {value} (size: {tag.size} bytes)")
        except Exception as e:
            print(f"  ✗ {tag_name}: {e}")

def test_network_connectivity():
    """Test basic network connectivity to PLC"""
    import socket
    
    print("\n" + "="*60)
    print("Testing Network Connectivity")
    print("="*60)
    
    PLC_IP = "192.168.0.20"
    PLC_PORT = 44818
    
    # Test TCP connection
    print(f"\nTest: TCP connection to {PLC_IP}:{PLC_PORT}")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((PLC_IP, PLC_PORT))
        sock.close()
        
        if result == 0:
            print(f"  ✓ TCP port {PLC_PORT} is OPEN")
        else:
            print(f"  ✗ TCP port {PLC_PORT} is CLOSED (error: {result})")
    except Exception as e:
        print(f"  ✗ Connection failed: {e}")

def main():
    print("="*60)
    print("Rockwell PLC Tag Browser Test Script")
    print("Target: 192.168.0.20:44818 (ControlLogix, Slot 1)")
    print("="*60)
    
    # Test 1: Network connectivity
    test_network_connectivity()
    
    # Test 2: libplctag browse
    if HAS_LIBPLCTAG:
        test_with_libplctag_python()
    else:
        print("\n⚠️  Cannot test tag browsing without libplctag package")
        print("Install with: pip install libplctag")
        
        # Try alternative: use ctypes to load native library
        print("\nAttempting to use native libplctag.dll...")
        try:
            # Check if native DLL exists in bin folder
            import os
            dll_paths = [
                r"D:\Development\BACKUP_BEFORE_HISTORICAL_20251117_225747 - Copy_backup_20251206\bin\Debug\net8.0\win-x86\runtimes\win-x86\native\plctag.dll",
                r"D:\Development\BACKUP_BEFORE_HISTORICAL_20251117_225747 - Copy_backup_20251206\bin\Debug\net8.0\win-x86\plctag.dll",
            ]
            
            for dll_path in dll_paths:
                if os.path.exists(dll_path):
                    print(f"  Found: {dll_path}")
                else:
                    print(f"  Not found: {dll_path}")
        except Exception as e:
            print(f"  Error: {e}")

if __name__ == "__main__":
    main()
