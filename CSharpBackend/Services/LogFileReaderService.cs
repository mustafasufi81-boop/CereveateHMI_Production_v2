using Parquet;
using Parquet.Data;

namespace OpcDaWebBrowser.Services;

/// <summary>
/// Service for reading and querying Parquet log files
/// </summary>
public class LogFileReaderService
{
    private readonly string _logsFolder;
    private readonly ILogger<LogFileReaderService> _logger;
    private List<string>? _cachedFileList;
    private DateTime _cacheExpiry = DateTime.MinValue;
    private readonly TimeSpan _cacheLifetime = TimeSpan.FromSeconds(10); // Cache for 10 seconds

    public LogFileReaderService(ILogger<LogFileReaderService> logger, IConfiguration configuration)
    {
        _logger = logger;
        
        // Read log directory from configuration
        var configuredPath = configuration["LoggingPaths:DataLogDirectory"] ?? "Logs";
        
        // If path is relative, make it relative to the application directory
        _logsFolder = Path.IsPathRooted(configuredPath)
            ? configuredPath
            : Path.Combine(AppDomain.CurrentDomain.BaseDirectory, configuredPath);
        
        _logger.LogInformation("Log file reader using directory: {LogDirectory}", _logsFolder);
    }

    public List<string> GetLogFiles()
    {
        try
        {
            // Return cached list if still valid
            if (_cachedFileList != null && DateTime.UtcNow < _cacheExpiry)
            {
                return _cachedFileList;
            }

            if (!Directory.Exists(_logsFolder))
            {
                _cachedFileList = new List<string>();
                _cacheExpiry = DateTime.UtcNow.Add(_cacheLifetime);
                return _cachedFileList;
            }

            // Refresh cache
            _cachedFileList = Directory.GetFiles(_logsFolder, "*.parquet")
                .Select(Path.GetFileName)
                .Where(f => f != null)
                .OrderByDescending(f => f)
                .ToList()!;
            
            _cacheExpiry = DateTime.UtcNow.Add(_cacheLifetime);
            
            return _cachedFileList;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error getting log files");
            return new List<string>();
        }
    }

    // Get row count and summary without loading all data
    public async Task<LogFileSummary> GetLogFileSummary(string? fileName = null, DateTime? startTime = null, DateTime? endTime = null)
    {
        try
        {
            if (!Directory.Exists(_logsFolder))
                return new LogFileSummary();

            var files = Directory.GetFiles(_logsFolder, "*.parquet")
                .OrderByDescending(f => f)
                .ToList();

            if (files.Count == 0)
                return new LogFileSummary();

            string targetFile;
            if (!string.IsNullOrEmpty(fileName))
            {
                targetFile = Path.Combine(_logsFolder, fileName);
                if (!File.Exists(targetFile))
                    return new LogFileSummary();
            }
            else
            {
                targetFile = files.First();
            }

            long totalRows = 0;
            DateTime? firstTime = null;
            DateTime? lastTime = null;
            var tags = new HashSet<string>();

            using var fileStream = File.OpenRead(targetFile);
            using var parquetReader = await ParquetReader.CreateAsync(fileStream);
            var schema = parquetReader.Schema.GetDataFields();

            for (int i = 0; i < parquetReader.RowGroupCount; i++)
            {
                using var groupReader = parquetReader.OpenRowGroupReader(i);
                var tagIdColumn = await groupReader.ReadColumnAsync(schema[1]);
                var timestampColumn = await groupReader.ReadColumnAsync(schema[2]);

                var tagIds = tagIdColumn.Data as string[];
                
                // Try different timestamp formats (nullable, non-nullable, DateTimeOffset)
                DateTime[]? timestamps = timestampColumn.Data as DateTime[];
                if (timestamps == null)
                {
                    // Try Nullable<DateTime>[]
                    var nullableTimestamps = timestampColumn.Data as DateTime?[];
                    if (nullableTimestamps != null)
                    {
                        timestamps = nullableTimestamps.Select(dt => dt ?? DateTime.MinValue).ToArray();
                    }
                    else
                    {
                        // Try DateTimeOffset
                        var timestampsOffset = timestampColumn.Data as DateTimeOffset[];
                        if (timestampsOffset != null)
                        {
                            timestamps = timestampsOffset.Select(dt => dt.DateTime).ToArray();
                        }
                        else
                        {
                            var actualType = timestampColumn.Data?.GetType().Name ?? "null";
                            _logger.LogWarning($"Timestamp column type: {actualType}");
                        }
                    }
                }

                // Apply time filtering
                if (timestamps != null && tagIds != null)
                {
                    for (int j = 0; j < timestamps.Length; j++)
                    {
                        var ts = timestamps[j];
                        
                        // Check time range
                        if (startTime.HasValue && ts < startTime.Value)
                            continue;
                        if (endTime.HasValue && ts > endTime.Value)
                            continue;

                        totalRows++;
                        tags.Add(tagIds[j]);

                        if (!firstTime.HasValue || ts < firstTime.Value)
                            firstTime = ts;
                        if (!lastTime.HasValue || ts > lastTime.Value)
                            lastTime = ts;
                    }
                }
            }

            var summary = new LogFileSummary
            {
                FileName = Path.GetFileName(targetFile),
                TotalRows = totalRows,
                TagCount = tags.Count,
                Tags = tags.ToList(),
                FirstTimestamp = firstTime,
                LastTimestamp = lastTime
            };
            
            _logger.LogInformation($"File: {summary.FileName}, Rows: {totalRows}, Tags: {tags.Count}, Time: {firstTime} to {lastTime}");
            
            return summary;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error getting log file summary");
            return new LogFileSummary();
        }
    }

    // Stream directly to CSV file without loading all data into memory
    public async Task<string> CreateCsvFile(string? fileName = null, DateTime? startTime = null, DateTime? endTime = null)
    {
        try
        {
            if (!Directory.Exists(_logsFolder))
                return string.Empty;

            var files = Directory.GetFiles(_logsFolder, "*.parquet")
                .OrderByDescending(f => f)
                .ToList();

            if (files.Count == 0)
                return string.Empty;

            string targetFile;
            if (!string.IsNullOrEmpty(fileName))
            {
                targetFile = Path.Combine(_logsFolder, fileName);
                if (!File.Exists(targetFile))
                    return string.Empty;
            }
            else
            {
                targetFile = files.First();
            }

            var csvFileName = Path.GetFileNameWithoutExtension(targetFile) + ".csv";
            
            // Save to user's Downloads folder
            var downloadsPath = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "Downloads");
            var csvFilePath = Path.Combine(downloadsPath, csvFileName);

            // Stream directly to CSV without loading into memory
            using var writer = new StreamWriter(csvFilePath, false, System.Text.Encoding.UTF8, 65536); // 64KB buffer
            await writer.WriteLineAsync("RowId,TagId,Timestamp,Value,Quality");

            using var fileStream = File.OpenRead(targetFile);
            using var parquetReader = await ParquetReader.CreateAsync(fileStream);
            var schema = parquetReader.Schema.GetDataFields();

            long recordsWritten = 0;
            var csvBuffer = new System.Text.StringBuilder(8192); // Buffer for batch writing
            
            for (int i = 0; i < parquetReader.RowGroupCount; i++)
            {
                using var groupReader = parquetReader.OpenRowGroupReader(i);
                
                var rowIdColumn = await groupReader.ReadColumnAsync(schema[0]);
                var tagIdColumn = await groupReader.ReadColumnAsync(schema[1]);
                var timestampColumn = await groupReader.ReadColumnAsync(schema[2]);
                var valueColumn = await groupReader.ReadColumnAsync(schema[3]);
                var qualityColumn = await groupReader.ReadColumnAsync(schema[4]);

                // Handle nullable RowId arrays
                long[]? rowIds = rowIdColumn.Data as long[];
                if (rowIds == null)
                {
                    var nullableRowIds = rowIdColumn.Data as long?[];
                    if (nullableRowIds != null)
                        rowIds = nullableRowIds.Select(x => x ?? 0).ToArray();
                }
                
                var tagIds = tagIdColumn.Data as string[];
                
                // Try different timestamp formats
                DateTime[]? timestamps = timestampColumn.Data as DateTime[];
                if (timestamps == null)
                {
                    var timestampsOffset = timestampColumn.Data as DateTimeOffset[];
                    if (timestampsOffset != null)
                    {
                        timestamps = timestampsOffset.Select(dt => dt.DateTime).ToArray();
                    }
                    else
                    {
                        _logger.LogWarning($"Timestamp column type in CreateCsvFile: {timestampColumn.Data?.GetType().Name ?? "null"}");
                        continue; // Skip this row group
                    }
                }
                
                var values = valueColumn.Data as string[];
                var qualities = qualityColumn.Data as string[];

                for (int j = 0; j < (rowIds?.Length ?? 0); j++)
                {
                    var ts = timestamps![j];
                    
                    // Apply time filtering
                    if (startTime.HasValue && ts < startTime.Value)
                        continue;
                    if (endTime.HasValue && ts > endTime.Value)
                        continue;

                    // Convert to local timezone if timestamp is UTC
                    // DateTime.FromFileTime returns local time, but if it's stored as UTC, convert it
                    DateTime localTs = ts.Kind == DateTimeKind.Utc 
                        ? ts.ToLocalTime() 
                        : (ts.Kind == DateTimeKind.Unspecified 
                            ? DateTime.SpecifyKind(ts, DateTimeKind.Utc).ToLocalTime() 
                            : ts);
                    
                    csvBuffer.AppendLine(
                        $"{rowIds![j]},\"{tagIds![j]}\",{localTs:yyyy-MM-dd HH:mm:ss.fff},{values![j]},{qualities![j]}");
                    recordsWritten++;
                    
                    // Write in batches of 1000 rows to prevent blocking
                    if (csvBuffer.Length > 8000)
                    {
                        await writer.WriteAsync(csvBuffer.ToString());
                        csvBuffer.Clear();
                        
                        // Yield to prevent blocking UI thread
                        if (recordsWritten % 10000 == 0)
                            await Task.Yield();
                    }
                }
                
                // Flush buffer after each row group
                if (csvBuffer.Length > 0)
                {
                    await writer.WriteAsync(csvBuffer.ToString());
                    csvBuffer.Clear();
                }
                
                // Yield after each row group to keep system responsive
                await Task.Yield();
            }
            
            // Final flush
            if (csvBuffer.Length > 0)
            {
                await writer.WriteAsync(csvBuffer.ToString());
            }

            _logger.LogInformation($"Created CSV file: {csvFilePath} with {recordsWritten} records");
            return csvFilePath;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error creating CSV file");
            throw; // Throw the exception so client sees the real error
        }
    }

    public async Task<LogDataResult> ReadLogData(string? fileName = null, int maxRecords = 1000, DateTime? startTime = null, DateTime? endTime = null)
    {
        try
        {
            if (!Directory.Exists(_logsFolder))
                return new LogDataResult { Records = new List<LogRecord>() };

            var files = Directory.GetFiles(_logsFolder, "*.parquet")
                .OrderByDescending(f => f)
                .ToList();

            if (files.Count == 0)
                return new LogDataResult { Records = new List<LogRecord>() };

            string targetFile;
            if (!string.IsNullOrEmpty(fileName))
            {
                targetFile = Path.Combine(_logsFolder, fileName);
                if (!File.Exists(targetFile))
                    return new LogDataResult { Records = new List<LogRecord>() };
            }
            else
            {
                targetFile = files.First(); // Most recent file
            }

            var records = await ReadParquetFile(targetFile, maxRecords, startTime, endTime);
            
            return new LogDataResult
            {
                FileName = Path.GetFileName(targetFile),
                RecordCount = records.Count,
                Records = records
            };
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error reading log data");
            return new LogDataResult { Records = new List<LogRecord>() };
        }
    }

    private async Task<List<LogRecord>> ReadParquetFile(string filePath, int maxRecords, DateTime? startTime = null, DateTime? endTime = null)
    {
        var records = new List<LogRecord>();

        try
        {
            using var fileStream = File.OpenRead(filePath);
            using var parquetReader = await ParquetReader.CreateAsync(fileStream);
            
            var schema = parquetReader.Schema.GetDataFields();
            
            _logger.LogInformation($"Reading {Path.GetFileName(filePath)}: {parquetReader.RowGroupCount} row groups");

            for (int i = 0; i < parquetReader.RowGroupCount; i++)
            {
                using var groupReader = parquetReader.OpenRowGroupReader(i);
                
                var rowIdColumn = await groupReader.ReadColumnAsync(schema[0]);
                var tagIdColumn = await groupReader.ReadColumnAsync(schema[1]);
                var timestampColumn = await groupReader.ReadColumnAsync(schema[2]);
                var valueColumn = await groupReader.ReadColumnAsync(schema[3]);
                var qualityColumn = await groupReader.ReadColumnAsync(schema[4]);

                // Handle nullable RowId arrays
                long[]? rowIds = rowIdColumn.Data as long[];
                if (rowIds == null)
                {
                    var nullableRowIds = rowIdColumn.Data as long?[];
                    if (nullableRowIds != null)
                        rowIds = nullableRowIds.Select(x => x ?? 0).ToArray();
                }
                
                var tagIds = tagIdColumn.Data as string[];
                
                // Handle different timestamp formats
                DateTime[]? timestamps = timestampColumn.Data as DateTime[];
                if (timestamps == null)
                {
                    // Try Nullable<DateTime>[]
                    var nullableTimestamps = timestampColumn.Data as DateTime?[];
                    if (nullableTimestamps != null)
                    {
                        timestamps = nullableTimestamps.Select(dt => dt ?? DateTime.MinValue).ToArray();
                    }
                    else
                    {
                        // Try DateTimeOffset[]
                        var timestampsOffset = timestampColumn.Data as DateTimeOffset[];
                        if (timestampsOffset != null)
                        {
                            timestamps = timestampsOffset.Select(dt => dt.DateTime).ToArray();
                        }
                        else
                        {
                            _logger.LogWarning($"Timestamp column type in ReadParquetFile: {timestampColumn.Data?.GetType().Name ?? "null"}");
                            continue; // Skip this row group
                        }
                    }
                }
                
                var values = valueColumn.Data as string[];
                var qualities = qualityColumn.Data as string[];
                
                _logger.LogInformation($"  Row group {i}: {rowIds?.Length ?? 0} rows");

                for (int j = 0; j < (rowIds?.Length ?? 0); j++)
                {
                    var ts = timestamps![j];
                    
                    // Apply time filtering
                    if (startTime.HasValue && ts < startTime.Value)
                        continue;
                    if (endTime.HasValue && ts > endTime.Value)
                        continue;

                    records.Add(new LogRecord
                    {
                        RowId = rowIds![j],
                        TagId = tagIds![j],
                        Timestamp = ts,
                        Value = values![j],
                        Quality = qualities![j]
                    });

                    if (records.Count >= maxRecords)
                        break;
                }

                if (records.Count >= maxRecords)
                    break;
            }
            
            _logger.LogInformation($"Read {records.Count} records total");
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, $"Error reading Parquet file: {filePath}");
        }

        return records.OrderByDescending(r => r.Timestamp).ToList();
    }

    public async Task<Dictionary<string, List<TrendPoint>>> GetTrendData(string? fileName = null, int maxPointsPerTag = 200)
    {
        try
        {
            // Get the file to read
            if (!Directory.Exists(_logsFolder))
                return new Dictionary<string, List<TrendPoint>>();

            var files = Directory.GetFiles(_logsFolder, "*.parquet")
                .OrderByDescending(f => f)
                .ToList();

            if (files.Count == 0)
                return new Dictionary<string, List<TrendPoint>>();

            string targetFile;
            if (!string.IsNullOrEmpty(fileName))
            {
                targetFile = Path.Combine(_logsFolder, fileName);
                if (!File.Exists(targetFile))
                    return new Dictionary<string, List<TrendPoint>>();
            }
            else
            {
                targetFile = files.First();
            }

            // DYNAMIC READ: Read directly from parquet with per-tag tracking
            return await ReadTrendDataFromParquet(targetFile, maxPointsPerTag);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error getting trend data");
            return new Dictionary<string, List<TrendPoint>>();
        }
    }

    private async Task<Dictionary<string, List<TrendPoint>>> ReadTrendDataFromParquet(string filePath, int maxPointsPerTag)
    {
        var trendData = new Dictionary<string, List<TrendPoint>>();

        try
        {
            using var fileStream = File.OpenRead(filePath);
            using var parquetReader = await ParquetReader.CreateAsync(fileStream);
            
            var schema = parquetReader.Schema.GetDataFields();
            
            _logger.LogInformation($"Reading trends from {Path.GetFileName(filePath)}: {parquetReader.RowGroupCount} row groups");

            // Read ALL row groups and collect data per tag
            for (int i = 0; i < parquetReader.RowGroupCount; i++)
            {
                using var groupReader = parquetReader.OpenRowGroupReader(i);
                
                var rowIdColumn = await groupReader.ReadColumnAsync(schema[0]);
                var tagIdColumn = await groupReader.ReadColumnAsync(schema[1]);
                var timestampColumn = await groupReader.ReadColumnAsync(schema[2]);
                var valueColumn = await groupReader.ReadColumnAsync(schema[3]);
                var qualityColumn = await groupReader.ReadColumnAsync(schema[4]);

                var tagIds = tagIdColumn.Data as string[];
                
                // Handle different timestamp formats
                DateTime[]? timestamps = timestampColumn.Data as DateTime[];
                if (timestamps == null)
                {
                    var nullableTimestamps = timestampColumn.Data as DateTime?[];
                    if (nullableTimestamps != null)
                    {
                        timestamps = nullableTimestamps.Select(dt => dt ?? DateTime.MinValue).ToArray();
                    }
                    else
                    {
                        var timestampsOffset = timestampColumn.Data as DateTimeOffset[];
                        if (timestampsOffset != null)
                        {
                            timestamps = timestampsOffset.Select(dt => dt.DateTime).ToArray();
                        }
                        else
                        {
                            _logger.LogWarning($"Skipping row group {i} - unknown timestamp type");
                            continue;
                        }
                    }
                }
                
                var values = valueColumn.Data as string[];
                var qualities = qualityColumn.Data as string[];

                // Process each record and collect ALL data per tag
                for (int j = 0; j < (tagIds?.Length ?? 0); j++)
                {
                    var tagId = tagIds![j];
                    
                    // Initialize tag list if first time seeing this tag
                    if (!trendData.ContainsKey(tagId))
                    {
                        trendData[tagId] = new List<TrendPoint>();
                    }

                    // Add ALL points (we'll trim to latest after)
                    trendData[tagId].Add(new TrendPoint
                    {
                        Timestamp = timestamps![j],
                        Value = values![j],
                        Quality = qualities![j]
                    });
                }

                _logger.LogInformation($"  Row group {i}/{parquetReader.RowGroupCount}: {trendData.Count} unique tags discovered");
            }

            _logger.LogInformation($"Loaded {trendData.Count} tags, now trimming to latest {maxPointsPerTag} points per tag");

            // For each tag, keep only the LATEST maxPointsPerTag points
            foreach (var tagId in trendData.Keys.ToList())
            {
                var allPoints = trendData[tagId];
                
                // Take the LAST maxPointsPerTag points (which are the latest chronologically)
                if (allPoints.Count > maxPointsPerTag)
                {
                    trendData[tagId] = allPoints.Skip(allPoints.Count - maxPointsPerTag).ToList();
                }
            }
            
            // Calculate the ACTUAL time range of the trend data being returned
            DateTime? firstTrendTime = null;
            DateTime? lastTrendTime = null;
            
            foreach (var points in trendData.Values)
            {
                if (points.Count > 0)
                {
                    var firstPoint = points.First().Timestamp;
                    var lastPoint = points.Last().Timestamp;
                    
                    if (!firstTrendTime.HasValue || firstPoint < firstTrendTime.Value)
                        firstTrendTime = firstPoint;
                    if (!lastTrendTime.HasValue || lastPoint > lastTrendTime.Value)
                        lastTrendTime = lastPoint;
                }
            }
            
            _logger.LogInformation($"Trimming complete. Returning {trendData.Count} tags with {maxPointsPerTag} points each. Time range: {firstTrendTime} to {lastTrendTime}");

            return trendData;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, $"Error reading trend data from Parquet file: {filePath}");
            return new Dictionary<string, List<TrendPoint>>();
        }
    }
}

public class LogDataResult
{
    public string FileName { get; set; } = "";
    public int RecordCount { get; set; }
    public List<LogRecord> Records { get; set; } = new();
}

public class LogFileSummary
{
    public string FileName { get; set; } = "";
    public long TotalRows { get; set; }
    public int TagCount { get; set; }
    public List<string> Tags { get; set; } = new();
    public DateTime? FirstTimestamp { get; set; }
    public DateTime? LastTimestamp { get; set; }
}

public class TrendPoint
{
    public DateTime Timestamp { get; set; }
    public string Value { get; set; } = "";
    public string Quality { get; set; } = "";
}
