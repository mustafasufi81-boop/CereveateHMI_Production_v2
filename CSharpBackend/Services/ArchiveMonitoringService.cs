using Parquet;
using Parquet.Data;
using System.Text.Json;

namespace OpcDaWebBrowser.Services;

/// <summary>
/// SAFE Archive Monitoring Service - 100% READ-ONLY
/// CRITICAL RULES:
/// - NEVER touches OPC server
/// - NEVER locks files being written
/// - NEVER scans large parquet files
/// - ONLY reads precomputed .meta.json files
/// - Uses FileShare.ReadWrite for zero interference
/// - Runs on separate thread pool
/// </summary>
public class ArchiveMonitoringService
{
    private readonly ILogger<ArchiveMonitoringService> _logger;
    private readonly IConfiguration _configuration;
    private readonly string _sourceParquetDirectory;
    private readonly string _archiveDirectory;
    private readonly string _archiveLogsPath;

    public ArchiveMonitoringService(
        ILogger<ArchiveMonitoringService> logger,
        IConfiguration configuration)
    {
        _logger = logger;
        _configuration = configuration;

        var sourceDir = configuration["LoggingPaths:DataLogDirectory"] ?? "D:\\OpcLogs\\Data";
        _sourceParquetDirectory = Path.IsPathRooted(sourceDir)
            ? sourceDir
            : Path.Combine(AppDomain.CurrentDomain.BaseDirectory, sourceDir);

        var archiveDir = configuration["LoggingPaths:BackupDirectory"] ?? "D:\\OpcLogs\\Backup";
        _archiveDirectory = Path.IsPathRooted(archiveDir)
            ? archiveDir
            : Path.Combine(AppDomain.CurrentDomain.BaseDirectory, archiveDir);

        var logsPath = configuration["LoggingPaths:ArchiveLogsPath"] ?? Path.Combine(_archiveDirectory, "Logs");
        _archiveLogsPath = Path.IsPathRooted(logsPath)
            ? logsPath
            : Path.Combine(AppDomain.CurrentDomain.BaseDirectory, logsPath);
    }

    /// <summary>
    /// Get source files (unarchived) - SAFE: Read-only, no locks
    /// </summary>
    public async Task<List<ParquetFileInfo>> GetSourceFilesAsync(CancellationToken cancellationToken = default)
    {
        return await Task.Run(() =>
        {
            var files = new List<ParquetFileInfo>();

            if (!Directory.Exists(_sourceParquetDirectory))
                return files;

            // Use EnumerateFiles for performance (streaming)
            foreach (var filePath in Directory.EnumerateFiles(_sourceParquetDirectory, "*.parquet"))
            {
                cancellationToken.ThrowIfCancellationRequested();

                try
                {
                    // Skip temp/backup files
                    if (filePath.EndsWith(".tmp") || filePath.EndsWith(".bak"))
                        continue;

                    var fileInfo = new FileInfo(filePath);
                    
                    // Quick metadata extraction (lightweight)
                    var info = GetQuickFileInfo(filePath);
                    files.Add(info);
                }
                catch (Exception ex)
                {
                    _logger.LogWarning($"Could not read source file {Path.GetFileName(filePath)}: {ex.Message}");
                }
            }

            return files.OrderByDescending(f => f.LastModified).ToList();
        }, cancellationToken);
    }

    /// <summary>
    /// Get archive files - SAFE: Uses cached metadata
    /// </summary>
    public async Task<List<ParquetFileInfo>> GetArchiveFilesAsync(CancellationToken cancellationToken = default)
    {
        return await Task.Run(() =>
        {
            var files = new List<ParquetFileInfo>();

            if (!Directory.Exists(_archiveDirectory))
                return files;

            foreach (var filePath in Directory.EnumerateFiles(_archiveDirectory, "Archive_*.parquet"))
            {
                cancellationToken.ThrowIfCancellationRequested();

                try
                {
                    if (filePath.EndsWith(".tmp") || filePath.EndsWith(".bak"))
                        continue;

                    // Try to load cached metadata first (ZERO parquet scanning)
                    var info = LoadCachedMetadata(filePath);
                    
                    if (info == null)
                    {
                        // Fallback to quick info (still lightweight)
                        info = GetQuickFileInfo(filePath);
                    }

                    files.Add(info);
                }
                catch (Exception ex)
                {
                    _logger.LogWarning($"Could not read archive file {Path.GetFileName(filePath)}: {ex.Message}");
                }
            }

            return files.OrderByDescending(f => f.LastModified).ToList();
        }, cancellationToken);
    }

    /// <summary>
    /// Load precomputed metadata (FASTEST - no parquet scanning)
    /// </summary>
    private ParquetFileInfo? LoadCachedMetadata(string parquetFile)
    {
        var metaFile = parquetFile + ".meta.json";
        
        if (!File.Exists(metaFile))
            return null;

        try
        {
            var json = File.ReadAllText(metaFile);
            var meta = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(json);
            
            if (meta == null)
                return null;

            return new ParquetFileInfo
            {
                FileName = meta.ContainsKey("fileName") ? meta["fileName"].GetString() ?? "" : "",
                FilePath = parquetFile,
                SizeBytes = meta.ContainsKey("sizeBytes") ? meta["sizeBytes"].GetInt64() : 0,
                SizeMB = meta.ContainsKey("sizeMB") ? meta["sizeMB"].GetDouble() : 0,
                LastModified = File.GetLastWriteTime(parquetFile),
                Rows = meta.ContainsKey("rows") ? meta["rows"].GetInt64() : 0,
                Columns = meta.ContainsKey("columns") ? meta["columns"].GetInt32() : 0,
                TotalValues = meta.ContainsKey("totalValues") ? meta["totalValues"].GetInt64() : 0,
                RowGroups = meta.ContainsKey("rowGroups") ? meta["rowGroups"].GetInt32() : 0,
                MinTimestamp = meta.ContainsKey("minTimestamp") ? meta["minTimestamp"].GetString() : null,
                MaxTimestamp = meta.ContainsKey("maxTimestamp") ? meta["maxTimestamp"].GetString() : null,
                HasMetadata = true
            };
        }
        catch
        {
            return null;
        }
    }

    /// <summary>
    /// Get quick file info without full parquet scan (SAFE)
    /// </summary>
    private ParquetFileInfo GetQuickFileInfo(string filePath)
    {
        var fileInfo = new FileInfo(filePath);
        
        return new ParquetFileInfo
        {
            FileName = fileInfo.Name,
            FilePath = filePath,
            SizeBytes = fileInfo.Length,
            SizeMB = Math.Round(fileInfo.Length / (1024.0 * 1024.0), 2),
            LastModified = fileInfo.LastWriteTime,
            HasMetadata = false
        };
    }

    /// <summary>
    /// Get detailed file info with schema (on-demand, still SAFE)
    /// </summary>
    public async Task<ParquetFileDetails?> GetFileDetailsAsync(string fileName, bool isArchive, CancellationToken cancellationToken = default)
    {
        return await Task.Run(async () =>
        {
            try
            {
                var directory = isArchive ? _archiveDirectory : _sourceParquetDirectory;
                var filePath = Path.Combine(directory, fileName);

                if (!File.Exists(filePath))
                    return null;

                // SAFE: Read-only with FileShare.ReadWrite (no locks)
                using var fileStream = File.Open(filePath, FileMode.Open, FileAccess.Read, FileShare.ReadWrite);
                using var reader = await ParquetReader.CreateAsync(fileStream, cancellationToken: cancellationToken);

                var schema = reader.Schema;
                long totalRows = 0;

                for (int i = 0; i < reader.RowGroupCount; i++)
                {
                    using var groupReader = reader.OpenRowGroupReader(i);
                    totalRows += groupReader.RowCount;
                }

                return new ParquetFileDetails
                {
                    FileName = fileName,
                    SizeBytes = new FileInfo(filePath).Length,
                    SizeMB = Math.Round(new FileInfo(filePath).Length / (1024.0 * 1024.0), 2),
                    Rows = totalRows,
                    Columns = schema.GetDataFields().Length,
                    TotalValues = totalRows * schema.GetDataFields().Length,
                    RowGroups = reader.RowGroupCount,
                    Schema = schema.GetDataFields().Select(f => new SchemaField
                    {
                        Name = f.Name,
                        Type = f.ClrType.Name,
                        SchemaType = f.SchemaType.ToString()
                    }).ToList()
                };
            }
            catch (Exception ex)
            {
                _logger.LogError($"Error getting file details: {ex.Message}");
                return null;
            }
        }, cancellationToken);
    }

    /// <summary>
    /// Preview first N rows (SAFE: limited rows only)
    /// </summary>
    public async Task<ParquetPreview?> PreviewFileAsync(string fileName, bool isArchive, int maxRows = 100, CancellationToken cancellationToken = default)
    {
        return await Task.Run(async () =>
        {
            try
            {
                var directory = isArchive ? _archiveDirectory : _sourceParquetDirectory;
                var filePath = Path.Combine(directory, fileName);

                if (!File.Exists(filePath))
                    return null;

                using var fileStream = File.Open(filePath, FileMode.Open, FileAccess.Read, FileShare.ReadWrite);
                using var reader = await ParquetReader.CreateAsync(fileStream, cancellationToken: cancellationToken);

                var schema = reader.Schema.GetDataFields();
                var rows = new List<Dictionary<string, object?>>();
                int rowsRead = 0;

                // Read first row group only for preview
                if (reader.RowGroupCount > 0)
                {
                    using var groupReader = reader.OpenRowGroupReader(0);
                    var columns = new Dictionary<string, Array>();

                    // Read all columns
                    foreach (var field in schema)
                    {
                        var column = await groupReader.ReadColumnAsync(field, cancellationToken);
                        columns[field.Name] = column.Data;
                    }

                    // Build rows (limited)
                    var rowCount = Math.Min((int)groupReader.RowCount, maxRows);
                    for (int i = 0; i < rowCount; i++)
                    {
                        var row = new Dictionary<string, object?>();
                        foreach (var field in schema)
                        {
                            var array = columns[field.Name];
                            row[field.Name] = array.GetValue(i);
                        }
                        rows.Add(row);
                        rowsRead++;
                    }
                }

                return new ParquetPreview
                {
                    FileName = fileName,
                    TotalRowsInFile = reader.RowGroupCount > 0 ? rows.Count : 0,
                    RowsReturned = rowsRead,
                    Columns = schema.Select(f => f.Name).ToList(),
                    Rows = rows
                };
            }
            catch (Exception ex)
            {
                _logger.LogError($"Error previewing file: {ex.Message}");
                return null;
            }
        }, cancellationToken);
    }

    /// <summary>
    /// Get log files (SAFE: read-only)
    /// </summary>
    public async Task<List<LogFileInfo>> GetLogFilesAsync(CancellationToken cancellationToken = default)
    {
        return await Task.Run(() =>
        {
            var logs = new List<LogFileInfo>();

            if (!Directory.Exists(_archiveLogsPath))
                return logs;

            foreach (var filePath in Directory.EnumerateFiles(_archiveLogsPath, "Archive_*.log"))
            {
                try
                {
                    var fileInfo = new FileInfo(filePath);
                    logs.Add(new LogFileInfo
                    {
                        FileName = fileInfo.Name,
                        FilePath = filePath,
                        SizeBytes = fileInfo.Length,
                        LastModified = fileInfo.LastWriteTime
                    });
                }
                catch { }
            }

            return logs.OrderByDescending(l => l.LastModified).ToList();
        }, cancellationToken);
    }

    /// <summary>
    /// Read log file with search (SAFE: limited lines)
    /// </summary>
    public async Task<LogFileContent> ReadLogFileAsync(string fileName, string? searchTerm = null, int maxLines = 1000, CancellationToken cancellationToken = default)
    {
        return await Task.Run(() =>
        {
            var filePath = Path.Combine(_archiveLogsPath, fileName);
            var lines = new List<LogEntry>();

            if (!File.Exists(filePath))
                return new LogFileContent { FileName = fileName, Lines = lines };

            try
            {
                var allLines = File.ReadAllLines(filePath);
                var filteredLines = string.IsNullOrWhiteSpace(searchTerm)
                    ? allLines
                    : allLines.Where(line => line.Contains(searchTerm, StringComparison.OrdinalIgnoreCase));

                foreach (var line in filteredLines.Take(maxLines))
                {
                    var level = GetLogLevel(line);
                    lines.Add(new LogEntry
                    {
                        Timestamp = ExtractTimestamp(line),
                        Level = level,
                        Message = line,
                        Color = GetLogColor(level)
                    });
                }
            }
            catch (Exception ex)
            {
                _logger.LogError($"Error reading log file: {ex.Message}");
            }

            return new LogFileContent { FileName = fileName, Lines = lines, TotalLines = lines.Count };
        }, cancellationToken);
    }

    private string GetLogLevel(string line)
    {
        if (line.Contains("ERROR")) return "ERROR";
        if (line.Contains("WARNING") || line.Contains("SKIP")) return "WARNING";
        if (line.Contains("SUCCESS")) return "SUCCESS";
        return "INFO";
    }

    private string GetLogColor(string level)
    {
        return level switch
        {
            "ERROR" => "red",
            "WARNING" => "orange",
            "SUCCESS" => "green",
            _ => "blue"
        };
    }

    private string ExtractTimestamp(string line)
    {
        // Extract [YYYY-MM-DD HH:MM:SS.fff] from log line
        var start = line.IndexOf('[');
        var end = line.IndexOf(']');
        if (start >= 0 && end > start)
            return line.Substring(start + 1, end - start - 1);
        return "";
    }
}

// ===== MODELS FOR SAFE MONITORING =====

public class ParquetFileInfo
{
    public string FileName { get; set; } = "";
    public string FilePath { get; set; } = "";
    public long SizeBytes { get; set; }
    public double SizeMB { get; set; }
    public DateTime LastModified { get; set; }
    public long Rows { get; set; }
    public int Columns { get; set; }
    public long TotalValues { get; set; }
    public int RowGroups { get; set; }
    public string? MinTimestamp { get; set; }
    public string? MaxTimestamp { get; set; }
    public bool HasMetadata { get; set; }
}

public class ParquetFileDetails
{
    public string FileName { get; set; } = "";
    public long SizeBytes { get; set; }
    public double SizeMB { get; set; }
    public long Rows { get; set; }
    public int Columns { get; set; }
    public long TotalValues { get; set; }
    public int RowGroups { get; set; }
    public List<SchemaField> Schema { get; set; } = new();
}

public class SchemaField
{
    public string Name { get; set; } = "";
    public string Type { get; set; } = "";
    public string SchemaType { get; set; } = "";
}

public class ParquetPreview
{
    public string FileName { get; set; } = "";
    public int TotalRowsInFile { get; set; }
    public int RowsReturned { get; set; }
    public List<string> Columns { get; set; } = new();
    public List<Dictionary<string, object?>> Rows { get; set; } = new();
}

public class LogFileInfo
{
    public string FileName { get; set; } = "";
    public string FilePath { get; set; } = "";
    public long SizeBytes { get; set; }
    public DateTime LastModified { get; set; }
}

public class LogFileContent
{
    public string FileName { get; set; } = "";
    public List<LogEntry> Lines { get; set; } = new();
    public int TotalLines { get; set; }
}

public class LogEntry
{
    public string Timestamp { get; set; } = "";
    public string Level { get; set; } = "";
    public string Message { get; set; } = "";
    public string Color { get; set; } = "";
}
