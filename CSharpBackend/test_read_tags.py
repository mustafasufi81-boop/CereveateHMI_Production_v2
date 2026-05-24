#!/usr/bin/env python3
"""Test reading specific tags from PLC to verify they exist and are readable"""
from pycomm3 import LogixDriver

try:
    print("Connecting to PLC 192.168.0.20...")
    plc = LogixDriver('192.168.0.20/1,0')
    plc.open()
    print("✅ PLC Connected!\n")
    
    # List of tags from your scan groups
    test_tags = [
        # Welding tags
        "Welding_Current_A",
        "Welding_Voltage_V",
        "Arc",
        "Power",
        "Welder_id",
        "WPS_ID",
        "Joint_Id",
        "Pipe_Id",
        "sim_step",
        # Pump tags
        "Pump_RPM",
        "Pump_Flow_Rate",
        "Pump_Discharge_Pressure",
        "Pump_Suction_Pressure",
        "Pump_Motor_Current",
        "Pump_Bearing_Temp",
        "Pump_Running_Status",
        "Pump_Healthy",
        "Load_MW",
        "Inlet_Temp",
        "Boiler_Inlet_Temp"
    ]
    
    print("=" * 80)
    print("TESTING TAG READS")
    print("=" * 80)
    
    for tag in test_tags:
        try:
            result = plc.read(tag)
            if hasattr(result, 'error') and result.error:
                print(f"❌ {tag:30s} - ERROR: {result.error}")
            else:
                value = result.value if hasattr(result, 'value') else result
                data_type = result.type if hasattr(result, 'type') else type(value).__name__
                print(f"✅ {tag:30s} = {value:15} ({data_type})")
        except Exception as e:
            print(f"❌ {tag:30s} - EXCEPTION: {e}")
    
    print("\n" + "=" * 80)
    print("BATCH READ TEST (like scanner does)")
    print("=" * 80)
    
    # Test batch read like the scanner does
    welding_tags = ["Welding_Current_A", "Welding_Voltage_V", "Arc"]
    print(f"\nReading batch: {welding_tags}")
    results = plc.read(*welding_tags)
    
    for tag, result in zip(welding_tags, results):
        if hasattr(result, 'error') and result.error:
            print(f"❌ {tag}: {result.error}")
        else:
            value = result.value if hasattr(result, 'value') else result
            print(f"✅ {tag} = {value}")
    
    plc.close()
    print("\n✅ Test complete!")
    
except Exception as e:
    print(f"❌ ERROR: {e}")
    import traceback
    traceback.print_exc()
