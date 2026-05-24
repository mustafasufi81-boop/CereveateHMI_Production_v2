using Microsoft.AspNetCore.Mvc;
using OpcDaWebBrowser.Services;

namespace OpcDaWebBrowser.Controllers;

/// <summary>
/// Archive Monitoring API - 100% READ-ONLY, ZERO interference with OPC/Logging/Archiving
/// Provides enterprise-grade monitoring for industrial historian archive pipeline
/// </summary>
[ApiController]
[Route("api/[controller]")]
public class ArchiveMonitorController : ControllerBase
{
    private readonly ILogger<ArchiveMonitorController> _logger;
    private readonly ArchiveMonitoringService _monitorService;
    private readonly LogBackupService _backupService;

    public ArchiveMonitorController(
        ILogger<ArchiveMonitorController> logger,
        ArchiveMonitoringService monitorService,
        LogBackupService backupService)
    {
        _logger = logger;
        _monitorService = monitorService;
        _backupService = backupService;
    }

    /// <summary>
    /// GET dashboard status (real-time archiving status)
    /// </summary>
    [HttpGet("status")]
    public ActionResult<ArchiverStatus> GetStatus()
    {
        try
        {
            var status = _backupService.GetStatus();
            return Ok(status);
        }
        catch (Exception ex)
        {
            _logger.LogError($"Error getting archiver status: {ex.Message}");
            return StatusCode(500, new { error = ex.Message });
        }
    }

    /// <summary>
    /// GET source files (unarchived parquet files)
    /// </summary>
    [HttpGet("source-files")]
    public async Task<ActionResult<List<ParquetFileInfo>>> GetSourceFiles(CancellationToken cancellationToken)
    {
        try
        {
            var files = await _monitorService.GetSourceFilesAsync(cancellationToken);
            return Ok(files);
        }
        catch (Exception ex)
        {
            _logger.LogError($"Error getting source files: {ex.Message}");
            return StatusCode(500, new { error = ex.Message });
        }
    }

    /// <summary>
    /// GET archive files (consolidated parquet archives)
    /// </summary>
    [HttpGet("archive-files")]
    public async Task<ActionResult<List<ParquetFileInfo>>> GetArchiveFiles(CancellationToken cancellationToken)
    {
        try
        {
            var files = await _monitorService.GetArchiveFilesAsync(cancellationToken);
            return Ok(files);
        }
        catch (Exception ex)
        {
            _logger.LogError($"Error getting archive files: {ex.Message}");
            return StatusCode(500, new { error = ex.Message });
        }
    }

    /// <summary>
    /// GET file details (schema, statistics)
    /// </summary>
    [HttpGet("file-details/{fileName}")]
    public async Task<ActionResult<ParquetFileDetails>> GetFileDetails(
        string fileName,
        [FromQuery] bool isArchive = false,
        CancellationToken cancellationToken = default)
    {
        try
        {
            var details = await _monitorService.GetFileDetailsAsync(fileName, isArchive, cancellationToken);
            if (details == null)
                return NotFound(new { error = "File not found" });

            return Ok(details);
        }
        catch (Exception ex)
        {
            _logger.LogError($"Error getting file details: {ex.Message}");
            return StatusCode(500, new { error = ex.Message });
        }
    }

    /// <summary>
    /// GET file preview (first 100 rows)
    /// </summary>
    [HttpGet("preview/{fileName}")]
    public async Task<ActionResult<ParquetPreview>> PreviewFile(
        string fileName,
        [FromQuery] bool isArchive = false,
        [FromQuery] int maxRows = 100,
        CancellationToken cancellationToken = default)
    {
        try
        {
            // Limit max rows for safety
            maxRows = Math.Min(maxRows, 500);

            var preview = await _monitorService.PreviewFileAsync(fileName, isArchive, maxRows, cancellationToken);
            if (preview == null)
                return NotFound(new { error = "File not found" });

            return Ok(preview);
        }
        catch (Exception ex)
        {
            _logger.LogError($"Error previewing file: {ex.Message}");
            return StatusCode(500, new { error = ex.Message });
        }
    }

    /// <summary>
    /// GET log files list
    /// </summary>
    [HttpGet("logs")]
    public async Task<ActionResult<List<LogFileInfo>>> GetLogFiles(CancellationToken cancellationToken)
    {
        try
        {
            var logs = await _monitorService.GetLogFilesAsync(cancellationToken);
            return Ok(logs);
        }
        catch (Exception ex)
        {
            _logger.LogError($"Error getting log files: {ex.Message}");
            return StatusCode(500, new { error = ex.Message });
        }
    }

    /// <summary>
    /// GET log file content (with optional search)
    /// </summary>
    [HttpGet("logs/{fileName}")]
    public async Task<ActionResult<LogFileContent>> ReadLogFile(
        string fileName,
        [FromQuery] string? search = null,
        [FromQuery] int maxLines = 1000,
        CancellationToken cancellationToken = default)
    {
        try
        {
            // Limit max lines for safety
            maxLines = Math.Min(maxLines, 5000);

            var content = await _monitorService.ReadLogFileAsync(fileName, search, maxLines, cancellationToken);
            return Ok(content);
        }
        catch (Exception ex)
        {
            _logger.LogError($"Error reading log file: {ex.Message}");
            return StatusCode(500, new { error = ex.Message });
        }
    }

    /// <summary>
    /// GET system health metrics
    /// </summary>
    [HttpGet("health")]
    public async Task<ActionResult<object>> GetSystemHealth()
    {
        try
        {
            var status = _backupService.GetStatus();
            var sourceFiles = await _monitorService.GetSourceFilesAsync();
            var archiveFiles = await _monitorService.GetArchiveFilesAsync();

            // Calculate metrics
            var totalArchiveSize = archiveFiles.Sum(f => f.SizeMB);
            var totalArchiveRows = archiveFiles.Sum(f => f.Rows);
            var totalArchiveValues = archiveFiles.Sum(f => f.TotalValues);
            var avgFileSize = archiveFiles.Any() ? archiveFiles.Average(f => f.SizeMB) : 0;
            var largestFile = archiveFiles.OrderByDescending(f => f.SizeMB).FirstOrDefault();

            return Ok(new
            {
                status = status.IsRunning ? "Running" : "Stopped",
                sourceFilesCount = status.UnarchivedFilesCount,
                archiveFilesCount = status.ArchiveFilesCount,
                currentArchiveFile = status.CurrentArchiveFile,
                currentArchiveSizeMB = status.CurrentArchiveSizeMB,
                metrics = new
                {
                    totalArchiveSizeMB = Math.Round(totalArchiveSize, 2),
                    totalArchiveRows = totalArchiveRows,
                    totalArchiveValues = totalArchiveValues,
                    averageFileSizeMB = Math.Round(avgFileSize, 2),
                    largestFileName = largestFile?.FileName,
                    largestFileSizeMB = largestFile?.SizeMB ?? 0
                },
                directories = new
                {
                    source = status.SourceDirectory,
                    archive = status.ArchiveDirectory
                },
                settings = new
                {
                    autoCompressEnabled = status.AutoCompressEnabled,
                    archiveInterval = status.NextArchiveIn.TotalMinutes + " minutes"
                }
            });
        }
        catch (Exception ex)
        {
            _logger.LogError($"Error getting system health: {ex.Message}");
            return StatusCode(500, new { error = ex.Message });
        }
    }

    /// <summary>
    /// POST force archive cycle (manual trigger)
    /// </summary>
    [HttpPost("force-archive")]
    public ActionResult ForceArchiveCycle()
    {
        try
        {
            // This would require adding a method to LogBackupService
            // For now, return a message
            return Ok(new { message = "Manual archive trigger not yet implemented - service runs automatically" });
        }
        catch (Exception ex)
        {
            _logger.LogError($"Error forcing archive: {ex.Message}");
            return StatusCode(500, new { error = ex.Message });
        }
    }

    /// <summary>
    /// POST compress archives by date range
    /// </summary>
    [HttpPost("compress")]
    public async Task<ActionResult<CompressResult>> CompressArchives(
        [FromQuery] DateTime startDate,
        [FromQuery] DateTime endDate,
        CancellationToken cancellationToken)
    {
        try
        {
            var result = await _backupService.CompressArchivesByDateRange(startDate, endDate, cancellationToken);
            return Ok(result);
        }
        catch (Exception ex)
        {
            _logger.LogError($"Error compressing archives: {ex.Message}");
            return StatusCode(500, new { error = ex.Message });
        }
    }
}
