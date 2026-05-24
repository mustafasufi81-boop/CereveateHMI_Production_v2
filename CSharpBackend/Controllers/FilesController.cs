using Microsoft.AspNetCore.Mvc;

namespace OpcDaWebBrowser.Controllers;

[ApiController]
[Route("api/[controller]")]
public class FilesController : ControllerBase
{
    private readonly ILogger<FilesController> _logger;

    public FilesController(ILogger<FilesController> logger)
    {
        _logger = logger;
    }

    [HttpGet("download")]
    public IActionResult DownloadFile([FromQuery] string path)
    {
        try
        {
            if (string.IsNullOrEmpty(path) || !System.IO.File.Exists(path))
            {
                _logger.LogWarning($"File not found: {path}");
                return NotFound($"File not found: {path}");
            }

            var fileName = Path.GetFileName(path);
            var fileBytes = System.IO.File.ReadAllBytes(path);
            
            _logger.LogInformation($"Downloading file: {fileName} ({fileBytes.Length} bytes)");
            
            return File(fileBytes, "text/csv", fileName);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error downloading file");
            return StatusCode(500, $"Error downloading file: {ex.Message}");
        }
    }
}
