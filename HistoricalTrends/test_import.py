import sys
import traceback

try:
    import parquet_reader_app
    print("SUCCESS: Module imported")
except Exception as e:
    print(f"ERROR: {e}")
    traceback.print_exc()
