import os
from services.high_performance_importer import HighPerformanceImporter

FILE_PATH = r"D:\OpcLogs\Data\OpcData_20251117_025420_test.parquet"

if not os.path.exists(FILE_PATH):
    raise SystemExit(f"File not found: {FILE_PATH}")

importer = HighPerformanceImporter(worker_id="manual-test")

if importer.enqueue_file(FILE_PATH):
    print("File enqueued successfully")
else:
    print("File already in queue or enqueue failed; attempting to proceed anyway")

metadata = importer.get_next_pending_file()
if not metadata:
    raise SystemExit("No pending file available for import")

print(f"Importing file: {metadata['file_path']}")

success = importer.import_file(metadata)
print(f"Import success: {success}")

HighPerformanceImporter.close_db_pool()
