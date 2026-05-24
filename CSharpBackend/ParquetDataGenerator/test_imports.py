"""Test all imports and basic functionality"""
import sys
print("Python version:", sys.version)
print("Starting import tests...")

try:
    import os
    print("✓ os")
except Exception as e:
    print(f"✗ os: {e}")

try:
    import json
    print("✓ json")
except Exception as e:
    print(f"✗ json: {e}")

try:
    import pandas as pd
    print("✓ pandas")
except Exception as e:
    print(f"✗ pandas: {e}")

try:
    import pyarrow as pa
    print("✓ pyarrow")
except Exception as e:
    print(f"✗ pyarrow: {e}")

try:
    import numpy as np
    print("✓ numpy")
except Exception as e:
    print(f"✗ numpy: {e}")

try:
    from flask import Flask
    print("✓ flask")
except Exception as e:
    print(f"✗ flask: {e}")

try:
    print("\nLoading config.json...")
    with open('config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)
    print("✓ config.json loaded")
    print(f"  - Tags: {len(config['Tags'])}")
    print(f"  - Port: {config['Server']['Port']}")
except Exception as e:
    print(f"✗ config.json: {e}")

try:
    print("\nImporting simulation_engine...")
    from simulation_engine import SimulationEngine
    print("✓ simulation_engine imported")
except Exception as e:
    print(f"✗ simulation_engine: {e}")
    import traceback
    traceback.print_exc()

try:
    print("\nImporting file_transfer_service...")
    from file_transfer_service import FileTransferService
    print("✓ file_transfer_service imported")
except Exception as e:
    print(f"✗ file_transfer_service: {e}")
    import traceback
    traceback.print_exc()

try:
    print("\nImporting backup_service...")
    from backup_service import BackupService
    print("✓ backup_service imported")
except Exception as e:
    print(f"✗ backup_service: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*60)
print("All import tests completed!")
print("="*60)
