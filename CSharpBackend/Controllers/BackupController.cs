using Microsoft.AspNetCore.Mvc;
using OpcDaWebBrowser.Services;

namespace OpcDaWebBrowser.Controllers;

/// <summary>
/// API Controller for managing encrypted backup configuration
/// Only accessible by opcadmin role
/// </summary>
[ApiController]
[Route("api/[controller]")]
public class BackupController : ControllerBase
{
    private readonly LogBackupService _backupService;
    private readonly CredentialEncryptionService _encryption;
    private readonly ILogger<BackupController> _logger;
    private readonly string _configFile;

    public BackupController(
        LogBackupService backupService,
        CredentialEncryptionService encryption,
        ILogger<BackupController> logger)
    {
        _backupService = backupService;
        _encryption = encryption;
        _logger = logger;
        _configFile = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, ".logbackup");
    }

    /// <summary>
    /// Get the decrypted backup directory path (opcadmin only)
    /// </summary>
    [HttpGet("path")]
    public IActionResult GetBackupPath()
    {
        var username = HttpContext.Session.GetString("Username");
        var role = HttpContext.Session.GetString("UserRole");

        if (username != "opcadmin" || role != "Administrator")
        {
            _logger.LogWarning($"Unauthorized access attempt to backup config by {username}");
            return Unauthorized(new { message = "Access denied: Only opcadmin can view backup configuration" });
        }

        try
        {
            var path = _backupService.GetBackupDirectory();
            return Ok(new { 
                backupPath = path,
                encrypted = true,
                message = "Backup path retrieved successfully"
            });
        }
        catch (Exception ex)
        {
            _logger.LogError($"Error retrieving backup path: {ex.Message}");
            return StatusCode(500, new { message = "Error retrieving backup path" });
        }
    }

    /// <summary>
    /// Update the backup directory path (opcadmin only)
    /// </summary>
    [HttpPost("path")]
    public IActionResult UpdateBackupPath([FromBody] UpdateBackupPathRequest request)
    {
        var username = HttpContext.Session.GetString("Username");
        var role = HttpContext.Session.GetString("UserRole");

        if (username != "opcadmin" || role != "Administrator")
        {
            _logger.LogWarning($"Unauthorized backup path change attempt by {username}");
            return Unauthorized(new { message = "Access denied: Only opcadmin can modify backup configuration" });
        }

        try
        {
            // Validate path
            if (string.IsNullOrWhiteSpace(request.NewPath))
            {
                return BadRequest(new { message = "Invalid path provided" });
            }

            // Encrypt and save new path
            var encrypted = _encryption.Encrypt(request.NewPath);
            System.IO.File.WriteAllText(_configFile, encrypted);

            // Hide the config file
            var fileInfo = new FileInfo(_configFile);
            fileInfo.Attributes = FileAttributes.Hidden | FileAttributes.System;

            _logger.LogInformation($"Backup path updated by {username} to: {request.NewPath}");

            return Ok(new { 
                message = "Backup path updated successfully. Restart application to apply changes.",
                newPath = request.NewPath
            });
        }
        catch (Exception ex)
        {
            _logger.LogError($"Error updating backup path: {ex.Message}");
            return StatusCode(500, new { message = "Error updating backup path" });
        }
    }

    /// <summary>
    /// Get list of backup files (opcadmin only)
    /// </summary>
    [HttpGet("files")]
    public IActionResult GetBackupFiles()
    {
        var username = HttpContext.Session.GetString("Username");
        var role = HttpContext.Session.GetString("UserRole");

        if (username != "opcadmin" || role != "Administrator")
        {
            return Unauthorized(new { message = "Access denied: Only opcadmin can view backups" });
        }

        try
        {
            var files = _backupService.GetBackupFiles();
            return Ok(new { 
                files,
                count = files.Count,
                backupLocation = _backupService.GetBackupDirectory()
            });
        }
        catch (Exception ex)
        {
            _logger.LogError($"Error retrieving backup files: {ex.Message}");
            return StatusCode(500, new { message = "Error retrieving backup files" });
        }
    }

    /// <summary>
    /// Restore a backup file (opcadmin only)
    /// </summary>
    [HttpPost("restore")]
    public async Task<IActionResult> RestoreBackup([FromBody] RestoreBackupRequest request)
    {
        var username = HttpContext.Session.GetString("Username");
        var role = HttpContext.Session.GetString("UserRole");

        if (username != "opcadmin" || role != "Administrator")
        {
            return Unauthorized(new { message = "Access denied: Only opcadmin can restore backups" });
        }

        try
        {
            var restoredPath = await _backupService.RestoreBackupFile(request.FileName, username!);
            
            if (restoredPath == null)
            {
                return NotFound(new { message = "Backup file not found" });
            }

            return Ok(new { 
                message = "Backup restored successfully",
                restoredFile = restoredPath
            });
        }
        catch (Exception ex)
        {
            _logger.LogError($"Error restoring backup: {ex.Message}");
            return StatusCode(500, new { message = "Error restoring backup" });
        }
    }
}

public class UpdateBackupPathRequest
{
    public string NewPath { get; set; } = string.Empty;
}

public class RestoreBackupRequest
{
    public string FileName { get; set; } = string.Empty;
}
