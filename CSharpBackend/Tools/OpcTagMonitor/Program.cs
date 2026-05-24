using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.AspNetCore.SignalR.Client;

const string defaultHubUrl = "http://localhost:5001/opcHub";
const string defaultStatusUrl = "http://localhost:5001/api/opc/status";

string hubUrl = defaultHubUrl;
string statusUrl = defaultStatusUrl;
string? tagFilter = null;
bool showRawJson = false;
bool quiet = false;

for (int i = 0; i < args.Length; i++)
{
    switch (args[i])
    {
        case "--hub":
        case "-h":
            if (i + 1 < args.Length)
            {
                hubUrl = args[++i];
            }
            break;
        case "--status":
            if (i + 1 < args.Length)
            {
                statusUrl = args[++i];
            }
            break;
        case "--tag":
        case "-t":
            if (i + 1 < args.Length)
            {
                tagFilter = args[++i];
            }
            break;
        case "--json":
            showRawJson = true;
            break;
        case "--quiet":
            quiet = true;
            break;
        case "--help":
        case "-?":
            PrintUsage();
            return;
    }
}

Console.CancelKeyPress += (_, e) =>
{
    Console.WriteLine("\nStopping monitor (CTRL+C detected)...");
    e.Cancel = true;
};

using var httpClient = new HttpClient();

await ProbeOpcStatusAsync(httpClient, statusUrl);

var jsonOptions = new JsonSerializerOptions
{
    PropertyNameCaseInsensitive = true,
    Converters = { new JsonStringEnumConverter() }
};

var connection = new HubConnectionBuilder()
    .WithUrl(hubUrl)
    .WithAutomaticReconnect()
    .Build();

connection.Closed += error =>
{
    if (error != null)
    {
        Console.WriteLine($"Connection closed: {error.Message}");
    }
    else
    {
        Console.WriteLine("Connection closed by server");
    }

    return Task.CompletedTask;
};

connection.Reconnected += connectionId =>
{
    Console.WriteLine($"Reconnected to hub (ConnectionId={connectionId ?? "n/a"})");
    return Task.CompletedTask;
};

connection.On<JsonElement>("TagValuesUpdated", payload =>
{
    List<TagValueMessage>? message;
    try
    {
        message = payload.Deserialize<List<TagValueMessage>>(jsonOptions);
    }
    catch (Exception ex)
    {
        Console.WriteLine($"Warning: Failed to deserialize payload ({ex.Message})");
        return;
    }

    if (message == null || message.Count == 0)
        return;

    IEnumerable<TagValueMessage> items = message;

    if (!string.IsNullOrEmpty(tagFilter))
    {
        items = items.Where(v => v.ItemID.Contains(tagFilter, StringComparison.OrdinalIgnoreCase));
    }

    var materialized = items.ToList();
    if (materialized.Count == 0)
        return;

    if (!quiet)
    {
        Console.WriteLine($"[{DateTimeOffset.Now:HH:mm:ss}] Samples received: {materialized.Count}");
    }

    foreach (var sample in materialized)
    {
        if (showRawJson)
        {
            string json = JsonSerializer.Serialize(sample, new JsonSerializerOptions { WriteIndented = false });
            Console.WriteLine(json);
        }
        else
        {
            Console.WriteLine($"  {sample.Timestamp:HH:mm:ss.fff} | {sample.ItemID,-30} | Value={sample.Value,-12} | Quality={sample.Quality,-8} | Server={sample.ServerConnection}");
        }
    }
});

Console.WriteLine($"Connecting to {hubUrl} ...");
await connection.StartAsync();
Console.WriteLine("Connected. Waiting for TagValuesUpdated events (CTRL+C to exit)...");

await SubscribeToTagsAsync(connection, tagFilter, quiet);

// Keep the process alive until cancelled
var completion = new TaskCompletionSource();
Console.CancelKeyPress += (_, __) => completion.TrySetResult();
await completion.Task;

await connection.StopAsync();
await connection.DisposeAsync();

static async Task ProbeOpcStatusAsync(HttpClient client, string statusUrl)
{
    try
    {
        using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(5));
        var response = await client.GetAsync(statusUrl, cts.Token);
        if (!response.IsSuccessStatusCode)
        {
            Console.WriteLine($"Warning: OPC status endpoint returned {(int)response.StatusCode} {response.ReasonPhrase}");
            return;
        }

        var content = await response.Content.ReadFromJsonAsync<OpcStatusResponse>(cancellationToken: cts.Token);
        if (content != null)
        {
            Console.WriteLine($"OPC status: connected={content.IsConnected}, server='{content.ServerName ?? ""}'");
        }
        else
        {
            Console.WriteLine("Warning: OPC status endpoint returned empty payload");
        }
    }
    catch (Exception ex)
    {
        Console.WriteLine($"Warning: Unable to probe OPC status endpoint ({ex.Message})");
    }
}

static async Task SubscribeToTagsAsync(HubConnection connection, string? filter, bool quiet)
{
    try
    {
        var tags = await connection.InvokeAsync<List<TagInfoMessage>>("BrowseTags");
        if (tags == null || tags.Count == 0)
        {
            Console.WriteLine("Warning: Server returned no tags. Waiting for updates without subscription.");
            return;
        }

        var selected = tags
            .Select(t => t.ItemID)
            .Where(id => !string.IsNullOrEmpty(id))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToList();

        if (!string.IsNullOrEmpty(filter))
        {
            var filtered = selected
                .Where(id => id.Contains(filter, StringComparison.OrdinalIgnoreCase))
                .ToList();
            if (filtered.Count > 0)
                selected = filtered;
            else if (!quiet)
                Console.WriteLine($"Filter '{filter}' did not match any tags; subscribing to all {selected.Count} tags.");
        }

        await connection.InvokeAsync("SubscribeToTags", selected);

        if (!quiet)
        {
            var preview = string.Join(", ", selected.Take(5));
            if (selected.Count > 5)
                preview += ", ...";
            Console.WriteLine($"Subscribed to {selected.Count} tag(s): {preview}");
        }
    }
    catch (Exception ex)
    {
        Console.WriteLine($"Warning: Unable to subscribe to tags ({ex.Message})");
    }
}

static void PrintUsage()
{
    Console.WriteLine("Usage: dotnet run --project Tools/OpcTagMonitor -- [options]");
    Console.WriteLine("Options:");
    Console.WriteLine("  --hub <url>       Hub URL (default http://localhost:5001/opcHub)");
    Console.WriteLine("  --status <url>    Status endpoint URL (default http://localhost:5001/api/opc/status)");
    Console.WriteLine("  --tag <filter>    Only show tags containing the filter text");
    Console.WriteLine("  --json            Print raw JSON payload instead of formatted output");
    Console.WriteLine("  --quiet           Suppress summary lines");
    Console.WriteLine("  --help            Show usage information");
}

sealed record TagValueMessage
{
    [JsonPropertyName("ItemID")]
    public string ItemID { get; init; } = string.Empty;

    [JsonPropertyName("DisplayName")]
    public string? DisplayName { get; init; }
        = string.Empty;

    [JsonPropertyName("Value")]
    public string? Value { get; init; }
        = string.Empty;

    [JsonPropertyName("Quality")]
    public string Quality { get; init; } = "U";

    [JsonPropertyName("Timestamp")]
    public DateTime Timestamp { get; init; }
        = DateTime.MinValue;

    [JsonPropertyName("DataType")]
    public string? DataType { get; init; }
        = string.Empty;

    [JsonPropertyName("ServerConnection")]
    public string? ServerConnection { get; init; }
        = string.Empty;
}

sealed record TagInfoMessage
{
    [JsonPropertyName("ItemID")]
    public string ItemID { get; init; } = string.Empty;
}
sealed record OpcStatusResponse
{
    [JsonPropertyName("isConnected")]
    public bool IsConnected { get; init; }
        = false;

    [JsonPropertyName("serverName")]
    public string? ServerName { get; init; }
        = string.Empty;
}
