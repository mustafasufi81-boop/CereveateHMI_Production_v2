"""
Data Scale Analysis - Calculate storage and performance requirements
"""

# Scenario: 300 tags, 1-second logging, 1 year

tags = 300
log_interval_seconds = 1
seconds_per_year = 365 * 24 * 60 * 60  # 31,536,000

# Total data points per year
records_per_tag_per_year = seconds_per_year / log_interval_seconds
total_records_per_year = tags * records_per_tag_per_year

print("=" * 70)
print("DATA SCALE ANALYSIS - 1 Year")
print("=" * 70)
print(f"Tags: {tags}")
print(f"Log Interval: {log_interval_seconds} second")
print(f"Duration: 1 year ({seconds_per_year:,} seconds)")
print()
print(f"Records per tag per year: {records_per_tag_per_year:,.0f}")
print(f"Total records per year: {total_records_per_year:,.0f}")
print(f"Total records per year (scientific): {total_records_per_year:.2e}")

# Storage estimation
# Parquet format (long): RowId(8) + TagId(50) + Timestamp(8) + Value(8) + Quality(10) = ~84 bytes
# With compression: ~30-40 bytes per record
bytes_per_record_compressed = 35
total_bytes = total_records_per_year * bytes_per_record_compressed
total_gb = total_bytes / (1024**3)

print()
print("=" * 70)
print("STORAGE REQUIREMENTS")
print("=" * 70)
print(f"Bytes per record (compressed): {bytes_per_record_compressed}")
print(f"Total storage (uncompressed): {total_bytes / (1024**3):.2f} GB")
print(f"Total storage (with parquet compression): {total_gb:.2f} GB")
print(f"Storage per month: {total_gb/12:.2f} GB")

# Current approach limitations
print()
print("=" * 70)
print("CURRENT APPROACH ANALYSIS")
print("=" * 70)
print("Issue: If each parquet file has ~500 records (as we see now)")
files_if_500_records = total_records_per_year / 500
print(f"  Number of files: {files_if_500_records:,.0f} files/year")
print(f"  JSON cache size: ~{files_if_500_records * 0.5 / 1024:.1f} MB")
print("  ⚠ Problem: Scanning/indexing millions of files is NOT scalable")
print()

# Better file organization
records_per_file_better = 1_000_000  # 1M records per file
files_per_year_better = total_records_per_year / records_per_file_better
print("Better: Larger parquet files (1M records each)")
print(f"  Number of files: {files_per_year_better:,.0f} files/year")
print(f"  File size each: ~{records_per_file_better * bytes_per_record_compressed / (1024**2):.1f} MB")
print(f"  JSON cache size: ~{files_per_year_better * 0.5:.1f} KB")
print()

# Time-partitioned approach
print("=" * 70)
print("RECOMMENDED: TIME-PARTITIONED APPROACH")
print("=" * 70)
print("Organize files by time hierarchy:")
print("  data/")
print("    2025/")
print("      01/  (January)")
print("        2025-01-01.parquet")
print("        2025-01-02.parquet")
print("      02/  (February)")
print("        ...")
print()
files_per_day = 1  # One file per day
days_per_year = 365
print(f"Files per year: {days_per_year} files")
records_per_daily_file = total_records_per_year / days_per_year
print(f"Records per daily file: {records_per_daily_file:,.0f}")
file_size_mb = (records_per_daily_file * bytes_per_record_compressed) / (1024**2)
print(f"File size per day: {file_size_mb:.1f} MB")
print()
print("Benefits:")
print("  ✓ Query for 2025-03-15? Read only data/2025/03/2025-03-15.parquet")
print("  ✓ No need to scan all files - path indicates date")
print("  ✓ Easy to archive old data (move folders)")
print("  ✓ Fast cache rebuild (only check 365 files, not millions)")

# Query performance
print()
print("=" * 70)
print("QUERY PERFORMANCE ESTIMATES")
print("=" * 70)
print("Query: 3 tags, 1 week range")
tags_queried = 3
days_queried = 7
records_to_read = tags_queried * (days_queried * 24 * 60 * 60)
files_to_read = days_queried  # With daily partitioning
print(f"  Records to process: {records_to_read:,.0f}")
print(f"  Files to read: {files_to_read}")
print(f"  Data size: {(records_to_read * bytes_per_record_compressed) / (1024**2):.2f} MB")
print(f"  Estimated read time (SSD): ~{files_to_read * 0.1:.2f} seconds")
print()

# Multi-year projection
print("=" * 70)
print("MULTI-YEAR PROJECTION")
print("=" * 70)
for year in [1, 2, 3, 5, 10]:
    storage = total_gb * year
    files = days_per_year * year
    print(f"{year:2d} year(s): {storage:6.1f} GB, {files:,} files")

print()
print("=" * 70)
print("RECOMMENDATIONS")
print("=" * 70)
print("1. TIME-PARTITIONED FILES (daily or hourly)")
print("   - Folder: YYYY/MM/DD/")
print("   - No need for full file scanning")
print()
print("2. COLUMNAR COMPRESSION")
print("   - Parquet with Snappy/Zstd compression")
print("   - Current approach is good")
print()
print("3. CONSIDER TIME-SERIES DB FOR >5 YEARS")
print("   - InfluxDB, TimescaleDB, QuestDB")
print("   - Better for long-term retention")
print("   - Built-in downsampling")
print()
print("4. IMPLEMENT DATA RETENTION POLICIES")
print("   - Full resolution: 1 year")
print("   - 1-minute average: 2-5 years")
print("   - 1-hour average: 5+ years")
print("   - Reduces storage by 60x (1-sec to 1-min)")
print()
print("5. CACHE STRATEGY")
print("   - For time-partitioned: Cache only file list + date ranges")
print("   - Memory: <1 MB for 10 years of daily files")
print("=" * 70)
