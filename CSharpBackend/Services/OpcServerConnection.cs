using System.Collections.Concurrent;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;
using OpcRcw.Da;
using OpcRcw.Comn;
using Microsoft.Extensions.Logging;
using OpcDaWebBrowser.Services.Logging;
using System.Diagnostics;

namespace OpcDaWebBrowser.Services;

/// <summary>
/// Encapsulates a single OPC group with its COM objects and tag list
/// </summary>
public class OpcGroupReader
{
    public int GroupHandle { get; set; }
    public IOPCItemMgt? ItemMgt { get; set; }
    public IOPCSyncIO? SyncIO { get; set; }
    public object? GroupObject { get; set; }
    public List<TagMonitor> Tags { get; set; } = new();
    public int Capacity { get; set; } = 2000;
    public int GroupIndex { get; set; }
}

/// <summary>
/// Represents a single OPC DA server connection with polling mechanism
/// Supports up to 10,000 tags using 5 groups of 2,000 tags each
/// </summary>
public class OpcServerConnection : IDisposable
{
    public string ConnectionId { get; }
    public string ServerProgID { get; }
    public string ServerCLSID { get; }
    public string Host { get; }
    public bool IsLocal => string.IsNullOrEmpty(Host);
    public DateTime ConnectedAt { get; private set; }
    public DateTime LastPollTime { get; private set; }
    public string Status { get; private set; } = "Disconnected";
    
    private IOPCServer? _opcServer;
    private readonly List<OpcGroupReader> _groups = new();
    private readonly object _lock = new();
    private CancellationTokenSource? _pollingCts;
    private Task? _pollingTask;
    private readonly int _pollingIntervalMs;
    private int _currentPollingIntervalMs;
    private int _consecutivePollErrors = 0;
    private List<TagValue>? _cachedValues;
    private readonly ILogger<OpcServerConnection> _logger;
    private readonly OpcDaWebBrowser.Services.Health.IHealthStatusService? _healthService;
    private readonly OpcStaDispatcher? _dispatcher;
    
    private const int GROUPS_COUNT = 5;
    private const int TAGS_PER_GROUP = 2000;
    private const int MAX_STALE_MS = 100; // Threshold for detecting stale timestamps (adjust based on polling rate)

    // Timestamp correction tracking per tag (thread-safe for 10K+ tags)
    private readonly ConcurrentDictionary<string, TimestampState> _timestampStates = new();

    public int MonitoredTagCount => _groups.Sum(g => g.Tags.Count);
    public bool IsConnected => _opcServer != null && Status == "Connected";

    public event EventHandler<TagValuesEventArgs>? TagValuesUpdated;

    public OpcServerConnection(string serverProgID, string host = "", string clsid = "", int pollingIntervalMs = 1000, ILogger<OpcServerConnection>? logger = null, OpcDaWebBrowser.Services.Health.IHealthStatusService? healthService = null, OpcStaDispatcher? dispatcher = null)
    {
        ServerProgID = serverProgID;
        ServerCLSID = clsid ?? "";
        Host = host ?? "";
        _pollingIntervalMs = pollingIntervalMs;
        ConnectionId = IsLocal ? serverProgID : $"{serverProgID}@{host}";
        _logger = logger ?? throw new ArgumentNullException(nameof(logger), "Logger is required for OpcServerConnection");
        _healthService = healthService;
        _dispatcher = dispatcher;
    }

    public void Connect()
    {
        lock (_lock)
        {
            if (IsConnected) return;

            var correlationId = CorrelationContext.NewCycle();
            var sw = Stopwatch.StartNew();

            try
            {
                _logger.LogInformation("[{EventType}] Starting connection | server={Server} | host={Host} | clsid={CLSID} | Thread={ThreadId} | Apartment={Apartment} | trace={CorrelationId}",
                    LogEventType.OPC_CONNECT, ServerProgID, Host, ServerCLSID,
                    Thread.CurrentThread.ManagedThreadId,
                    Thread.CurrentThread.GetApartmentState(),
                    correlationId);
                Type? serverType = null;

                // Try CLSID first (recommended for Windows XP compatibility)
                if (!string.IsNullOrWhiteSpace(ServerCLSID))
                {
                    try
                    {
                        _logger.LogDebug("[{EventType}] Attempting CLSID resolution | clsid={CLSID} | trace={CorrelationId}",
                            LogEventType.OPC_CONNECT, ServerCLSID, correlationId);
                        string cleanClsid = ServerCLSID.Trim().Trim('{', '}');
                        Guid clsidGuid = Guid.Parse(cleanClsid);
                        serverType = IsLocal
                            ? Type.GetTypeFromCLSID(clsidGuid)
                            : Type.GetTypeFromCLSID(clsidGuid, Host);
                        _logger.LogDebug("[{EventType}] CLSID resolution result={Result} | trace={CorrelationId}",
                            LogEventType.OPC_CONNECT, serverType != null ? "SUCCESS" : "NULL", correlationId);
                    }
                    catch (Exception clsidEx)
                    {
                        _logger.LogContextualError(clsidEx, LogEventType.OPC_CONNECT_ERROR,
                            $"CLSID resolution failed | clsid={ServerCLSID}",
                            new Dictionary<string, object> { ["server"] = ServerProgID, ["host"] = Host ?? "local" });
                        throw new Exception($"Invalid CLSID format '{ServerCLSID}': {clsidEx.Message}");
                    }
                }
                // Fallback to ProgID (may fail on Windows XP)
                else
                {
                    _logger.LogDebug("[{EventType}] Attempting ProgID resolution | progID={ProgID} | trace={CorrelationId}",
                        LogEventType.OPC_CONNECT, ServerProgID, correlationId);
                    serverType = IsLocal
                        ? Type.GetTypeFromProgID(ServerProgID)
                        : Type.GetTypeFromProgID(ServerProgID, Host);
                    _logger.LogDebug("[{EventType}] ProgID resolution result={Result} | trace={CorrelationId}",
                        LogEventType.OPC_CONNECT, serverType != null ? "SUCCESS" : "NULL", correlationId);
                }

                if (serverType == null)
                {
                    string errorMsg = !string.IsNullOrWhiteSpace(ServerCLSID)
                        ? $"Cannot create type from CLSID '{ServerCLSID}' on {(IsLocal ? "local machine" : $"remote host '{Host}'")}."
                        : IsLocal 
                            ? $"Cannot find ProgID '{ServerProgID}' on local machine. Ensure OPC server is installed."
                            : $"Cannot find ProgID '{ServerProgID}' on remote host '{Host}'. For Windows XP, use CLSID instead.";
                    _logger.LogError("[{EventType}] {ErrorMessage} | trace={CorrelationId}",
                        LogEventType.OPC_CONNECT_ERROR, errorMsg, correlationId);
                    throw new Exception(errorMsg);
                }

                _logger.LogDebug("[{EventType}] Creating COM Activator instance | trace={CorrelationId}",
                    LogEventType.OPC_CONNECT, correlationId);
                _opcServer = (IOPCServer)Activator.CreateInstance(serverType)!;
                ConnectedAt = DateTime.Now;
                Status = "Connected";

                // Create 5 OPC groups for tag monitoring (2000 tags each)
                _logger.LogDebug("[{EventType}] Creating {GroupCount} OPC groups | trace={CorrelationId}",
                    LogEventType.OPC_CONNECT, GROUPS_COUNT, correlationId);
                for (int i = 0; i < GROUPS_COUNT; i++)
                {
                    Guid iid = typeof(IOPCItemMgt).GUID;
                    _opcServer.AddGroup(
                        $"Group_{ConnectionId}_{i}",
                        1, // Active
                        _pollingIntervalMs,  // Requested update rate
                        0,
                        IntPtr.Zero,
                        IntPtr.Zero,
                        0,
                        out int groupHandle,
                        out int revisedUpdateRate,  // CRITICAL: Capture actual rate OPC server supports
                        ref iid,
                        out object group);

                    var itemMgt = (IOPCItemMgt)group;
                    var syncIO = (IOPCSyncIO)itemMgt;
                    
                    _groups.Add(new OpcGroupReader
                    {
                        GroupHandle = groupHandle,
                        ItemMgt = itemMgt,
                        SyncIO = syncIO,
                        GroupObject = group,
                        Capacity = TAGS_PER_GROUP,
                        GroupIndex = i
                    });
                    
                    _logger.LogDebug("[{EventType}] Group {Index} created | handle={Handle} | requested={RequestedMs}ms | revised={RevisedMs}ms | trace={CorrelationId}",
                        LogEventType.OPC_CONNECT, i, groupHandle, _pollingIntervalMs, revisedUpdateRate, correlationId);
                }

                // Start single-threaded polling loop with backoff
                _currentPollingIntervalMs = _pollingIntervalMs;
                StartPollingLoop();
                
                sw.Stop();
                _logger.LogOpcOperation(LogEventType.OPC_CONNECT, 
                    $"Connection established | server={ServerProgID} | host={Host ?? "local"} | groups={GROUPS_COUNT}",
                    sw.ElapsedMilliseconds, MonitoredTagCount);

                // Push initial health state on connect
                _healthService?.UpdateOpcHealth(new OpcDaWebBrowser.Services.Health.OpcHealth
                {
                    Status = "Connected",
                    ServerName = ConnectionId,
                    TagsConnected = MonitoredTagCount,
                    TagsActive = MonitoredTagCount,
                    UpdateRateMs = _pollingIntervalMs,
                    LastUpdate = DateTime.Now,
                    ErrorCount = 0,
                    HealthScore = 100
                });
            }
            catch (COMException comEx)
            {
                string errorDetail = comEx.ErrorCode switch
                {
                    unchecked((int)0x80070005) => $"Access Denied (0x80070005). DCOM permissions required for remote host '{Host}'. Configure DCOM security.",
                    unchecked((int)0x800706BA) => $"RPC Server Unavailable (0x800706BA). Remote host '{Host}' not reachable or firewall blocking.",
                    unchecked((int)0x80080005) => $"Server Execution Failed (0x80080005). OPC server '{ServerProgID}' cannot start on '{Host}'.",
                    unchecked((int)0x800401F0) => $"Class Not Registered (0x800401F0). OPC server '{ServerProgID}' not installed on '{Host}'.",
                    _ => $"COM Error (0x{comEx.ErrorCode:X8}): {comEx.Message}"
                };
                Status = $"Error: {errorDetail}";
                
                _logger.LogContextualError(comEx, LogEventType.OPC_CONNECT_ERROR,
                    $"COM connection failed | errorCode=0x{comEx.ErrorCode:X8}",
                    new Dictionary<string, object> { 
                        ["server"] = ServerProgID, 
                        ["host"] = Host ?? "local", 
                        ["clsid"] = ServerCLSID 
                    });
                
                Cleanup();
                throw new Exception(errorDetail, comEx);
            }
            catch (Exception ex)
            {
                Status = $"Error: {ex.Message}";
                
                _logger.LogContextualError(ex, LogEventType.OPC_CONNECT_ERROR,
                    "Connection failed (non-COM error)",
                    new Dictionary<string, object> { 
                        ["server"] = ServerProgID, 
                        ["host"] = Host ?? "local" 
                    });
                
                Cleanup();
                throw;
            }
        }
    }

    public void Disconnect()
    {
        lock (_lock)
        {
            _pollingCts?.Cancel();
            try { _pollingTask?.Wait(2000); } catch { }
            _pollingTask = null;
            _pollingCts = null;

            if (_opcServer != null)
            {
                foreach (var group in _groups)
                {
                    try
                    {
                        if (group.GroupHandle != 0)
                        {
                            _opcServer.RemoveGroup(group.GroupHandle, 0);
                        }
                    }
                    catch { }
                }
            }

            Cleanup();
            Status = "Disconnected";

            _healthService?.UpdateOpcHealth(new OpcDaWebBrowser.Services.Health.OpcHealth
            {
                Status = "Disconnected",
                ServerName = ConnectionId,
                TagsConnected = 0,
                TagsActive = 0,
                UpdateRateMs = _pollingIntervalMs,
                LastUpdate = DateTime.Now,
                ErrorCount = _consecutivePollErrors,
                HealthScore = 0
            });
        }
    }

    private void StartPollingLoop()
    {
        _pollingCts?.Cancel();
        _pollingCts = new CancellationTokenSource();
        var token = _pollingCts.Token;

        _pollingTask = Task.Run(async () =>
        {
            while (!token.IsCancellationRequested)
            {
                try
                {
                    await Task.Delay(_currentPollingIntervalMs, token);
                    var success = _dispatcher != null
                        ? await _dispatcher.InvokeAsync(() => PollOnce())
                        : PollOnce();

                    if (success)
                    {
                        _consecutivePollErrors = 0;
                        _currentPollingIntervalMs = _pollingIntervalMs;
                    }
                    else
                    {
                        _consecutivePollErrors++;
                        _currentPollingIntervalMs = Math.Min(_pollingIntervalMs * (int)Math.Pow(2, _consecutivePollErrors), _pollingIntervalMs * 8);
                    }
                }
                catch (TaskCanceledException)
                {
                    break;
                }
                catch (Exception ex)
                {
                    _logger.LogWarning(ex, "[{EventType}] Poll loop error", LogEventType.OPC_READ_ERROR);
                    _consecutivePollErrors++;
                    _currentPollingIntervalMs = Math.Min(_pollingIntervalMs * (int)Math.Pow(2, _consecutivePollErrors), _pollingIntervalMs * 8);
                }
            }
        }, token);
    }

    private void Cleanup()
    {
        foreach (var group in _groups)
        {
            if (group.ItemMgt != null)
            {
                try { Marshal.ReleaseComObject(group.ItemMgt); } catch { }
                group.ItemMgt = null;
            }
            
            if (group.GroupObject != null)
            {
                try { Marshal.ReleaseComObject(group.GroupObject); } catch { }
                group.GroupObject = null;
            }
            
            group.SyncIO = null;
            group.Tags.Clear();
        }
        
        _groups.Clear();

        if (_opcServer != null)
        {
            try { Marshal.ReleaseComObject(_opcServer); } catch { }
            _opcServer = null;
        }
    }

    public List<TagInfo> BrowseTags()
    {
        lock (_lock)
        {
            if (_opcServer == null)
                throw new Exception("Not connected to server");

            List<TagInfo> tags = new();
            IOPCBrowseServerAddressSpace? browser = _opcServer as IOPCBrowseServerAddressSpace;

            if (browser == null)
            {
                _logger.LogWarning("[OPC BROWSE] Server does not support browsing");
                return new List<TagInfo>();
            }

            try
            {
                _logger.LogInformation("[OPC BROWSE] Starting DEEP hierarchical browse from root");
                
                // Start from root
                browser.ChangeBrowsePosition(OPCBROWSEDIRECTION.OPC_BROWSE_TO, "");
                
                // Recursively browse all folders and tags
                BrowseRecursive(browser, "", tags, 0);
                
                _logger.LogInformation("[OPC BROWSE] TOTAL TAGS FOUND: {Count}", tags.Count);
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "[OPC BROWSE ERROR]");
            }

            return tags;
        }
    }

    private void BrowseRecursive(IOPCBrowseServerAddressSpace browser, string currentPath, List<TagInfo> tags, int depth)
    {
        if (depth > 20)
        {
            _logger.LogWarning("[OPC BROWSE] Max depth 20 reached at path: {Path}", currentPath);
            return;
        }

        try
        {
            // Get all branches (folders) at current level
            browser.BrowseOPCItemIDs(OPCBROWSETYPE.OPC_BRANCH, "", 0, 0, out OpcRcw.Da.IEnumString? enumBranches);
            
            if (enumBranches != null)
            {
                string[] branchBuffer = new string[100];
                while (true)
                {
                    enumBranches.RemoteNext(100, branchBuffer, out int fetchedBranches);
                    if (fetchedBranches == 0) break;

                    for (int i = 0; i < fetchedBranches; i++)
                    {
                        if (!string.IsNullOrEmpty(branchBuffer[i]))
                        {
                            string branchName = branchBuffer[i];
                            string branchPath = string.IsNullOrEmpty(currentPath) ? branchName : $"{currentPath}.{branchName}";
                            
                            _logger.LogDebug("[OPC BROWSE] Found folder: {Path} at depth {Depth}", branchPath, depth);
                            
                            // Add folder to list
                            tags.Add(new TagInfo
                            {
                                Name = branchName,
                                ItemID = branchPath,
                                IsFolder = true,
                                Path = currentPath,
                                ServerConnection = ConnectionId
                            });

                            // Move into this branch and recurse
                            try
                            {
                                browser.ChangeBrowsePosition(OPCBROWSEDIRECTION.OPC_BROWSE_DOWN, branchName);
                                BrowseRecursive(browser, branchPath, tags, depth + 1);
                                browser.ChangeBrowsePosition(OPCBROWSEDIRECTION.OPC_BROWSE_UP, "");
                            }
                            catch (Exception ex)
                            {
                                _logger.LogDebug("[OPC BROWSE] Cannot enter folder {Folder}: {Error}", branchName, ex.Message);
                            }
                        }
                    }

                    if (fetchedBranches < 100) break;
                }
                Marshal.ReleaseComObject(enumBranches);
            }

            // Get all leaves (actual tags) at current level
            browser.BrowseOPCItemIDs(OPCBROWSETYPE.OPC_LEAF, "", 0, 0, out OpcRcw.Da.IEnumString? enumLeaves);
            
            if (enumLeaves != null)
            {
                string[] leafBuffer = new string[100];
                while (true)
                {
                    enumLeaves.RemoteNext(100, leafBuffer, out int fetchedLeaves);
                    if (fetchedLeaves == 0) break;

                    for (int i = 0; i < fetchedLeaves; i++)
                    {
                        if (!string.IsNullOrEmpty(leafBuffer[i]))
                        {
                            string leafName = leafBuffer[i];
                            string itemID = leafName;
                            
                            // Try to get full qualified ItemID
                            try
                            {
                                browser.GetItemID(leafName, out string fullItemID);
                                if (!string.IsNullOrEmpty(fullItemID))
                                    itemID = fullItemID;
                            }
                            catch { }

                            tags.Add(new TagInfo
                            {
                                Name = leafName,
                                ItemID = itemID,
                                IsFolder = false,
                                Path = currentPath,
                                ServerConnection = ConnectionId
                            });
                        }
                    }

                    if (fetchedLeaves < 100) break;
                }
                Marshal.ReleaseComObject(enumLeaves);
            }
        }
        catch (Exception ex)
        {
            _logger.LogDebug("[OPC BROWSE] Error at path {Path}: {Error}", currentPath, ex.Message);
        }
    }

    private List<TagInfo> BrowseFlatNamespace(IOPCBrowseServerAddressSpace browser)
    {
        List<TagInfo> tags = new();
        try
        {
            // Try to get all items in flat namespace
            browser.ChangeBrowsePosition(OPCBROWSEDIRECTION.OPC_BROWSE_TO, "");
            
            // Get all leaves (actual tags)
            string[] leaves = GetBrowseItems(browser, OPCBROWSETYPE.OPC_LEAF);
            _logger.LogInformation("[OPC BROWSE FLAT] Found {Count} leaf items", leaves.Length);
            
            foreach (string leaf in leaves)
            {
                string itemID = leaf;
                try
                {
                    browser.GetItemID(leaf, out string fullItemID);
                    if (!string.IsNullOrEmpty(fullItemID))
                        itemID = fullItemID;
                }
                catch
                {
                    // Use leaf name as-is if GetItemID fails
                }

                tags.Add(new TagInfo
                {
                    Name = leaf,
                    ItemID = itemID,
                    IsFolder = false,
                    Path = "",
                    ServerConnection = ConnectionId
                });
            }
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "[OPC BROWSE FLAT ERROR]");
        }
        return tags;
    }

    private void BrowseRecursive(IOPCBrowseServerAddressSpace browser, string currentPath, List<TagInfo> tags)
    {
        try
        {
            // Get branches
            string[] branches = GetBrowseItems(browser, OPCBROWSETYPE.OPC_BRANCH);
            foreach (string branch in branches)
            {
                string path = string.IsNullOrEmpty(currentPath) ? branch : $"{currentPath}.{branch}";
                tags.Add(new TagInfo 
                { 
                    Name = branch, 
                    ItemID = path, 
                    IsFolder = true, 
                    Path = currentPath,
                    ServerConnection = ConnectionId
                });

                try
                {
                    browser.ChangeBrowsePosition(OPCBROWSEDIRECTION.OPC_BROWSE_DOWN, branch);
                    BrowseRecursive(browser, path, tags);
                    browser.ChangeBrowsePosition(OPCBROWSEDIRECTION.OPC_BROWSE_UP, "");
                }
                catch { }
            }

            // Get leaves
            string[] leaves = GetBrowseItems(browser, OPCBROWSETYPE.OPC_LEAF);
            foreach (string leaf in leaves)
            {
                string itemID;
                try
                {
                    browser.GetItemID(leaf, out itemID);
                }
                catch
                {
                    itemID = string.IsNullOrEmpty(currentPath) ? leaf : $"{currentPath}.{leaf}";
                }

                tags.Add(new TagInfo 
                { 
                    Name = leaf, 
                    ItemID = itemID, 
                    IsFolder = false, 
                    Path = currentPath,
                    ServerConnection = ConnectionId
                });
            }
        }
        catch { }
    }

    private string[] GetBrowseItems(IOPCBrowseServerAddressSpace browser, OPCBROWSETYPE browseType)
    {
        try
        {
            _logger.LogDebug("[OPC BROWSE] GetBrowseItems called for type: {Type}", browseType);
            browser.BrowseOPCItemIDs(browseType, "", 0, 0, out OpcRcw.Da.IEnumString? enumString);
            
            if (enumString == null)
            {
                _logger.LogDebug("[OPC BROWSE] BrowseOPCItemIDs returned null enumString");
                return Array.Empty<string>();
            }

            List<string> items = new();
            string[] buffer = new string[100];

            while (true)
            {
                enumString.RemoteNext(100, buffer, out int fetched);
                _logger.LogDebug("[OPC BROWSE] Fetched {Count} items in this batch", fetched);
                
                if (fetched == 0) break;

                for (int i = 0; i < fetched; i++)
                {
                    if (!string.IsNullOrEmpty(buffer[i]))
                    {
                        items.Add(buffer[i]);
                    }
                }

                if (fetched < 100) break;
            }

            Marshal.ReleaseComObject(enumString);
            _logger.LogInformation("[OPC BROWSE] Total items retrieved: {Count}", items.Count);
            return items.ToArray();
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "[OPC BROWSE ERROR] GetBrowseItems failed");
            return Array.Empty<string>();
        }
    }

    private List<TagInfo> GetKnownSimulationTags()
    {
        return new List<TagInfo>
        {
            new() { Name = "Random.Int4", ItemID = "Random.Int4", IsFolder = false, ServerConnection = ConnectionId },
            new() { Name = "Random.Real8", ItemID = "Random.Real8", IsFolder = false, ServerConnection = ConnectionId },
            new() { Name = "Random.String", ItemID = "Random.String", IsFolder = false, ServerConnection = ConnectionId },
            new() { Name = "Bucket Brigade.Int4", ItemID = "Bucket Brigade.Int4", IsFolder = false, ServerConnection = ConnectionId }
        };
    }

    public void AddTag(string itemID, string displayName)
    {
        lock (_lock)
        {
            if (_groups.Count == 0)
                throw new Exception("Not connected");

            // Check if tag already exists in any group
            foreach (var grp in _groups)
            {
                if (grp.Tags.Any(t => t.ItemID == itemID))
                    return;
            }

            // Find group with available capacity (round-robin)
            var targetGroup = _groups
                .Where(g => g.Tags.Count < g.Capacity)
                .OrderBy(g => g.Tags.Count)
                .FirstOrDefault();

            if (targetGroup == null)
                throw new Exception($"All groups at capacity ({TAGS_PER_GROUP} tags per group)");

            if (targetGroup.ItemMgt == null)
                throw new Exception("Group not initialized");

            _logger.LogInformation(
                "[OPC ADD TAG] Calling AddItems | tag={ItemID} | group={Group} | Thread={ThreadId} | Apartment={Apartment}",
                itemID, targetGroup.GroupIndex,
                Thread.CurrentThread.ManagedThreadId,
                Thread.CurrentThread.GetApartmentState());

            OPCITEMDEF[] itemDefs = new[]
            {
                new OPCITEMDEF
                {
                    szItemID = itemID,
                    bActive = 1,
                    hClient = targetGroup.Tags.Count + 1,
                    dwBlobSize = 0,
                    pBlob = IntPtr.Zero,
                    vtRequestedDataType = 0
                }
            };

            OPCITEMRESULT result = default;
            try
            {
                targetGroup.ItemMgt.AddItems(1, itemDefs, out IntPtr resultsPtr, out IntPtr errorsPtr);

                result = (OPCITEMRESULT)Marshal.PtrToStructure(resultsPtr, typeof(OPCITEMRESULT))!;
                int[] errors = new int[1];
                Marshal.Copy(errorsPtr, errors, 0, 1);

                Marshal.FreeCoTaskMem(resultsPtr);
                Marshal.FreeCoTaskMem(errorsPtr);

                if (errors[0] != 0)
                {
                    _logger.LogError(
                        "[OPC ADD TAG] AddItems HRESULT error | tag={ItemID} | HRESULT=0x{HResult:X8} | Thread={ThreadId} | Apartment={Apartment}",
                        itemID, errors[0],
                        Thread.CurrentThread.ManagedThreadId,
                        Thread.CurrentThread.GetApartmentState());
                    throw new Exception($"Failed to add tag: 0x{errors[0]:X8}");
                }
            }
            catch (System.Runtime.InteropServices.COMException comEx)
            {
                _logger.LogError(
                    comEx,
                    "[OPC ADD TAG] COMException | tag={ItemID} | HRESULT=0x{HResult:X8} | Thread={ThreadId} | Apartment={Apartment}",
                    itemID, comEx.ErrorCode,
                    Thread.CurrentThread.ManagedThreadId,
                    Thread.CurrentThread.GetApartmentState());
                throw;
            }

            targetGroup.Tags.Add(new TagMonitor
            {
                ItemID = itemID,
                DisplayName = displayName,
                ServerHandle = result.hServer,
                ServerConnection = ConnectionId
            });
            _logger.LogDebug("[OPC ADD TAG] '{ItemID}' added to Group {Group}", itemID, targetGroup.GroupIndex);
        }
    }

    public void RemoveTag(string itemID)
    {
        lock (_lock)
        {
            foreach (var group in _groups)
            {
                var tag = group.Tags.FirstOrDefault(t => t.ItemID == itemID);
                if (tag != null && group.ItemMgt != null)
                {
                    try
                    {
                        int[] handles = new[] { tag.ServerHandle };
                        group.ItemMgt.RemoveItems(1, handles, out IntPtr errorsPtr);
                        Marshal.FreeCoTaskMem(errorsPtr);
                        group.Tags.Remove(tag);
                        _logger.LogDebug("[OPC REMOVE TAG] '{ItemID}' removed from Group {Group}", itemID, group.GroupIndex);
                    }
                    catch { }
                    break;
                }
            }
        }
    }

    private bool PollOnce()
    {
        try
        {
            if (!IsConnected || _groups.Count == 0 || MonitoredTagCount == 0)
                return true;

            // NEW CORRELATION ID PER POLL CYCLE (not per tag)
            var correlationId = CorrelationContext.NewCycle();
            
            var values = ReadTagValues();
            LastPollTime = DateTime.Now;
            _cachedValues = values;

            // Push OPC health snapshot on every successful poll (push-only, no UI polling)
            _healthService?.UpdateOpcHealth(new OpcDaWebBrowser.Services.Health.OpcHealth
            {
                Status = "Connected",
                ServerName = ConnectionId,
                TagsConnected = MonitoredTagCount,
                TagsActive = values.Count,
                UpdateRateMs = _currentPollingIntervalMs,
                LastUpdate = LastPollTime,
                ErrorCount = _consecutivePollErrors,
                HealthScore = values.Count > 0 ? 100 : 80
            });

            if (values.Count > 0)
            {
                TagValuesUpdated?.Invoke(this, new TagValuesEventArgs 
                { 
                    Values = values,
                    ServerConnection = ConnectionId
                });
            }

            return true;
        }
        catch (Exception ex)
        {
            Status = $"Poll Error: {ex.Message}";
            _logger.LogContextualError(ex, LogEventType.OPC_READ_ERROR,
                "Poll cycle failed",
                new Dictionary<string, object> { 
                    ["server"] = ServerProgID, 
                    ["tags"] = MonitoredTagCount.ToString() 
                });

            _healthService?.UpdateOpcHealth(new OpcDaWebBrowser.Services.Health.OpcHealth
            {
                Status = "Error",
                ServerName = ConnectionId,
                TagsConnected = MonitoredTagCount,
                TagsActive = 0,
                UpdateRateMs = _currentPollingIntervalMs,
                LastUpdate = DateTime.Now,
                ErrorCount = _consecutivePollErrors,
                LastError = ex.Message,
                HealthScore = 0
            });
            return false;
        }
    }

    public List<TagValue> GetCachedValues()
    {
        return _cachedValues != null ? new List<TagValue>(_cachedValues) : new List<TagValue>();
    }

    public List<TagValue> ReadTagValues()
    {
        var correlationId = CorrelationContext.Current; // Use existing cycle ID or create new one
        var sw = Stopwatch.StartNew();
        _logger.LogDebug(
            "[OPC READ] ReadTagValues | tags={TagCount} | Thread={ThreadId} | Apartment={Apartment}",
            MonitoredTagCount,
            Thread.CurrentThread.ManagedThreadId,
            Thread.CurrentThread.GetApartmentState());
        List<TagValue> allValues = new(MonitoredTagCount);
        
        // Read each group sequentially
        for (int groupIdx = 0; groupIdx < _groups.Count; groupIdx++)
        {
            var group = _groups[groupIdx];
            if (group.Tags.Count == 0)
                continue;
                
            try
            {
                var groupStart = Stopwatch.StartNew();
                var groupValues = ReadGroupValues(group);
                allValues.AddRange(groupValues);
                groupStart.Stop();
                
                // Only log slow group reads (>500ms threshold)
                if (groupStart.ElapsedMilliseconds > 500)
                {
                    _logger.LogWarning("[{EventType}] SLOW group read | group={Group} | tags={Tags} | duration={Duration}ms | trace={CorrelationId}",
                        LogEventType.OPC_READ_SLOW, groupIdx, groupValues.Count, groupStart.ElapsedMilliseconds, correlationId);
                }
            }
            catch (Exception ex)
            {
                _logger.LogContextualError(ex, LogEventType.OPC_READ_ERROR,
                    $"Group {groupIdx} read failed | tags={group.Tags.Count}",
                    new Dictionary<string, object> { 
                        ["server"] = ServerProgID, 
                        ["group"] = groupIdx.ToString() 
                    });
            }
        }
        
        sw.Stop();
        
        // Log full cycle summary (only if EnableOpcDiagnostics=true)
        if (sw.ElapsedMilliseconds > 1000 || allValues.Count < MonitoredTagCount)
        {
            _logger.LogOpcOperation(LogEventType.OPC_READ_CYCLE,
                $"Cycle completed | success={allValues.Count} | total={MonitoredTagCount}",
                sw.ElapsedMilliseconds, allValues.Count);
        }
        
        return allValues;
    }
    
    private List<TagValue> ReadGroupValues(OpcGroupReader group)
    {
        const int BATCH_SIZE = 500; // Read 500 tags per batch
        
        if (group.SyncIO == null || group.Tags.Count == 0)
            return new List<TagValue>();
        
        List<TagValue> values = new(group.Tags.Count);
        TagMonitor[] tagSnapshot;
        int[] handles;

        // Snapshot handles and tags atomically to avoid races with add/remove
        lock (_lock)
        {
            tagSnapshot = group.Tags.ToArray();
            handles = tagSnapshot.Select(t => t.ServerHandle).ToArray();
        }
        int opcItemStateSize = Marshal.SizeOf(typeof(OPCITEMSTATE));
        
        // Read in batches of 500
        for (int batchStart = 0; batchStart < handles.Length; batchStart += BATCH_SIZE)
        {
            int currentBatchSize = Math.Min(BATCH_SIZE, handles.Length - batchStart);
            int[] batchHandles = new int[currentBatchSize];
            Array.Copy(handles, batchStart, batchHandles, 0, currentBatchSize);
            
            IntPtr valuesPtr = IntPtr.Zero;
            IntPtr errorsPtr = IntPtr.Zero;
            
            try
            {
                // Read from OPC server cache (faster, respects server update rate)
                // Use OPC_DS_CACHE for cached reads, OPC_DS_DEVICE for direct device reads
                group.SyncIO.Read(OPCDATASOURCE.OPC_DS_CACHE, 
                    currentBatchSize, batchHandles,
                    out valuesPtr, out errorsPtr);
                
                // CRITICAL FIX: Loop only over currentBatchSize (not full handles array)
                for (int i = 0; i < currentBatchSize; i++)
                {
                    IntPtr itemPtr = IntPtr.Add(valuesPtr, i * opcItemStateSize);
                    OPCITEMSTATE state = (OPCITEMSTATE)Marshal.PtrToStructure(itemPtr, typeof(OPCITEMSTATE))!;
                    
                    // CRITICAL FIX: Map to correct tag using batchStart + i
                    var tag = tagSnapshot[batchStart + i];
                    
                    string quality = state.wQuality == 192 ? "GOOD" :
                                   state.wQuality >= 64 && state.wQuality < 128 ? "UNCERTAIN" : "BAD";
                    
                    // Convert FILETIME to DateTime with proper validation
                    long fileTime = ((long)state.ftTimeStamp.dwHighDateTime << 32) | (uint)state.ftTimeStamp.dwLowDateTime;
                    DateTime timestamp = GetCorrectedTimestamp(tag.ItemID, fileTime);
                    
                    string value, dataType;
                    try
                    {
                        value = state.vDataValue?.ToString() ?? "null";
                        dataType = state.vDataValue?.GetType().Name ?? "Unknown";
                    }
                    catch
                    {
                        value = "unmarshall_error";
                        dataType = "Unknown";
                    }
                    
                    values.Add(new TagValue
                    {
                        ItemID = tag.ItemID,
                        DisplayName = tag.DisplayName,
                        Value = value,
                        Quality = quality,
                        Timestamp = timestamp,
                        DataType = dataType,
                        ServerConnection = ConnectionId
                    });
                }
            }
            finally
            {
                // Per-batch cleanup
                if (valuesPtr != IntPtr.Zero)
                    Marshal.FreeCoTaskMem(valuesPtr);
                if (errorsPtr != IntPtr.Zero)
                    Marshal.FreeCoTaskMem(errorsPtr);
            }
        }
        
        return values;
    }

    /// <summary>
    /// Production-grade timestamp correction for 10K+ tags
    /// Handles stale OPC timestamps while preserving chronological order
    /// </summary>
    private DateTime GetCorrectedTimestamp(string itemId, long fileTime)
    {
        DateTime opcTimestamp = DateTime.MinValue;

        // RULE 1: Convert FILETIME to DateTime (UTC for consistency)
        if (fileTime > 0)
        {
            try
            {
                opcTimestamp = DateTime.FromFileTimeUtc(fileTime);
            }
            catch
            {
                opcTimestamp = DateTime.MinValue;
            }
        }

        // RULE 2: If OPC timestamp is invalid, use UtcNow
        if (opcTimestamp == DateTime.MinValue || opcTimestamp.Year < 2000)
        {
            return DateTime.UtcNow;
        }

        // RULE 3: Detect and correct stale timestamps per tag (thread-safe per tag)
        var state = _timestampStates.GetOrAdd(itemId, _ => new TimestampState());
        lock (state.Lock)
        {
            if (opcTimestamp == state.LastOpcTimestamp)
            {
                state.LastReturnedTimestamp = state.LastReturnedTimestamp.AddMilliseconds(MAX_STALE_MS);
            }
            else
            {
                state.LastReturnedTimestamp = opcTimestamp;
            }

            state.LastOpcTimestamp = opcTimestamp;
            return state.LastReturnedTimestamp;
        }
    }

    private class TimestampState
    {
        public DateTime LastOpcTimestamp = DateTime.MinValue;
        public DateTime LastReturnedTimestamp = DateTime.MinValue;
        public readonly object Lock = new();
    }

    public void Dispose()
    {
        Disconnect();
    }
}

public class TagMonitor
{
    public required string ItemID { get; set; }
    public required string DisplayName { get; set; }
    public required int ServerHandle { get; set; }
    public required string ServerConnection { get; set; }
}

public class TagInfo
{
    public required string Name { get; set; }
    public required string ItemID { get; set; }
    public required bool IsFolder { get; set; }
    public string Path { get; set; } = "";
    public string DataType { get; set; } = "Variant";
    public required string ServerConnection { get; set; }
}

public class TagValue
{
    public required string ItemID { get; set; }
    public required string DisplayName { get; set; }
    public required string Value { get; set; }
    public required string Quality { get; set; }
    public required DateTime Timestamp { get; set; }
    public required string DataType { get; set; }
    public required string ServerConnection { get; set; }
}

public class TagValuesEventArgs : EventArgs
{
    public required List<TagValue> Values { get; set; }
    public required string ServerConnection { get; set; }
}
