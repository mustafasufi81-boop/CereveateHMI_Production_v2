using Microsoft.AspNetCore.Mvc.RazorPages;

namespace OpcDaWebBrowser.Pages;

public class IndexModel : PageModel
{
    public string UserRole { get; set; } = "Viewer";
    public string Username { get; set; } = string.Empty;
    
    public void OnGet()
    {
        UserRole = HttpContext.Session.GetString("UserRole") ?? "Viewer";
        Username = HttpContext.Session.GetString("Username") ?? "Guest";
    }
}
