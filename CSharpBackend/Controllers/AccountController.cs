using Microsoft.AspNetCore.Mvc;
using OpcDaWebBrowser.Services;

namespace OpcDaWebBrowser.Controllers;

/// <summary>
/// API Controller for account management (password changes and user management)
/// </summary>
[ApiController]
[Route("api/[controller]")]
public class AccountController : ControllerBase
{
    private readonly AuthenticationService _authService;
    private readonly ILogger<AccountController> _logger;

    public AccountController(
        AuthenticationService authService,
        ILogger<AccountController> logger)
    {
        _authService = authService;
        _logger = logger;
    }

    /// <summary>
    /// Change own password (any authenticated user)
    /// </summary>
    [HttpPost("change-password")]
    public IActionResult ChangePassword([FromBody] ChangePasswordRequest request)
    {
        var username = HttpContext.Session.GetString("Username");
        var isAuthenticated = HttpContext.Session.GetString("IsAuthenticated") == "true";

        if (!isAuthenticated || string.IsNullOrEmpty(username))
        {
            return Unauthorized(new { message = "Not authenticated" });
        }

        if (string.IsNullOrWhiteSpace(request.OldPassword) || string.IsNullOrWhiteSpace(request.NewPassword))
        {
            return BadRequest(new { message = "Old password and new password are required" });
        }

        if (request.NewPassword.Length < 6)
        {
            return BadRequest(new { message = "New password must be at least 6 characters" });
        }

        var success = _authService.ChangePassword(username, request.OldPassword, request.NewPassword);
        
        if (success)
        {
            _logger.LogInformation($"Password changed successfully for user '{username}'");
            return Ok(new { success = true, message = "Password changed successfully" });
        }
        else
        {
            return BadRequest(new { message = "Invalid old password" });
        }
    }

    /// <summary>
    /// Change another user's password (opcadmin only)
    /// </summary>
    [HttpPost("admin/change-user-password")]
    public IActionResult ChangeUserPassword([FromBody] AdminChangePasswordRequest request)
    {
        var adminUsername = HttpContext.Session.GetString("Username");
        var role = HttpContext.Session.GetString("UserRole");

        if (adminUsername != "opcadmin" || role != "Administrator")
        {
            _logger.LogWarning($"Unauthorized password change attempt by {adminUsername}");
            return Unauthorized(new { message = "Access denied: Only opcadmin can change other users' passwords" });
        }

        if (string.IsNullOrWhiteSpace(request.TargetUsername) || string.IsNullOrWhiteSpace(request.NewPassword))
        {
            return BadRequest(new { message = "Target username and new password are required" });
        }

        if (request.NewPassword.Length < 6)
        {
            return BadRequest(new { message = "New password must be at least 6 characters" });
        }

        var success = _authService.ChangeUserPassword(request.TargetUsername, request.NewPassword, adminUsername!);
        
        if (success)
        {
            _logger.LogInformation($"Password changed for user '{request.TargetUsername}' by admin '{adminUsername}'");
            return Ok(new { success = true, message = $"Password changed successfully for user '{request.TargetUsername}'" });
        }
        else
        {
            return BadRequest(new { message = "Failed to change password" });
        }
    }

    /// <summary>
    /// Toggle user enabled/disabled status (opcadmin only)
    /// </summary>
    [HttpPost("admin/toggle-user")]
    public IActionResult ToggleUserEnabled([FromBody] ToggleUserRequest request)
    {
        // Verify authentication
        var isAuthenticated = HttpContext.Session.GetString("IsAuthenticated") == "true";
        var currentUsername = HttpContext.Session.GetString("Username");

        if (!isAuthenticated || string.IsNullOrEmpty(currentUsername))
        {
            return Unauthorized(new { success = false, message = "Not authenticated" });
        }

        // Only opcadmin can toggle users
        if (currentUsername != "opcadmin")
        {
            return Forbid();
        }

        var success = _authService.ToggleUserEnabled(request.Username, request.Enabled, currentUsername);
        if (!success)
        {
            return BadRequest(new { success = false, message = "Failed to update user status" });
        }

        return Ok(new { success = true, message = $"User {request.Username} has been {(request.Enabled ? "enabled" : "disabled")}" });
    }

    /// <summary>
    /// Get all users (opcadmin only)
    /// </summary>
    [HttpGet("admin/users")]
    public IActionResult GetAllUsers()
    {
        // Verify authentication
        var isAuthenticated = HttpContext.Session.GetString("IsAuthenticated") == "true";
        var currentUsername = HttpContext.Session.GetString("Username");

        if (!isAuthenticated || string.IsNullOrEmpty(currentUsername))
        {
            return Unauthorized(new { success = false, message = "Not authenticated" });
        }

        // Only opcadmin can view users
        if (currentUsername != "opcadmin")
        {
            return Forbid();
        }

        var users = _authService.GetAllUsers(currentUsername);
        return Ok(new { success = true, users = users });
    }
}

public class ChangePasswordRequest
{
    public string OldPassword { get; set; } = string.Empty;
    public string NewPassword { get; set; } = string.Empty;
}

public class AdminChangePasswordRequest
{
    public string TargetUsername { get; set; } = string.Empty;
    public string NewPassword { get; set; } = string.Empty;
}

public class ToggleUserRequest
{
    public string Username { get; set; } = string.Empty;
    public bool Enabled { get; set; }
}
