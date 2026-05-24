"""
Test script to browse Rockwell PLC tags using pylogix
Tests direct connection to PLC at 192.168.0.20
"""

from pylogix import PLC
import socket

def test_network_connectivity():
    """Test basic network connectivity to PLC"""
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
            print(f"  ✓ TCP port {PLC_PORT} is OPEN - PLC is reachable!")
            return True
        else:
            print(f"  ✗ TCP port {PLC_PORT} is CLOSED (error: {result})")
            return False
    except Exception as e:
        print(f"  ✗ Connection failed: {e}")
        return False

def test_pylogix_browse():
    """Test tag browsing with pylogix"""
    print("\n" + "="*60)
    print("Testing Tag Browse with pylogix")
    print("="*60)
    
    PLC_IP = "192.168.0.20"
    SLOT = 1
    
    try:
        with PLC() as comm:
            comm.IPAddress = PLC_IP
            comm.ProcessorSlot = SLOT
            comm.Micro800 = False  # ControlLogix, not Micro800
            
            print(f"\nConnecting to {PLC_IP}, Slot {SLOT}...")
            
            # Get all tags
            print("\nBrowsing tags...")
            tags = comm.GetTagList()
            
            if tags.Status == "Success":
                print(f"\n✓ SUCCESS! Found {len(tags.Value)} tags:\n")
                
                # Print all tags
                for i, tag in enumerate(tags.Value):
                    tag_type = getattr(tag, 'DataType', 'Unknown')
                    array_size = getattr(tag, 'Array', 0)
                    array_str = f"[{array_size}]" if array_size > 0 else ""
                    print(f"  {i+1:3}. {tag.TagName}{array_str} ({tag_type})")
                    
                    if i >= 49:  # Limit output
                        remaining = len(tags.Value) - 50
                        if remaining > 0:
                            print(f"\n  ... and {remaining} more tags")
                        break
                
                return tags.Value
            else:
                print(f"\n✗ Failed to get tags: {tags.Status}")
                return []
                
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return []

def test_read_known_tags():
    """Test reading specific tags"""
    print("\n" + "="*60)
    print("Testing Read of Known Tags")
    print("="*60)
    
    PLC_IP = "192.168.0.20"
    SLOT = 1
    
    # Tags to test (from your RSLogix screenshot)
    test_tags = [
        "Pump_Flow",
        "Inlet_Pressure",
        "Load_MW",
        "Pump_RPM",
        "Temperature",
        "Blastfurnace_Tuyer1_Pressure",
        "Program:MainProgram.LocalTag",
    ]
    
    try:
        with PLC() as comm:
            comm.IPAddress = PLC_IP
            comm.ProcessorSlot = SLOT
            
            print(f"\nReading tags from {PLC_IP}...")
            
            for tag_name in test_tags:
                result = comm.Read(tag_name)
                if result.Status == "Success":
                    print(f"  ✓ {tag_name} = {result.Value}")
                else:
                    print(f"  ✗ {tag_name}: {result.Status}")
                    
    except Exception as e:
        print(f"\n✗ Error: {e}")

def main():
    print("="*60)
    print("Rockwell PLC Tag Browser Test Script")
    print("Using: pylogix library")
    print("Target: 192.168.0.20 (ControlLogix, Slot 1)")
    print("="*60)
    
    # Test 1: Network connectivity
    network_ok = test_network_connectivity()
    
    if not network_ok:
        print("\n⚠️  Cannot reach PLC. Check:")
        print("   1. PLC is powered on")
        print("   2. Network cable connected")
        print("   3. IP address is correct (192.168.0.20)")
        print("   4. Your PC is on same subnet (192.168.0.x)")
        print("   5. Firewall allows port 44818")
        return
    
    # Test 2: Browse tags
    tags = test_pylogix_browse()
    
    # Test 3: Read specific tags
    if tags:
        test_read_known_tags()

if __name__ == "__main__":
    main()
