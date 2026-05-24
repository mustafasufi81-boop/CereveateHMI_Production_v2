using System.IO;
using System.Security.AccessControl;
using System.Security.Principal;
using Parquet;
using Parquet.Data;
using Parquet.Schema;
using System.IO.Compression;
using OpcDaWebBrowser.Services.Health;

namespace OpcDaWebBrowser.Services;

/// <summary>
/// INDUSTRIAL-GRADE Parquet Archive Service
/// Consolidates multiple small parquet files into 200MB archives
/// - Hourly execution with precise timing
/// - Atomic operations (temp file strategy, zero data loss)
/// - Crash recovery (starts fresh, no partial archives)
/// - Skip locked files (no deadlocks, non-blocking)
/// - Per-day logging with comprehensive details
/// - Oldest-first processing
/// - Automatic cleanup after successful archive
/// </summary>
public class LogBackupService : BackgroundService
{
    private readonly ILogger<LogBackupService> _logger;
    private readonly IConfiguration _configuration;
    private readonly IHealthStatusService? _healthService;
    private readonly string _sourceParquetDirectory;
    private readonly string _archiveDirectory;
    private readonly string _archiveLogsPath;
    private TimeSpan _archiveInterval;
    private readonly TimeSpan _autoCompressInterval = TimeSpan.FromDays(1); // Auto-compress daily
    private readonly long _maxArchiveSizeBytes = 200 * 1024 * 1024; // 200MB
    private readonly long _archiveSizeTolerance = 10 * 1024 * 1024; // 10MB tolerance (210MB max)
    private readonly SemaphoreSlim _archiveLock = new(1, 1);
    private readonly SemaphoreSlim _compressLock = new(1, 1);
    private string? _currentArchivePath;
    private long _currentArchiveSize = 0;
    private readonly object _fileLock = new();
    private DateTime _lastAutoCompress = DateTime.MinValue;
    private bool _archiveEnabled = true;
    private readonly bool _autoCompressEnabled;

    public LogBackupService(
        ILogger<LogBackupService> logger,
        IConfiguration configuration,
        IHealthStatusService? healthService = null)
    {
        _logger = logger;
        _configuration = configuration;
        _healthService = healthService;

        // Read archive settings from config
        _archiveEnabled = configuration.GetValue<bool>("ArchiveSettings:Enabled", true);
        var intervalMinutes = configuration.GetValue<int>("ArchiveSettings:ArchiveIntervalMinutes", 15);
        _archiveInterval = TimeSpan.FromMinutes(intervalMinutes);
        _autoCompressEnabled = configuration.GetValue<bool>("ArchiveSettings:AutoCompressEnabled", false);

        // LOG CONFIG SOURCE AND VALUES FOR VERIFICATION
        _logger.LogInformation($"📋 CONFIG VERIFICATION:");
        _logger.LogInformation($"   Base Directory: {AppDomain.CurrentDomain.BaseDirectory}");
        _logger.LogInformation($"   Archive Enabled: {_archiveEnabled}");
        _logger.LogInformation($"   Archive Interval: {intervalMinutes} minutes");
        _logger.LogInformation($"   Auto-Compress: {_autoCompressEnabled}");

        // Read source parquet directory from configuration
        var sourceDir = configuration["LoggingPaths:DataLogDirectory"] ?? "D:\\OpcLogs\\Data";
        _sourceParquetDirectory = Path.IsPathRooted(sourceDir)
            ? sourceDir
            : Path.Combine(AppDomain.CurrentDomain.BaseDirectory, sourceDir);

        // Read archive directory from configuration
        var archiveDir = configuration["LoggingPaths:BackupDirectory"] ?? "D:\\OpcLogs\\Backup";
        _archiveDirectory = Path.IsPathRooted(archiveDir)
            ? archiveDir
            : Path.Combine(AppDomain.CurrentDomain.BaseDirectory, archiveDir);

        // Read archive logs path from configuration
        var logsPath = configuration["LoggingPaths:ArchiveLogsPath"] ?? Path.Combine(_archiveDirectory, "Logs");
        _archiveLogsPath = Path.IsPathRooted(logsPath)
            ? logsPath
            : Path.Combine(AppDomain.CurrentDomain.BaseDirectory, logsPath);

        InitializeArchiveDirectories();
    }

    private void InitializeArchiveDirectories()
    {
        try
        {
            // Create archive directory if it doesn't exist
            if (!Directory.Exists(_archiveDirectory))
            {
                Directory.CreateDirectory(_archiveDirectory);
                _logger.LogInformation($"✅ Created archive directory: {_archiveDirectory}");
            }

            // Create archive logs directory if it doesn't exist
            if (!Directory.Exists(_archiveLogsPath))
            {
                Directory.CreateDirectory(_archiveLogsPath);
                _logger.LogInformation($"✅ Created archive logs directory: {_archiveLogsPath}");
            }

            _logger.LogInformation($"🗄️ Parquet Archive Service initialized");
            _logger.LogInformation($"   Source: {_sourceParquetDirectory}");
            _logger.LogInformation($"   Archive: {_archiveDirectory}");
            _logger.LogInformation($"   Logs: {_archiveLogsPath}");
            _logger.LogInformation($"   Max Size: {_maxArchiveSizeBytes / (1024 * 1024)}MB");
            _logger.LogInformation($"   Interval: {_archiveInterval.TotalHours} hour(s)");
            _logger.LogInformation($"   Auto-Compress: {(_autoCompressEnabled ? "ENABLED" : "DISABLED")}");
        }
        catch (Exception ex)
        {
            _logger.LogError($"❌ Failed to initialize archive directories: {ex.Message}");
        }
    }

    /// <summary>
    /// Check if file is locked by another process (non-blocking)
    /// </summary>
    private bool IsFileLocked(string filePath)
    {
        try
        {
            using var stream = File.Open(filePath, FileMode.Open, FileAccess.Read, FileShare.None);
            return false;
        }
        catch (IOException)
        {
            return true;
        }
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("🗄️ Parquet Archive Service started");

        // Check if archiving is enabled in config
        if (!_archiveEnabled)
        {
            _logger.LogInformation("⏸️ Archiving is DISABLED in configuration - service will not run");
            return;
        }

        _logger.LogInformation($"✅ Archiving ENABLED - interval: {_archiveInterval.TotalMinutes} minutes, auto-compress: {(_autoCompressEnabled ? "enabled" : "disabled")}");

        // Clean up any incomplete archive files from previous crash
        CleanupIncompleteArchives();

        // Archive any old OpcData files that exist in the Backup directory (one-time cleanup on startup)
        await ArchiveOldBackupFiles(stoppingToken);

        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                // Archive parquet files
                await ArchiveParquetFiles(stoppingToken);

                // Auto-compress old archives (if enabled in config)
                if (_autoCompressEnabled)
                {
                    await AutoCompressOldArchives(stoppingToken);
                }

                await Task.Delay(_archiveInterval, stoppingToken);
            }
            catch (OperationCanceledException)
            {
                break;
            }
            catch (Exception ex)
            {
                _logger.LogError($"❌ Error in archive service: {ex.Message}");
                LogToFile($"ERROR: {ex.Message}\n{ex.StackTrace}");
                await Task.Delay(TimeSpan.FromMinutes(5), stoppingToken);
            }
        }

        _logger.LogInformation("🗄️ Parquet Archive Service stopped");
    }

    /// <summary>
    /// Clean up incomplete .tmp archive files from previous crash
    /// </summary>
    private void CleanupIncompleteArchives()
    {
        try
        {
            var tmpFiles = Directory.GetFiles(_archiveDirectory, "*.tmp");
            foreach (var tmpFile in tmpFiles)
            {
                try
                {
                    File.Delete(tmpFile);
                    _logger.LogInformation($"🧹 Cleaned up incomplete archive: {Path.GetFileName(tmpFile)}");
                    LogToFile($"CLEANUP: Deleted incomplete archive {Path.GetFileName(tmpFile)}");
                }
                catch (Exception ex)
                {
                    _logger.LogWarning($"Could not delete {tmpFile}: {ex.Message}");
                }
            }
        }
        catch (Exception ex)
        {
            _logger.LogWarning($"Cleanup error: {ex.Message}");
        }
    }

    /// <summary>
    /// ONE-TIME CLEANUP: Archive any old OpcData parquet files that exist in the Backup directory
    /// These files were likely copied there by the old backup service before we converted it to archive service
    /// </summary>
    private async Task ArchiveOldBackupFiles(CancellationToken cancellationToken)
    {
        try
        {
            // Find all OpcData_*.parquet files in the Backup directory (excluding Archive_*.parquet)
            var oldFiles = Directory.EnumerateFiles(_archiveDirectory, "OpcData_*.parquet")
                .OrderBy(f => new FileInfo(f).LastWriteTime)
                .ToList();

            cancellationToken.ThrowIfCancellationRequested();

            if (oldFiles.Count == 0)
            {
                _logger.LogInformation("✅ No old backup files to archive");
                return;
            }

            _logger.LogInformation($"🔍 Found {oldFiles.Count} old OpcData files in Backup folder - starting one-time cleanup...");
            LogToFile($"=== ONE-TIME CLEANUP: {oldFiles.Count} old backup files ===");

            int processedCount = 0;
            long totalSize = 0;

            foreach (var sourceFile in oldFiles)
            {
                if (cancellationToken.IsCancellationRequested) break;

                try
                {
                    var fileInfo = new FileInfo(sourceFile);
                    var fileSize = fileInfo.Length;

                    // Check if we need to start a new archive (size limit reached)
                    if (_currentArchivePath == null || _currentArchiveSize + fileSize > (_maxArchiveSizeBytes + _archiveSizeTolerance))
                    {
                        // Start new archive
                        var archiveName = $"Archive_{DateTime.Now:yyyyMMdd_HHmmss}.parquet";
                        _currentArchivePath = Path.Combine(_archiveDirectory, archiveName);
                        _currentArchiveSize = 0;
                        _logger.LogInformation($"📝 Starting new archive for cleanup: {archiveName}");
                        LogToFile($"CLEANUP NEW ARCHIVE: {archiveName}");
                    }

                    // Append to archive
                    await AppendToArchive(sourceFile, _currentArchivePath, cancellationToken);

                    _currentArchiveSize += fileSize;

                    // Generate metadata for the archive
                    await GenerateArchiveMetadata(_currentArchivePath, cancellationToken);

                    // Delete source file after successful archive
                    File.Delete(sourceFile);
                    processedCount++;
                    totalSize += fileSize;

                    LogToFile($"CLEANUP SUCCESS: {Path.GetFileName(sourceFile)} - {fileSize} bytes - Deleted");
                }
                catch (Exception ex)
                {
                    _logger.LogWarning($"⚠️ Could not archive old file {Path.GetFileName(sourceFile)}: {ex.Message}");
                    LogToFile($"CLEANUP SKIP: {Path.GetFileName(sourceFile)} - {ex.Message}");
                }
            }

            _logger.LogInformation($"✅ One-time cleanup complete: Archived {processedCount} old files ({totalSize / 1024 / 1024:F2} MB)");
            LogToFile($"CLEANUP COMPLETE: {processedCount} files, {totalSize} bytes total");
        }
        catch (Exception ex)
        {
            _logger.LogError($"❌ Error during old backup files cleanup: {ex.Message}");
            LogToFile($"CLEANUP ERROR: {ex.Message}");
        }
    }

    /// <summary>
    /// Main archiving logic - consolidate parquet files into 200MB archives
    /// </summary>
    private async Task ArchiveParquetFiles(CancellationToken cancellationToken)
    {
        // Use semaphore for single execution (no race conditions)
        if (!await _archiveLock.WaitAsync(0, cancellationToken))
        {
            _logger.LogDebug("Archive operation already running, skipping");
            return;
        }

        try
        {
            if (!Directory.Exists(_sourceParquetDirectory))
            {
                _logger.LogWarning($"Source directory does not exist: {_sourceParquetDirectory}");
                return;
            }

            // Clean up orphaned metadata files where the base parquet no longer exists
            CleanupOrphanedArchiveMetadata();

            // Get all parquet files using EnumerateFiles (faster for large directories)
            // Keep the two newest files in place to ensure live logging head remains available
            var parquetFiles = Directory.EnumerateFiles(_sourceParquetDirectory, "*.parquet")
                .Select(f => new FileInfo(f))
                .OrderBy(f => f.LastWriteTime)
                .ToList();

            // Retain the latest two files (most recent write time) to avoid emptying active folder
            if (parquetFiles.Count > 2)
            {
                parquetFiles = parquetFiles.Take(parquetFiles.Count - 2).ToList();
            }
            else
            {
                _logger.LogInformation("No archivable parquet files (<=2 files present). Skipping archive cycle.");
                return;
            }

            cancellationToken.ThrowIfCancellationRequested();

            if (parquetFiles.Count == 0)
            {
                _logger.LogInformation("No parquet files to archive");
                return;
            }

            _logger.LogInformation($"📦 Found {parquetFiles.Count} parquet files to process");
            LogToFile($"ARCHIVE CYCLE START: Found {parquetFiles.Count} files");

            int filesProcessed = 0;
            long totalBytesArchived = 0;

            foreach (var fileInfo in parquetFiles)
            {
                cancellationToken.ThrowIfCancellationRequested();

                // Skip locked files (no deadlock)
                if (IsFileLocked(fileInfo.FullName))
                {
                    _logger.LogWarning($"⏭️ Skipping locked file: {fileInfo.Name}");
                    LogToFile($"SKIP: File locked - {fileInfo.Name}");
                    continue;
                }

                try
                {
                    // Check if we need a new archive file
                    if (_currentArchivePath == null || 
                        (_currentArchiveSize + fileInfo.Length) > (_maxArchiveSizeBytes + _archiveSizeTolerance))
                    {
                        // Start new archive
                        var archiveName = $"Archive_{DateTime.Now:yyyyMMdd_HHmmss}.parquet";
                        _currentArchivePath = Path.Combine(_archiveDirectory, archiveName);
                        
                        // Initialize size from existing file if it exists (restart scenario)
                        if (File.Exists(_currentArchivePath))
                        {
                            _currentArchiveSize = new FileInfo(_currentArchivePath).Length;
                            _logger.LogInformation($"📝 Reusing existing archive: {archiveName} (current size: {_currentArchiveSize / (1024 * 1024)}MB)");
                        }
                        else
                        {
                            _currentArchiveSize = 0;
                            _logger.LogInformation($"📝 Starting new archive: {archiveName}");
                        }
                        LogToFile($"NEW ARCHIVE: {archiveName}");
                    }

                    // Append file to archive using atomic temp file strategy
                    await AppendToArchive(fileInfo.FullName, _currentArchivePath, cancellationToken);

                    _currentArchiveSize += fileInfo.Length;
                    totalBytesArchived += fileInfo.Length;
                    filesProcessed++;

                    // Check cancellation before deleting source
                    cancellationToken.ThrowIfCancellationRequested();

                    // Generate metadata for the archive after successful append
                    await GenerateArchiveMetadata(_currentArchivePath, cancellationToken);

                    // Delete source file after successful archive
                    File.Delete(fileInfo.FullName);
                    _logger.LogInformation($"✅ Archived and deleted: {fileInfo.Name} ({fileInfo.Length / 1024}KB)");
                    LogToFile($"SUCCESS: {fileInfo.Name} - {fileInfo.Length} bytes - Deleted");
                }
                catch (Exception ex)
                {
                    _logger.LogError($"❌ Failed to archive {fileInfo.Name}: {ex.Message}");
                    LogToFile($"ERROR: {fileInfo.Name} - {ex.Message}");
                }
            }

            _logger.LogInformation($"📊 Archive cycle complete: {filesProcessed} files, {totalBytesArchived / (1024 * 1024)}MB");
            LogToFile($"CYCLE COMPLETE: {filesProcessed} files, {totalBytesArchived} bytes total");

            // Update health monitoring
            UpdateHealthStatus(0); // Success, no errors
        }
        finally
        {
            _archiveLock.Release();
        }
    }

    private void CleanupOrphanedArchiveMetadata()
    {
        try
        {
            if (!Directory.Exists(_archiveDirectory))
                return;

            foreach (var meta in Directory.EnumerateFiles(_archiveDirectory, "*.parquet.meta.json"))
            {
                var baseFile = meta[..^".meta.json".Length];
                if (!File.Exists(baseFile))
                {
                    _logger.LogInformation("Removing orphaned archive metadata: {MetaFile}", Path.GetFileName(meta));
                    File.Delete(meta);
                }
            }
        }
        catch (Exception ex)
        {
            _logger.LogWarning("Metadata cleanup skipped: {Message}", ex.Message);
        }
    }

    /// <summary>
    /// Append parquet file to archive using SAFE rewrite strategy (zero data loss)
    /// CRITICAL FIX: Parquet format does NOT support true append - we must read entire archive and rewrite
    /// </summary>
    private async Task AppendToArchive(string sourceFile, string archiveFile, CancellationToken cancellationToken)
    {
        var tempFile = archiveFile + ".tmp";
        var backupFile = archiveFile + ".bak";

        try
        {
            cancellationToken.ThrowIfCancellationRequested();

            // Read source parquet data
            using var sourceStream = File.OpenRead(sourceFile);
            using var sourceReader = await ParquetReader.CreateAsync(sourceStream, cancellationToken: cancellationToken);
            var sourceSchema = sourceReader.Schema;

            // Check if archive exists - if so, validate schema compatibility
            if (File.Exists(archiveFile))
            {
                cancellationToken.ThrowIfCancellationRequested();

                // Read existing archive schema
                using var archiveStream = File.OpenRead(archiveFile);
                using var archiveReader = await ParquetReader.CreateAsync(archiveStream, cancellationToken: cancellationToken);
                var archiveSchema = archiveReader.Schema;

                // CRITICAL: Check schema compatibility
                if (!SchemasAreCompatible(archiveSchema, sourceSchema))
                {
                    _logger.LogWarning($"⚠️ Schema mismatch detected - starting new archive for file: {Path.GetFileName(sourceFile)}");
                    _logger.LogWarning($"   Archive schema: {archiveSchema.Fields.Count} fields, Source schema: {sourceSchema.Fields.Count} fields");
                    
                    // Start a NEW archive for this mismatched file instead of throwing
                    var newArchiveName = $"Archive_{DateTime.Now:yyyyMMdd_HHmmss}_schema.parquet";
                    var newArchivePath = Path.Combine(Path.GetDirectoryName(archiveFile)!, newArchiveName);
                    
                    await WriteParquetToFile(sourceReader, newArchivePath, cancellationToken);
                    
                    // Update current archive path to the new one
                    _currentArchivePath = newArchivePath;
                    _currentArchiveSize = new FileInfo(newArchivePath).Length;
                    
                    _logger.LogInformation($"✅ Created new archive for schema-mismatched file: {newArchiveName}");
                    LogToFile($"SCHEMA MISMATCH: Created new archive {newArchiveName} for {Path.GetFileName(sourceFile)}");
                    return; // Successfully handled
                }

                // SAFE REWRITE STRATEGY: Read entire archive + source, write to new file
                await RewriteArchiveWithNewData(archiveReader, sourceReader, tempFile, cancellationToken);
            }
            else
            {
                // First file - direct write to temp
                cancellationToken.ThrowIfCancellationRequested();
                await WriteParquetToFile(sourceReader, tempFile, cancellationToken);
            }

            cancellationToken.ThrowIfCancellationRequested();

            // ATOMIC REPLACE: Use File.Replace for maximum safety
            if (File.Exists(archiveFile))
            {
                // Create backup, replace archive with temp, delete backup
                lock (_fileLock)
                {
                    try
                    {
                        File.Replace(tempFile, archiveFile, backupFile);
                        // Cleanup backup if replace succeeded
                        if (File.Exists(backupFile))
                        {
                            try { File.Delete(backupFile); } catch { }
                        }
                    }
                    catch (PlatformNotSupportedException)
                    {
                        // File.Replace not supported (cross-volume) - use copy+delete fallback
                        _logger.LogWarning("File.Replace not supported - using copy+delete fallback");
                        File.Copy(tempFile, archiveFile, overwrite: true);
                        File.Delete(tempFile);
                    }
                    catch (IOException ex) when (ex.Message.Contains("different volume") || ex.Message.Contains("cross-device"))
                    {
                        // Cross-volume scenario - use copy+delete fallback
                        _logger.LogWarning("Cross-volume operation detected - using copy+delete fallback");
                        File.Copy(tempFile, archiveFile, overwrite: true);
                        File.Delete(tempFile);
                    }
                }
            }
            else
            {
                // First file - simple rename
                lock (_fileLock)
                {
                    File.Move(tempFile, archiveFile, overwrite: true);
                }
            }
        }
        catch (OperationCanceledException)
        {
            // Shutdown requested - cleanup temp but preserve archive and backup
            if (File.Exists(tempFile))
            {
                try { File.Delete(tempFile); } catch { }
            }
            throw;
        }
        catch (Exception)
        {
            // CRITICAL: Only delete temp if archive still exists (prevents data loss)
            if (File.Exists(archiveFile) && File.Exists(tempFile))
            {
                try { File.Delete(tempFile); } catch { }
            }
            // If archive doesn't exist and temp does, temp is our ONLY copy - don't delete!
            throw;
        }
        finally
        {
            // Cleanup backup file if it exists
            if (File.Exists(backupFile))
            {
                try { File.Delete(backupFile); } catch { }
            }
        }
    }

    /// <summary>
    /// Check if two parquet schemas are compatible for merging
    /// </summary>
    private bool SchemasAreCompatible(ParquetSchema schema1, ParquetSchema schema2)
    {
        if (schema1.Fields.Count != schema2.Fields.Count)
            return false;

        for (int i = 0; i < schema1.Fields.Count; i++)
        {
            var field1 = schema1.Fields[i];
            var field2 = schema2.Fields[i];

            if (field1.Name != field2.Name)
                return false;
            
            // Type compatibility check
            if (field1.SchemaType != field2.SchemaType)
                return false;
        }

        return true;
    }

    /// <summary>
    /// SAFE PARQUET REWRITE: Read all data from archive and source, write to new file
    /// This is the ONLY safe way to "append" to parquet files
    /// </summary>
    private async Task RewriteArchiveWithNewData(
        ParquetReader archiveReader,
        ParquetReader sourceReader,
        string outputFile,
        CancellationToken cancellationToken)
    {
        var schema = archiveReader.Schema;

        using var outputStream = File.Create(outputFile);
        using var writer = await ParquetWriter.CreateAsync(schema, outputStream, cancellationToken: cancellationToken);

        // Copy all row groups from existing archive
        for (int i = 0; i < archiveReader.RowGroupCount; i++)
        {
            cancellationToken.ThrowIfCancellationRequested();

            using var archiveGroupReader = archiveReader.OpenRowGroupReader(i);
            using var groupWriter = writer.CreateRowGroup();

            foreach (var field in schema.GetDataFields())
            {
                var column = await archiveGroupReader.ReadColumnAsync(field, cancellationToken);
                await groupWriter.WriteColumnAsync(column, cancellationToken);
            }
        }

        // Append all row groups from source file
        for (int i = 0; i < sourceReader.RowGroupCount; i++)
        {
            cancellationToken.ThrowIfCancellationRequested();

            using var sourceGroupReader = sourceReader.OpenRowGroupReader(i);
            using var groupWriter = writer.CreateRowGroup();

            foreach (var field in schema.GetDataFields())
            {
                var column = await sourceGroupReader.ReadColumnAsync(field, cancellationToken);
                await groupWriter.WriteColumnAsync(column, cancellationToken);
            }
        }
    }

    /// <summary>
    /// Write parquet reader data to file (for new archives)
    /// </summary>
    private async Task WriteParquetToFile(ParquetReader reader, string outputFile, CancellationToken cancellationToken)
    {
        var schema = reader.Schema;

        using var outputStream = File.Create(outputFile);
        using var writer = await ParquetWriter.CreateAsync(schema, outputStream, cancellationToken: cancellationToken);

        for (int i = 0; i < reader.RowGroupCount; i++)
        {
            cancellationToken.ThrowIfCancellationRequested();

            using var groupReader = reader.OpenRowGroupReader(i);
            using var groupWriter = writer.CreateRowGroup();

            foreach (var field in schema.GetDataFields())
            {
                var column = await groupReader.ReadColumnAsync(field, cancellationToken);
                await groupWriter.WriteColumnAsync(column, cancellationToken);
            }
        }
    }

    /// <summary>
    /// Log to daily archive log file
    /// </summary>
    private void LogToFile(string message)
    {
        try
        {
            var logFile = Path.Combine(_archiveLogsPath, $"Archive_{DateTime.Now:yyyyMMdd}.log");
            var logEntry = $"[{DateTime.Now:yyyy-MM-dd HH:mm:ss.fff}] {message}\n";
            
            lock (_fileLock)
            {
                File.AppendAllText(logFile, logEntry);
            }
        }
        catch (Exception ex)
        {
            _logger.LogWarning($"Failed to write to log file: {ex.Message}");
        }
    }

    /// <summary>
    /// AUTO-COMPRESS: Automatically compress archives older than 7 days (runs once per day)
    /// </summary>
    private async Task AutoCompressOldArchives(CancellationToken cancellationToken)
    {
        // Check if we've already run today
        if ((DateTime.Now - _lastAutoCompress).TotalHours < 24)
        {
            return;
        }

        if (!await _compressLock.WaitAsync(0, cancellationToken))
        {
            return;
        }

        try
        {
            cancellationToken.ThrowIfCancellationRequested();

            _logger.LogInformation("🤖 Auto-compress: Checking for old archives...");
            LogToFile("AUTO-COMPRESS: Starting automatic compression check");

            var sevenDaysAgo = DateTime.Now.AddDays(-7).Date;
            var thirtyDaysAgo = DateTime.Now.AddDays(-30).Date;

            // Compress archives in 1-month chunks, starting from 7 days ago
            var startDate = thirtyDaysAgo;
            var endDate = sevenDaysAgo;

            cancellationToken.ThrowIfCancellationRequested();

            var result = await CompressArchivesByDateRange(startDate, endDate, cancellationToken);

            if (result.FilesCompressed > 0)
            {
                _logger.LogInformation($"✅ Auto-compressed {result.FilesCompressed} archives ({result.CompressedSizeMB}MB)");
                LogToFile($"AUTO-COMPRESS SUCCESS: {result.FilesCompressed} files, {result.CompressedSizeMB}MB compressed, {result.CompressionRatio}% saved");
            }
            else
            {
                _logger.LogInformation("ℹ️ No old archives to compress");
            }

            _lastAutoCompress = DateTime.Now;
        }
        catch (Exception ex)
        {
            _logger.LogError($"❌ Auto-compress error: {ex.Message}");
            LogToFile($"AUTO-COMPRESS ERROR: {ex.Message}");
        }
        finally
        {
            _compressLock.Release();
        }
    }

    /// <summary>
    /// MANUAL COMPRESS: Compress archives by date range (called from API)
    /// </summary>
    public async Task<CompressResult> CompressArchivesByDateRange(DateTime startDate, DateTime endDate, CancellationToken cancellationToken)
    {
        if (!await _compressLock.WaitAsync(0, cancellationToken))
        {
            return new CompressResult { Success = false, Message = "Compression already in progress" };
        }

        try
        {
            cancellationToken.ThrowIfCancellationRequested();

            // Find archive files in date range
            var archiveFiles = Directory.EnumerateFiles(_archiveDirectory, "Archive_*.parquet")
                .Select(f => new FileInfo(f))
                .Where(f =>
                {
                    // Parse date from filename: Archive_YYYYMMDD_HHMMSS.parquet
                    var fileName = Path.GetFileNameWithoutExtension(f.Name);
                    var parts = fileName.Split('_');
                    if (parts.Length >= 2 && parts[0] == "Archive")
                    {
                        if (DateTime.TryParseExact(parts[1], "yyyyMMdd", null,
                            System.Globalization.DateTimeStyles.None, out var fileDate))
                        {
                            return fileDate >= startDate.Date && fileDate <= endDate.Date;
                        }
                    }
                    return false;
                })
                .ToList();

            cancellationToken.ThrowIfCancellationRequested();

            cancellationToken.ThrowIfCancellationRequested();

            if (archiveFiles.Count == 0)
            {
                return new CompressResult { Success = true, FilesCompressed = 0, Message = "No files found in range" };
            }

            // Create ZIP file
            var zipFileName = $"ArchiveCompressed_{startDate:yyyyMMdd}_to_{endDate:yyyyMMdd}.zip";
            var zipPath = Path.Combine(_archiveDirectory, zipFileName);

            // Delete existing ZIP if exists
            if (File.Exists(zipPath))
            {
                cancellationToken.ThrowIfCancellationRequested();
                File.Delete(zipPath);
            }

            cancellationToken.ThrowIfCancellationRequested();

            long totalSizeBytes = 0;
            using (var zipArchive = ZipFile.Open(zipPath, ZipArchiveMode.Create))
            {
                foreach (var file in archiveFiles)
                {
                    cancellationToken.ThrowIfCancellationRequested();
                    zipArchive.CreateEntryFromFile(file.FullName, file.Name, CompressionLevel.Optimal);
                    totalSizeBytes += file.Length;
                }
            }

            var zipFileInfo = new FileInfo(zipPath);
            var compressionRatio = totalSizeBytes > 0
                ? (1 - (double)zipFileInfo.Length / totalSizeBytes) * 100
                : 0;

            LogToFile($"COMPRESS: Created {zipFileName}, {archiveFiles.Count} files, {zipFileInfo.Length / (1024.0 * 1024.0):F2}MB");

            return new CompressResult
            {
                Success = true,
                ZipFileName = zipFileName,
                FilesCompressed = archiveFiles.Count,
                OriginalSizeMB = Math.Round(totalSizeBytes / (1024.0 * 1024.0), 2),
                CompressedSizeMB = Math.Round(zipFileInfo.Length / (1024.0 * 1024.0), 2),
                CompressionRatio = Math.Round(compressionRatio, 1),
                Message = $"Successfully compressed {archiveFiles.Count} files"
            };
        }
        finally
        {
            _compressLock.Release();
        }
    }

    // ===== LEGACY API COMPATIBILITY (for BackupController) =====
    public string GetBackupDirectory() => _archiveDirectory;

    public List<string> GetBackupFiles()
    {
        try
        {
            if (!Directory.Exists(_archiveDirectory))
            {
                return new List<string>();
            }

            return Directory.GetFiles(_archiveDirectory, "Archive_*.parquet")
                .Select(Path.GetFileName)
                .OrderByDescending(f => f)
                .ToList()!;
        }
        catch
        {
            return new List<string>();
        }
    }

    public async Task<string?> RestoreBackupFile(string fileName, string username)
    {
        _logger.LogWarning("Restore not supported in archive mode");
        await Task.CompletedTask;
        return null;
    }

    /// <summary>
    /// Generate lightweight metadata cache for archive file (CRITICAL for safe UI)
    /// This enables UI to be COMPLETELY READ-ONLY with ZERO parquet scanning
    /// </summary>
    private async Task GenerateArchiveMetadata(string archiveFile, CancellationToken cancellationToken)
    {
        if (!File.Exists(archiveFile))
            return;

        try
        {
            var metadataFile = archiveFile + ".meta.json";
            
            // Read parquet metadata ONCE during archiving (not from UI)
            using var fileStream = File.Open(archiveFile, FileMode.Open, FileAccess.Read, FileShare.ReadWrite);
            using var reader = await ParquetReader.CreateAsync(fileStream, cancellationToken: cancellationToken);
            
            var schema = reader.Schema;
            long totalRows = 0;
            DateTime? minTimestamp = null;
            DateTime? maxTimestamp = null;

            // Calculate total rows and timestamp range
            for (int i = 0; i < reader.RowGroupCount; i++)
            {
                cancellationToken.ThrowIfCancellationRequested();
                
                using var groupReader = reader.OpenRowGroupReader(i);
                var rowCount = groupReader.RowCount;
                totalRows += rowCount;

                // Try to read timestamp column for range
                try
                {
                    var timestampField = schema.GetDataFields().FirstOrDefault(f => 
                        f.Name.Equals("Timestamp", StringComparison.OrdinalIgnoreCase));
                    
                    if (timestampField != null)
                    {
                        var timestampColumn = await groupReader.ReadColumnAsync(timestampField, cancellationToken);
                        var timestamps = timestampColumn.Data as DateTime[];
                        
                        if (timestamps != null && timestamps.Length > 0)
                        {
                            var groupMin = timestamps.Min();
                            var groupMax = timestamps.Max();
                            
                            if (minTimestamp == null || groupMin < minTimestamp)
                                minTimestamp = groupMin;
                            if (maxTimestamp == null || groupMax > maxTimestamp)
                                maxTimestamp = groupMax;
                        }
                    }
                }
                catch
                {
                    // Timestamp extraction failed - not critical
                }
            }

            var fileInfo = new FileInfo(archiveFile);
            var metadata = new
            {
                fileName = Path.GetFileName(archiveFile),
                sizeBytes = fileInfo.Length,
                sizeMB = Math.Round(fileInfo.Length / (1024.0 * 1024.0), 2),
                rows = totalRows,
                columns = schema.GetDataFields().Length,
                totalValues = totalRows * schema.GetDataFields().Length,
                rowGroups = reader.RowGroupCount,
                schema = schema.GetDataFields().Select(f => new { name = f.Name, type = f.ClrType.Name }).ToArray(),
                minTimestamp = minTimestamp?.ToString("yyyy-MM-dd HH:mm:ss.fff"),
                maxTimestamp = maxTimestamp?.ToString("yyyy-MM-dd HH:mm:ss.fff"),
                generatedAt = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss.fff"),
                compressionCodec = "Snappy" // Default for Parquet.NET
            };

            var json = System.Text.Json.JsonSerializer.Serialize(metadata, new System.Text.Json.JsonSerializerOptions 
            { 
                WriteIndented = true 
            });

            // Write metadata atomically
            var tempMetaFile = metadataFile + ".tmp";
            await File.WriteAllTextAsync(tempMetaFile, json, cancellationToken);
            File.Move(tempMetaFile, metadataFile, overwrite: true);

            _logger.LogDebug($"📋 Generated metadata for {Path.GetFileName(archiveFile)}: {totalRows} rows, {totalRows * schema.GetDataFields().Length} values");
        }
        catch (Exception ex)
        {
            _logger.LogWarning($"⚠️ Could not generate metadata for {Path.GetFileName(archiveFile)}: {ex.Message}");
            // Non-critical - UI will fall back to basic file info
        }
    }

    /// <summary>
    /// Get archiving service status for dashboard (READ-ONLY, SAFE)
    /// </summary>
    public ArchiverStatus GetStatus()
    {
        try {
            var sourceFileCount = Directory.Exists(_sourceParquetDirectory)
                ? Directory.EnumerateFiles(_sourceParquetDirectory, "*.parquet").Count()
                : 0;

            var archiveFileCount = Directory.Exists(_archiveDirectory)
                ? Directory.EnumerateFiles(_archiveDirectory, "Archive_*.parquet").Count()
                : 0;

            return new ArchiverStatus
            {
                IsRunning = _archiveEnabled,
                LastArchiveTime = DateTime.Now, // Simplified - could track actual last run
                NextArchiveIn = _archiveInterval,
                SourceDirectory = _sourceParquetDirectory,
                ArchiveDirectory = _archiveDirectory,
                UnarchivedFilesCount = sourceFileCount,
                ArchiveFilesCount = archiveFileCount,
                CurrentArchiveFile = _currentArchivePath != null ? Path.GetFileName(_currentArchivePath) : null,
                CurrentArchiveSizeMB = Math.Round(_currentArchiveSize / (1024.0 * 1024.0), 2),
                AutoCompressEnabled = _autoCompressEnabled
            };
        }
        catch
        {
            return new ArchiverStatus { IsRunning = false };
        }
    }

    /// <summary>
    /// Update health monitoring service with archiver status
    /// </summary>
    private void UpdateHealthStatus(int errorCount)
    {
        if (_healthService == null) return;

        try
        {
            var status = GetStatus();
            
            // Calculate health score (0-100)
            double healthScore = 100;
            
            // Penalties for backlog
            if (status.UnarchivedFilesCount > 1000) healthScore -= 30; // Critical backlog
            else if (status.UnarchivedFilesCount > 500) healthScore -= 20;
            else if (status.UnarchivedFilesCount > 100) healthScore -= 10;
            
            // Penalty for errors
            if (errorCount > 0) healthScore -= 20;
            
            // Penalty if disabled
            if (!status.IsRunning) healthScore = 50;
            
            healthScore = Math.Max(0, healthScore);

            var health = new ArchiverHealth
            {
                Status = status.IsRunning ? (errorCount > 0 ? "Error" : "Running") : "Disabled",
                UnarchivedFilesCount = status.UnarchivedFilesCount,
                ArchiveFilesCount = status.ArchiveFilesCount,
                CurrentArchiveSizeMB = status.CurrentArchiveSizeMB,
                LastArchiveTime = status.LastArchiveTime,
                NextArchiveIn = status.NextArchiveIn,
                ErrorCount = errorCount,
                LastError = null, // Could track last error message
                HealthScore = healthScore
            };

            _healthService.UpdateArchiverHealth(health);
        }
        catch (Exception ex)
        {
            _logger.LogWarning($"Failed to update health status: {ex.Message}");
        }
    }
}

/// <summary>
/// Result of compression operation
/// </summary>
public class CompressResult
{
    public bool Success { get; set; }
    public string ZipFileName { get; set; } = "";
    public int FilesCompressed { get; set; }
    public double OriginalSizeMB { get; set; }
    public double CompressedSizeMB { get; set; }
    public double CompressionRatio { get; set; }
    public string Message { get; set; } = "";
}

/// <summary>
/// Archiver service status for dashboard (READ-ONLY)
/// </summary>
public class ArchiverStatus
{
    public bool IsRunning { get; set; }
    public DateTime LastArchiveTime { get; set; }
    public TimeSpan NextArchiveIn { get; set; }
    public string SourceDirectory { get; set; } = "";
    public string ArchiveDirectory { get; set; } = "";
    public int UnarchivedFilesCount { get; set; }
    public int ArchiveFilesCount { get; set; }
    public string? CurrentArchiveFile { get; set; }
    public double CurrentArchiveSizeMB { get; set; }
    public bool AutoCompressEnabled { get; set; }
}
