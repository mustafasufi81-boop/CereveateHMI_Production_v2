import sys
sys.path.insert(0, r"d:\Development\BACKUP_BEFORE_HISTORICAL_20251117_225747 - Copy\HistoricalTrends")

from parquet_reader_app import app

if __name__ == '__main__':
    print("=" * 60)
    print("🔍 PARQUET READER & COMPARISON TOOL")
    print("=" * 60)
    print(f"📁 Data Directory: D:\\OpcLogs\\Data")
    print(f"🌐 Server: http://localhost:5003")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5003, debug=True, use_reloader=False)
