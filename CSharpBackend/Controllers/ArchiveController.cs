using Microsoft.AspNetCore.Mvc;
using OpcDaWebBrowser.Services;
using Parquet;
using System.Text;
using System.IO.Compression;
using System.Text.Json;

namespace OpcDaWebBrowser.Controllers;

/// <summary>
/// API Controller for Parquet Archive Management
/// - View archive files and logs
/// - Convert parquet to CSV (streaming for large files)
/// - Extract date ranges
/// - Statistics and monitoring
/// </summary>
[ApiController]
[Route("api/[controller]")]
public class ArchiveController : ControllerBase
{
    private readonly LogBackupService _archiveService;
    private readonly ILogger<ArchiveController> _logger;
    private readonly IConfiguration _configuration;
    private readonly string _loggingConfigPath;
    private const string UnsafePathError = "Invalid file name";

    public ArchiveController(
        LogBackupService archiveService,
        ILogger<ArchiveController> logger,
        IConfiguration configuration)
    {
        _archiveService = archiveService;
        _logger = logger;
        _configuration = configuration;
        _loggingConfigPath = Path.Combine(AppContext.BaseDirectory, "logging-config.json");
    }

    /// <summary>
    /// Get parquet tag coverage metrics: mapped vs observed + quality breakdown
    /// Uses latest archive parquet file to keep the scan lightweight
    /// </summary>
    [HttpGet("tag-coverage")]
    public async Task<IActionResult> GetParquetTagCoverage()
    {
        try
        {
            var archiveDir = _configuration["BackupDirectory"] ?? "D:\\OpcLogs\\Backup";
            var files = Directory.Exists(archiveDir)
                ? Directory.GetFiles(archiveDir, "Archive_*.parquet")
                    .OrderByDescending(f => new FileInfo(f).LastWriteTimeUtc)
                    .ToList()
                : new List<string>();

            if (files.Count == 0)
            {
                return Ok(new
                {
                    mappedTags = GetSelectedTags(),
                    observedTags = new List<string>(),
                    counts = new { mapped = 0, observed = 0, missing = 0 },
                    quality = new { good = 0, bad = 0, uncertain = 0, available = false },
                    sourceFile = (string?)null,
                    rowCount = 0
                });
            }

            var latestFile = files.First();
            var selectedTags = GetSelectedTags();
            var observedTags = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

            int good = 0, bad = 0, uncertain = 0;
            long rowCount = 0;
            bool qualityAvailable = false;

            using var stream = System.IO.File.OpenRead(latestFile);
            using var reader = await ParquetReader.CreateAsync(stream);
            var fields = reader.Schema.GetDataFields();

            var tagField = fields.FirstOrDefault(f => f.Name.Equals("TagId", StringComparison.OrdinalIgnoreCase))
                           ?? fields.FirstOrDefault(f => f.Name.Contains("Tag", StringComparison.OrdinalIgnoreCase));
            if (tagField == null)
            {
                return Ok(new
                {
                    mappedTags = selectedTags,
                    observedTags = Array.Empty<string>(),
                    counts = new { mapped = selectedTags.Count, observed = 0, missing = selectedTags.Count },
                    quality = new { good = 0, bad = 0, uncertain = 0, available = false },
                    sourceFile = Path.GetFileName(latestFile),
                    rowCount
                });
            }

            var qualityField = fields.FirstOrDefault(f => f.Name.Contains("Quality", StringComparison.OrdinalIgnoreCase));
            qualityAvailable = qualityField != null;

            for (int i = 0; i < reader.RowGroupCount; i++)
            {
                using var rowGroup = reader.OpenRowGroupReader(i);
                var tagColumn = await rowGroup.ReadColumnAsync(tagField);
                var tagData = tagColumn.Data;
                Array? qualityData = null;

                if (qualityField != null)
                {
                    var qc = await rowGroup.ReadColumnAsync(qualityField);
                    qualityData = qc.Data;
                }

                rowCount += tagData.Length;

                for (int idx = 0; idx < tagData.Length; idx++)
                {
                    var tagVal = tagData.GetValue(idx)?.ToString();
                    if (!string.IsNullOrWhiteSpace(tagVal))
                    {
                        observedTags.Add(tagVal);
                    }

                    if (qualityData != null)
                    {
                        var q = qualityData.GetValue(idx);
                        if (q != null)
                        {
                            var qs = q.ToString()?.ToUpperInvariant();
                            if (qs is not null)
                            {
                                if (qs.Contains("GOOD")) good++;
                                else if (qs.Contains("BAD")) bad++;
                                else uncertain++;
                            }
                        }
                    }
                }
            }

            var missing = selectedTags.Count == 0 ? 0 : selectedTags.Count(tag => !observedTags.Contains(tag));

            return Ok(new
            {
                mappedTags = selectedTags,
                observedTags = observedTags.ToArray(),
                counts = new
                {
                    mapped = selectedTags.Count,
                    observed = observedTags.Count,
                    missing
                },
                quality = new
                {
                    good,
                    bad,
                    uncertain,
                    available = qualityAvailable
                },
                sourceFile = Path.GetFileName(latestFile),
                rowCount
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error calculating parquet tag coverage");
            return StatusCode(500, new { error = ex.Message });
        }
    }

    private List<string> GetSelectedTags()
    {
        try
        {
            if (System.IO.File.Exists(_loggingConfigPath))
            {
                var json = System.IO.File.ReadAllText(_loggingConfigPath);
                using var doc = System.Text.Json.JsonDocument.Parse(json);
                if (doc.RootElement.TryGetProperty("SelectedTags", out var arr) && arr.ValueKind == System.Text.Json.JsonValueKind.Array)
                {
                    return arr.EnumerateArray()
                        .Where(e => e.ValueKind == System.Text.Json.JsonValueKind.String)
                        .Select(e => e.GetString()!)
                        .Where(s => !string.IsNullOrWhiteSpace(s))
                        .Distinct(StringComparer.OrdinalIgnoreCase)
                        .ToList();
                }
            }
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Unable to read SelectedTags from logging-config.json");
        }
        return new List<string>();
    }

    /// <summary>
    /// Get archive statistics and file list
    /// </summary>
    [HttpGet("stats")]
    public IActionResult GetArchiveStats()
    {
        try
        {
            var archiveDir = _configuration["BackupDirectory"] ?? "D:\\OpcLogs\\Backup";
            var logsDir = _configuration["ArchiveLogsPath"] ?? Path.Combine(archiveDir, "Logs");

            if (!Directory.Exists(archiveDir))
            {
                return Ok(new { archiveFiles = new List<object>(), logFiles = new List<object>(), totalSizeMB = 0, fileCount = 0 });
            }

            var archiveFiles = Directory.GetFiles(archiveDir, "Archive_*.parquet")
                .Select(f => new FileInfo(f))
                .OrderByDescending(f => f.LastWriteTime)
                .Select(f => new
                {
                    name = f.Name,
                    sizeMB = Math.Round(f.Length / (1024.0 * 1024.0), 2),
                    sizeBytes = f.Length,
                    created = f.CreationTime.ToString("yyyy-MM-dd HH:mm:ss"),
                    modified = f.LastWriteTime.ToString("yyyy-MM-dd HH:mm:ss"),
                    path = f.FullName
                })
                .ToList();

            var logFiles = Directory.Exists(logsDir)
                ? Directory.GetFiles(logsDir, "Archive_*.log")
                    .Select(f => new FileInfo(f))
                    .OrderByDescending(f => f.LastWriteTime)
                    .Select(f => new
                    {
                        name = f.Name,
                        sizeKB = Math.Round(f.Length / 1024.0, 2),
                        modified = f.LastWriteTime.ToString("yyyy-MM-dd HH:mm:ss"),
                        path = f.FullName
                    })
                    .ToList<object>()
                : new List<object>();

            var totalSizeMB = archiveFiles.Sum(f => f.sizeMB);

            return Ok(new
            {
                archiveFiles,
                logFiles,
                totalSizeMB = Math.Round(totalSizeMB, 2),
                fileCount = archiveFiles.Count,
                archiveDirectory = archiveDir,
                logsDirectory = logsDir
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error getting archive stats");
            return StatusCode(500, new { error = ex.Message });
        }
    }

    /// <summary>
    /// Get log file content
    /// </summary>
    [HttpGet("log/{fileName}")]
    public IActionResult GetLogContent(string fileName)
    {
        try
        {
            var logsDir = _configuration["LoggingPaths:ArchiveLogsPath"] ?? "D:\\OpcLogs\\Backup\\Logs";

            if (!TryGetSafePath(logsDir, fileName, out var logPath))
            {
                return BadRequest(new { error = UnsafePathError });
            }

            if (!System.IO.File.Exists(logPath))
            {
                return NotFound(new { error = "Log file not found" });
            }

            var content = System.IO.File.ReadAllText(logPath);
            return Ok(new { fileName, content, lines = content.Split('\n').Length });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, $"Error reading log file {fileName}");
            return StatusCode(500, new { error = ex.Message });
        }
    }

    /// <summary>
    /// Get parquet file info (row count, columns, date range)
    /// </summary>
    [HttpGet("info/{fileName}")]
    public async Task<IActionResult> GetParquetInfo(string fileName)
    {
        try
        {
            var archiveDir = _configuration["BackupDirectory"] ?? "D:\\OpcLogs\\Backup";

            if (!TryGetSafePath(archiveDir, fileName, out var filePath))
            {
                return BadRequest(new { error = UnsafePathError });
            }

            if (!System.IO.File.Exists(filePath))
            {
                return NotFound(new { error = "Archive file not found" });
            }

            using var stream = System.IO.File.OpenRead(filePath);
            using var reader = await ParquetReader.CreateAsync(stream);

            var fields = reader.Schema.GetDataFields();
            var columnNames = fields.Select(f => f.Name).ToList();

            // Calculate total rows across all row groups
            DateTime? minDate = null, maxDate = null;
            long totalRows = 0;

            for (int i = 0; i < reader.RowGroupCount; i++)
            {
                using var rowGroup = reader.OpenRowGroupReader(i);
                
                // Get row count from first column (all columns have same row count)
                var firstColumn = await rowGroup.ReadColumnAsync(fields[0]);
                totalRows += firstColumn.Data.Length;
                
                // Get date range from timestamp field if exists
                var timestampField = fields.FirstOrDefault(f => f.Name.Contains("Time", StringComparison.OrdinalIgnoreCase));
                if (timestampField != null)
                {
                    var column = await rowGroup.ReadColumnAsync(timestampField);
                    if (column.Data.Length > 0)
                    {
                        var firstVal = column.Data.GetValue(0);
                        var lastVal = column.Data.GetValue(column.Data.Length - 1);
                        
                        if (firstVal is DateTime dt1)
                        {
                            if (minDate == null || dt1 < minDate) minDate = dt1;
                        }
                        if (lastVal is DateTime dt2)
                        {
                            if (maxDate == null || dt2 > maxDate) maxDate = dt2;
                        }
                    }
                }
            }

            var fileInfo = new FileInfo(filePath);

            return Ok(new
            {
                fileName,
                rowCount = totalRows,
                columnCount = columnNames.Count,
                columns = columnNames,
                minDate = minDate?.ToString("yyyy-MM-dd HH:mm:ss"),
                maxDate = maxDate?.ToString("yyyy-MM-dd HH:mm:ss"),
                sizeMB = Math.Round(fileInfo.Length / (1024.0 * 1024.0), 2),
                rowGroupCount = reader.RowGroupCount
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, $"Error reading parquet info {fileName}");
            return StatusCode(500, new { error = ex.Message });
        }
    }

    /// <summary>
    /// Convert parquet to CSV with smart splitting for large files
    /// Returns ZIP with multiple CSV files if data is large (>100k rows per file)
    /// </summary>
    [HttpPost("convert")]
    public async Task<IActionResult> ConvertToCsv([FromBody] ConvertRequest request)
    {
        try
        {
            var archiveDir = _configuration["BackupDirectory"] ?? "D:\\OpcLogs\\Backup";
            if (!TryGetSafePath(archiveDir, request.FileName, out var filePath))
            {
                return BadRequest(new { error = UnsafePathError });
            }

            if (!System.IO.File.Exists(filePath))
            {
                return NotFound(new { error = "Archive file not found" });
            }

            DateTime? filterStart = !string.IsNullOrEmpty(request.StartDate) ? DateTime.Parse(request.StartDate) : null;
            DateTime? filterEnd = !string.IsNullOrEmpty(request.EndDate) ? DateTime.Parse(request.EndDate) : null;
            var selectedColumns = request.Columns?.Where(c => !string.IsNullOrEmpty(c)).ToList();

            const int ROWS_PER_CSV = 100000; // Split into 100k rows per CSV
            var csvFiles = new List<string>();
            var baseFileName = Path.GetFileNameWithoutExtension(request.FileName);
            var tempDir = Path.Combine(archiveDir, $"temp_{Guid.NewGuid():N}");
            Directory.CreateDirectory(tempDir);

            try
            {
                // Stream conversion (memory-efficient for large files)
                using var stream = System.IO.File.OpenRead(filePath);
                using var reader = await ParquetReader.CreateAsync(stream);

                var fields = reader.Schema.GetDataFields();
                var columnsToExport = selectedColumns != null && selectedColumns.Count > 0
                    ? fields.Where(f => selectedColumns.Contains(f.Name, StringComparer.OrdinalIgnoreCase)).ToArray()
                    : fields;

                long totalRowsWritten = 0;
                int fileIndex = 1;
                StreamWriter? writer = null;
                string? currentCsvPath = null;
                long currentFileRows = 0;
                var timestampField = fields.FirstOrDefault(f => f.Name.Contains("Time", StringComparison.OrdinalIgnoreCase));

                for (int i = 0; i < reader.RowGroupCount; i++)
                {
                    using var rowGroup = reader.OpenRowGroupReader(i);
                    
                    // Read all columns for this row group
                    var columnData = new Dictionary<string, Array>();
                    foreach (var field in columnsToExport)
                    {
                        var column = await rowGroup.ReadColumnAsync(field);
                        columnData[field.Name] = column.Data;
                    }

                    var rowCount = columnData.First().Value.Length;

                    for (int row = 0; row < rowCount; row++)
                    {
                        // Check if we need a new CSV file
                        if (writer == null || currentFileRows >= ROWS_PER_CSV)
                        {
                            if (writer != null)
                            {
                                await writer.FlushAsync();
                                writer.Dispose();
                            }

                            currentCsvPath = Path.Combine(tempDir, $"{baseFileName}_part{fileIndex}.csv");
                            csvFiles.Add(currentCsvPath);
                            writer = new StreamWriter(currentCsvPath, false, Encoding.UTF8);
                            
                            // Write CSV header
                            await writer.WriteLineAsync(string.Join(",", columnsToExport.Select(f => EscapeCsv(f.Name))));
                            currentFileRows = 0;
                            fileIndex++;
                        }

                        // Date filter
                        if (timestampField != null && (filterStart != null || filterEnd != null))
                        {
                            var timestampData = columnData.ContainsKey(timestampField.Name) 
                                ? columnData[timestampField.Name].GetValue(row)
                                : null;
                            
                            if (timestampData is DateTime dt)
                            {
                                if (filterStart != null && dt < filterStart) continue;
                                if (filterEnd != null && dt > filterEnd) continue;
                            }
                        }

                        // Build CSV row
                        var values = columnsToExport.Select(f => 
                        {
                            var val = columnData[f.Name].GetValue(row);
                            return EscapeCsv(val?.ToString() ?? "");
                        });

                        await writer.WriteLineAsync(string.Join(",", values));
                        currentFileRows++;
                        totalRowsWritten++;
                    }
                }

                writer?.Dispose();

                // Create ZIP if multiple files or single large file
                string resultFile;
                double resultSizeMB;
                
                if (csvFiles.Count > 1 || totalRowsWritten > ROWS_PER_CSV)
                {
                    // Create ZIP with all CSV files
                    var zipFileName = $"{baseFileName}_CSV.zip";
                    var zipPath = Path.Combine(archiveDir, zipFileName);
                    
                    if (System.IO.File.Exists(zipPath))
                        System.IO.File.Delete(zipPath);
                    
                    using (var zipArchive = ZipFile.Open(zipPath, ZipArchiveMode.Create))
                    {
                        foreach (var csvFile in csvFiles)
                        {
                            zipArchive.CreateEntryFromFile(csvFile, Path.GetFileName(csvFile));
                        }
                    }
                    
                    resultFile = zipFileName;
                    resultSizeMB = Math.Round(new FileInfo(zipPath).Length / (1024.0 * 1024.0), 2);
                }
                else
                {
                    // Single small CSV - move to archive directory
                    var csvFileName = $"{baseFileName}.csv";
                    var csvPath = Path.Combine(archiveDir, csvFileName);
                    
                    if (System.IO.File.Exists(csvPath))
                        System.IO.File.Delete(csvPath);
                    
                    System.IO.File.Move(csvFiles[0], csvPath);
                    resultFile = csvFileName;
                    resultSizeMB = Math.Round(new FileInfo(csvPath).Length / (1024.0 * 1024.0), 2);
                }

                // Cleanup temp directory
                Directory.Delete(tempDir, true);

                return Ok(new
                {
                    success = true,
                    resultFile,
                    filesCreated = csvFiles.Count,
                    totalRowsWritten,
                    sizeMB = resultSizeMB,
                    isZipped = csvFiles.Count > 1,
                    downloadPath = Path.Combine(archiveDir, resultFile),
                    message = csvFiles.Count > 1 
                        ? $"Created {csvFiles.Count} CSV files ({totalRowsWritten:N0} rows) in ZIP archive"
                        : $"Created 1 CSV file ({totalRowsWritten:N0} rows)"
                });
            }
            catch
            {
                // Cleanup on error
                if (Directory.Exists(tempDir))
                    Directory.Delete(tempDir, true);
                throw;
            }
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, $"Error converting {request.FileName} to CSV");
            return StatusCode(500, new { error = ex.Message });
        }
    }

    /// <summary>
    /// Download CSV file
    /// </summary>
    [HttpGet("download/{fileName}")]
    public IActionResult DownloadCsv(string fileName)
    {
        try
        {
            var archiveDir = _configuration["BackupDirectory"] ?? "D:\\OpcLogs\\Backup";
            if (!TryGetSafePath(archiveDir, fileName, out var filePath))
            {
                return BadRequest(new { error = UnsafePathError });
            }

            if (!System.IO.File.Exists(filePath))
            {
                return NotFound(new { error = "File not found" });
            }

            var stream = System.IO.File.OpenRead(filePath);
            return File(stream, "text/csv", fileName);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, $"Error downloading {fileName}");
            return StatusCode(500, new { error = ex.Message });
        }
    }

    private bool TryGetSafePath(string baseDirectory, string fileName, out string fullPath)
    {
        fullPath = string.Empty;
        if (string.IsNullOrWhiteSpace(fileName)) return false;

        var sanitizedName = Path.GetFileName(fileName);
        if (string.IsNullOrWhiteSpace(sanitizedName)) return false;

        var baseFull = Path.GetFullPath(baseDirectory);
        var combined = Path.GetFullPath(Path.Combine(baseFull, sanitizedName));

        if (!combined.StartsWith(baseFull, StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        fullPath = combined;
        return true;
    }

    private string EscapeCsv(string value)
    {
        if (string.IsNullOrEmpty(value))
            return "";

        if (value.Contains(',') || value.Contains('"') || value.Contains('\n'))
        {
            return $"\"{value.Replace("\"", "\"\"")}\"";
        }

        return value;
    }

    /// <summary>
    /// Compress archive files by date range into ZIP
    /// Validation: Must select unused files, minimum 1 day old, maximum 1 month range
    /// </summary>
    [HttpPost("compress")]
    public async Task<IActionResult> CompressArchives([FromBody] CompressRequest request)
    {
        try
        {
            // Validate date range
            if (!DateTime.TryParse(request.StartDate, out var startDate) || 
                !DateTime.TryParse(request.EndDate, out var endDate))
            {
                return BadRequest(new { error = "Invalid date format" });
            }

            // Validation: End date must be at least 1 day old
            var oneDayAgo = DateTime.Now.AddDays(-1);
            if (endDate > oneDayAgo)
            {
                return BadRequest(new { 
                    error = "End date must be at least 1 day old (cannot compress recent files)",
                    maxAllowedDate = oneDayAgo.ToString("yyyy-MM-dd")
                });
            }

            // Validation: Date range cannot exceed 1 month
            var daysDiff = (endDate - startDate).TotalDays;
            if (daysDiff > 31)
            {
                return BadRequest(new { 
                    error = "Date range cannot exceed 1 month (31 days)",
                    rangeSelected = $"{daysDiff:F0} days"
                });
            }

            if (daysDiff < 0)
            {
                return BadRequest(new { error = "Start date must be before end date" });
            }

            // Call service compression method
            var result = await _archiveService.CompressArchivesByDateRange(startDate, endDate, CancellationToken.None);

            if (result.Success && result.FilesCompressed > 0)
            {
                return Ok(new
                {
                    success = true,
                    zipFile = result.ZipFileName,
                    filesCompressed = result.FilesCompressed,
                    originalSizeMB = result.OriginalSizeMB,
                    compressedSizeMB = result.CompressedSizeMB,
                    compressionRatio = result.CompressionRatio,
                    message = result.Message
                });
            }
            else
            {
                return Ok(new
                {
                    success = false,
                    message = result.Message,
                    filesFound = result.FilesCompressed
                });
            }
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error compressing archives");
            return StatusCode(500, new { error = ex.Message });
        }
    }

    /// <summary>
    /// List available ZIP compressed archives
    /// </summary>
    [HttpGet("compressed")]
    public IActionResult GetCompressedArchives()
    {
        try
        {
            var archiveDir = _configuration["BackupDirectory"] ?? "D:\\OpcLogs\\Backup";

            if (!Directory.Exists(archiveDir))
            {
                return Ok(new { files = new List<object>() });
            }

            var zipFiles = Directory.GetFiles(archiveDir, "ArchiveCompressed_*.zip")
                .Select(f => new FileInfo(f))
                .OrderByDescending(f => f.LastWriteTime)
                .Select(f => new
                {
                    name = f.Name,
                    sizeMB = Math.Round(f.Length / (1024.0 * 1024.0), 2),
                    created = f.CreationTime.ToString("yyyy-MM-dd HH:mm:ss"),
                    modified = f.LastWriteTime.ToString("yyyy-MM-dd HH:mm:ss"),
                    path = f.FullName
                })
                .ToList();

            return Ok(new { files = zipFiles });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error getting compressed archives");
            return StatusCode(500, new { error = ex.Message });
        }
    }
}

public class CompressRequest
{
    public string StartDate { get; set; } = "";
    public string EndDate { get; set; } = "";
}

public class ConvertRequest
{
    public string FileName { get; set; } = "";
    public string? StartDate { get; set; }
    public string? EndDate { get; set; }
    public List<string>? Columns { get; set; }
}
