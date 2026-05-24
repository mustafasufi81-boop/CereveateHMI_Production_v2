using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using OpcDaWebBrowser.Services;

namespace OpcDaWebBrowser.Pages;

public class LoginModel : PageModel
{
    private readonly AuthenticationService _authService;
    private readonly ILogger<LoginModel> _logger;

    public string? ErrorMessage { get; set; }

    public LoginModel(AuthenticationService authService, ILogger<LoginModel> logger)
    {
        _authService = authService;
        _logger = logger;
    }

    public void OnGet()
    {
        // Check if already authenticated
        if (HttpContext.Session.GetString("IsAuthenticated") == "true")
        {
            Response.Redirect("/");
            return;
        }
    }

    public IActionResult OnPost(string username, string password)
    {
        try
        {
            var result = _authService.ValidateUser(username, password);
            if (!result.IsValid)
            {
                ErrorMessage = "Invalid username or password";
                _logger.LogWarning("Failed login for '{username}'", username);
                return Page();
            }

            HttpContext.Session.SetString("IsAuthenticated", "true");
            HttpContext.Session.SetString("Username", username);
            HttpContext.Session.SetString("UserRole", result.Role);
            _logger.LogInformation("User '{username}' logged in with role {role}", username, result.Role);
            return Redirect("/");
        }
        catch (Exception ex)
        {
            ErrorMessage = "Login error. Please try again.";
            _logger.LogError(ex, "Login failed for '{username}'", username);
            return Page();
        }
    }
}
