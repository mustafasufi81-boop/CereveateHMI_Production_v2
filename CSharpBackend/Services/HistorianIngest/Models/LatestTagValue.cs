namespace OpcDaWebBrowser.Services.HistorianIngest.Models;

/// <summary>
/// Latest value for a tag from the historian database
/// </summary>
public class LatestTagValue
{
    public string TagId { get; set; } = string.Empty;
    public DateTime Timestamp { get; set; }
    public object? Value { get; set; }
    public string Quality { get; set; } = "U";
}
