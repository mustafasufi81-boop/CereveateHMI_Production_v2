namespace PlcGateway.Transport;

/// <summary>
/// Tag value for transport (protocol-agnostic)
/// Used by both MQTT and REST API
/// </summary>
public class TransportTagValue
{
    public string PlcId { get; set; } = "";
    public string TagName { get; set; } = "";
    public string Address { get; set; } = "";
    public object? Value { get; set; }
    public string DataType { get; set; } = "double";
    public string Quality { get; set; } = "Good";
    public DateTime Timestamp { get; set; }
    public string? Unit { get; set; }
    
    /// <summary>
    /// Unique key for this tag
    /// </summary>
    public string Key => $"{PlcId}/{TagName}";
}

/// <summary>
/// Bulk message format for MQTT topic: plc/all
/// </summary>
public class TransportBulkMessage
{
    public DateTime Timestamp { get; set; }
    public int Count { get; set; }
    public List<TransportTagValue> Values { get; set; } = new();
}

/// <summary>
/// PLC Health Metrics for MQTT topic: plc/health
/// Published every 3 seconds with comprehensive health data
/// 
/// 18 HEALTH METRICS (from user's specification):
/// ═══════════════════════════════════════════════════════════════════════════════
/// | #  | Metric               | Source                    | Interpretation        |
/// |----|----------------------|---------------------------|------------------------|
/// | 1  | PLC Mode             | GSV Controller.Status     | FAULT → PLC unhealthy |
/// | 2  | Major Fault          | ControllerFault           | Immediate alarm       |
/// | 3  | Minor Fault          | MinorFaultBits            | Warning               |
/// | 4  | Avg Scan Time (ms)   | Task:MainTask.AvgScanTime | Rising = CPU stress   |
/// | 5  | Max Scan Time (ms)   | Task:MainTask.MaxScanTime | Spikes = overload     |
/// | 6  | Scan Load %          | AvgScan/TaskPeriod*100    | >70% = danger         |
/// | 7  | Task Overrun         | Task:MainTask.OverrunCount| Missed real-time      |
/// | 8  | Comm Latency (ms)    | t_response - t_request    | >500ms = warning      |
/// | 9  | Comm Timeout Rate    | timeouts/total_reads      | >1% = unstable        |
/// | 10 | Reconnect Rate       | reconnects/minute         | Network issue         |
/// | 11 | Open CIP Connections | CIP CM Object             | Near limit = risk     |
/// | 12 | Module Fault Count   | GSV(Module, Status)       | I/O issue             |
/// | 13 | I/O Task Faulted     | IOTaskFaulted             | Fieldbus issue        |
/// | 14 | Power Supply Status  | GSV(Module, PowerSupply)  | Electrical issue      |
/// | 15 | Temperature (°C)     | GSV(Chassis, Temp)        | Near max = risk       |
/// | 16 | Effective Poll Rate  | executed/scheduled*100    | Design KPI            |
/// | 17 | Failed Polls         | Driver stats              | PLC or network        |
/// | 18 | Health Score %       | Weighted avg              | Dashboard only        |
/// ═══════════════════════════════════════════════════════════════════════════════
/// </summary>
public class PlcHealthMetrics
{
    public DateTime Timestamp { get; set; }
    public string PlcId { get; set; } = "";
    public string PlcName { get; set; } = "";
    public string Protocol { get; set; } = "";
    public string IpAddress { get; set; } = "";
    public int Port { get; set; }
    
    // ═══════════════════════════════════════════════════════════════════
    // CONNECTION STATUS (Priority 4: PLC State)
    // ═══════════════════════════════════════════════════════════════════
    public bool IsConnected { get; set; }
    public string State { get; set; } = "Unknown";  // Running, Disconnected, Faulted
    
    // ═══════════════════════════════════════════════════════════════════
    // TIMING METRICS (Priority 1 & 5: Scan Time & Latency)
    // ═══════════════════════════════════════════════════════════════════
    /// <summary>Average time to read all tags from PLC (milliseconds)</summary>
    public double AverageReadTimeMs { get; set; }
    /// <summary>Last read cycle time (milliseconds)</summary>
    public double LastReadTimeMs { get; set; }
    /// <summary>Configured polling interval (milliseconds)</summary>
    public int PollingIntervalMs { get; set; }
    /// <summary>Time since last successful poll (seconds)</summary>
    public double SecondsSinceLastPoll { get; set; }
    
    // ═══════════════════════════════════════════════════════════════════
    // ERROR METRICS (Priority 6 & 7: Errors & Reconnections)
    // ═══════════════════════════════════════════════════════════════════
    /// <summary>Total polls since startup</summary>
    public long TotalPolls { get; set; }
    /// <summary>Successful polls since startup</summary>
    public long SuccessfulPolls { get; set; }
    /// <summary>Failed polls since startup</summary>
    public long FailedPolls { get; set; }
    /// <summary>Consecutive failures (resets on success)</summary>
    public int ConsecutiveFailures { get; set; }
    /// <summary>Success rate percentage (0-100)</summary>
    public double SuccessRatePercent { get; set; }
    /// <summary>Last error message (null if none)</summary>
    public string? LastError { get; set; }
    // ReconnectionCount moved to #10 section below
    
    // ═══════════════════════════════════════════════════════════════════
    // TAG STATISTICS
    // ═══════════════════════════════════════════════════════════════════
    /// <summary>Number of tags being polled</summary>
    public int TagCount { get; set; }
    /// <summary>Tags with Good quality</summary>
    public int GoodQualityTags { get; set; }
    /// <summary>Tags with Bad quality</summary>
    public int BadQualityTags { get; set; }
    /// <summary>Is tag pool data stale (not updated recently)</summary>
    public bool IsPoolStale { get; set; }
    
    // ═══════════════════════════════════════════════════════════════════
    // SCAN RATE SCHEDULER STATS
    // ═══════════════════════════════════════════════════════════════════
    /// <summary>Total scan cycles executed</summary>
    public long TotalScans { get; set; }
    /// <summary>Values cached (passed deadband)</summary>
    public long TotalCached { get; set; }
    /// <summary>Values filtered (didn't pass deadband)</summary>
    public long TotalFiltered { get; set; }
    /// <summary>Values transmitted to clients</summary>
    public long TotalTransmitted { get; set; }
    /// <summary>Current buffer size</summary>
    public int BufferedCount { get; set; }
    /// <summary>Tags by scan rate (e.g., {"200": 5, "1000": 27})</summary>
    public Dictionary<int, int> TagsByScanRate { get; set; } = new();
    
    // ═══════════════════════════════════════════════════════════════════
    // 18 HEALTH METRICS (Matching User's Table)
    // ═══════════════════════════════════════════════════════════════════
    
    // ─────────────────────────────────────────────────────────────────────
    // #1: PLC Mode - GSV(Controller, Status) → RUN=1, PROGRAM=2, FAULT=4
    // ─────────────────────────────────────────────────────────────────────
    /// <summary>#1 PLC Mode Code: RUN=1, PROGRAM=2, FAULT=4</summary>
    public int? PlcModeCode { get; set; }
    /// <summary>#1 PLC Mode String: "RUN", "PROGRAM", "FAULT", "UNKNOWN"</summary>
    public string PlcMode { get; set; } = "UNKNOWN";
    
    // ─────────────────────────────────────────────────────────────────────
    // #2: Major Fault - ControllerFault (BOOL) → true = fault, Immediate alarm
    // ─────────────────────────────────────────────────────────────────────
    /// <summary>#2 Major Fault Active (true = immediate alarm)</summary>
    public bool? MajorFaultActive { get; set; }
    /// <summary>#2 Major Fault Code (0 = no fault)</summary>
    public int? MajorFaultCode { get; set; }
    
    // ─────────────────────────────────────────────────────────────────────
    // #3: Minor Fault - MinorFaultBits (INT) → != 0 = Warning
    // ─────────────────────────────────────────────────────────────────────
    /// <summary>#3 Minor Fault Bits (!=0 means warning)</summary>
    public int? MinorFaultBits { get; set; }
    /// <summary>#3 Has Minor Fault (computed)</summary>
    public bool HasMinorFault => MinorFaultBits.HasValue && MinorFaultBits != 0;
    
    // ─────────────────────────────────────────────────────────────────────
    // #4: Avg Scan Time (ms) - Task:MainTask.AvgScanTime → Rising = CPU stress
    // ─────────────────────────────────────────────────────────────────────
    /// <summary>#4 Avg Scan Time (ms) from PLC - Rising = CPU stress</summary>
    public double? AvgScanTimeMs { get; set; }
    
    // ─────────────────────────────────────────────────────────────────────
    // #5: Max Scan Time (ms) - Task:MainTask.MaxScanTime → Spikes = overload
    // ─────────────────────────────────────────────────────────────────────
    /// <summary>#5 Max Scan Time (ms) from PLC - Spikes = overload</summary>
    public double? MaxScanTimeMs { get; set; }
    
    // ─────────────────────────────────────────────────────────────────────
    // #6: Scan Load % - (AvgScanTime / TaskPeriod) × 100 → >70% = danger
    // ─────────────────────────────────────────────────────────────────────
    /// <summary>#6 Task Period (ms) - configured scan interval in PLC</summary>
    public double? TaskPeriodMs { get; set; }
    /// <summary>#6 Scan Load % = (AvgScanTime/TaskPeriod)*100. >70% = danger zone</summary>
    public double? ScanLoadPercent => (AvgScanTimeMs.HasValue && TaskPeriodMs.HasValue && TaskPeriodMs > 0)
        ? Math.Round((AvgScanTimeMs.Value / TaskPeriodMs.Value) * 100.0, 1)
        : null;
    
    // ─────────────────────────────────────────────────────────────────────
    // #7: Task Overrun - Task:MainTask.OverrunCount → delta > 0 = Missed real-time
    // ─────────────────────────────────────────────────────────────────────
    /// <summary>#7 Task Overrun Count - delta > 0 means missed real-time deadline</summary>
    public int? TaskOverrunCount { get; set; }
    
    // ─────────────────────────────────────────────────────────────────────
    // #8: Communication Latency (ms) - t_response - t_request → >500ms = warning
    // ─────────────────────────────────────────────────────────────────────
    /// <summary>#8 Communication Latency (ms) - Gateway measured. >500ms = warning</summary>
    public double CommunicationLatencyMs { get; set; }
    
    // ─────────────────────────────────────────────────────────────────────
    // #9: Comm Timeout Rate - timeouts / total_reads → >1% = unstable
    // ─────────────────────────────────────────────────────────────────────
    /// <summary>#9 Timeout count (failed reads due to timeout)</summary>
    public long TimeoutCount { get; set; }
    /// <summary>#9 Comm Timeout Rate % = (timeouts/total_reads)*100. >1% = unstable</summary>
    public double CommTimeoutRatePercent => TotalPolls > 0 
        ? Math.Round((double)TimeoutCount / TotalPolls * 100.0, 2) 
        : 0;
    
    // ─────────────────────────────────────────────────────────────────────
    // #10: Reconnect Rate - reconnects / minute → Network issue indicator
    // ─────────────────────────────────────────────────────────────────────
    /// <summary>#10 Reconnection Count since startup</summary>
    public int ReconnectionCount { get; set; }
    /// <summary>#10 Uptime in minutes (for rate calculation)</summary>
    public double UptimeMinutes { get; set; }
    /// <summary>#10 Reconnect Rate per minute. High = network instability</summary>
    public double ReconnectRatePerMinute => UptimeMinutes > 0 
        ? Math.Round(ReconnectionCount / UptimeMinutes, 2) 
        : 0;
    
    // ─────────────────────────────────────────────────────────────────────
    // #11: Open CIP Connections - CIP CM Object (0x06) → Near limit = risk
    // ─────────────────────────────────────────────────────────────────────
    /// <summary>#11 Open CIP Connections (from PLC)</summary>
    public int? OpenConnections { get; set; }
    /// <summary>#11 Max CIP Connections allowed</summary>
    public int? MaxConnections { get; set; }
    /// <summary>#11 Connection usage % (computed)</summary>
    public double? ConnectionUsagePercent => (OpenConnections.HasValue && MaxConnections.HasValue && MaxConnections > 0)
        ? Math.Round((double)OpenConnections.Value / MaxConnections.Value * 100.0, 1)
        : null;
    
    // ─────────────────────────────────────────────────────────────────────
    // #12: Module Fault Count - GSV(Module, Status) → fault != 0 = I/O issue
    // ─────────────────────────────────────────────────────────────────────
    /// <summary>#12 Module Fault Count - I/O modules with faults</summary>
    public int? ModuleFaultCount { get; set; }
    
    // ─────────────────────────────────────────────────────────────────────
    // #13: I/O Task Faulted - IOTaskFaulted (BOOL) → true = Fieldbus issue
    // ─────────────────────────────────────────────────────────────────────
    /// <summary>#13 I/O Task Faulted - Fieldbus/IO issue</summary>
    public bool? IOTaskFaulted { get; set; }
    
    // ─────────────────────────────────────────────────────────────────────
    // #14: Power Supply Status - GSV(Module, PowerSupply) → != OK = Electrical issue
    // ─────────────────────────────────────────────────────────────────────
    /// <summary>#14 Power Supply Status: 1=OK, 0=Fault</summary>
    public int? PowerSupplyStatus { get; set; }
    /// <summary>#14 Power Supply OK (computed)</summary>
    public bool PowerSupplyOk => PowerSupplyStatus == 1;
    
    // ─────────────────────────────────────────────────────────────────────
    // #15: Temperature (°C) - GSV(Chassis, Temp) → Near max = risk
    // ─────────────────────────────────────────────────────────────────────
    /// <summary>#15 CPU/Chassis Temperature (°C) if available</summary>
    public double? TemperatureCelsius { get; set; }
    
    // ─────────────────────────────────────────────────────────────────────
    // #16: Effective Poll Rate % - (executed_reads / scheduled_reads) × 100
    // ─────────────────────────────────────────────────────────────────────
    /// <summary>#16 Scheduled poll count (expected based on interval)</summary>
    public long ScheduledPolls { get; set; }
    /// <summary>#16 Effective Poll Rate % = (SuccessfulPolls/ScheduledPolls)*100. Design KPI</summary>
    public double EffectivePollRatePercent => ScheduledPolls > 0 
        ? Math.Round((double)SuccessfulPolls / ScheduledPolls * 100.0, 1) 
        : 100.0;
    
    // ─────────────────────────────────────────────────────────────────────
    // #17: Failed Polls - Driver stats → > 0 = PLC or network issue
    // ─────────────────────────────────────────────────────────────────────
    /// <summary>#17 Failed Poll Count - PLC or network issue indicator</summary>
    public long FailedPollCount { get; set; }
    
    // ─────────────────────────────────────────────────────────────────────
    // #18: Health Score % - Weighted average of key metrics (Dashboard KPI)
    // ─────────────────────────────────────────────────────────────────────
    /// <summary>#18 Overall Health Score (0-100%). Weighted average for dashboard</summary>
    public double HealthScorePercent { get; set; }
    
    // ═══════════════════════════════════════════════════════════════════
    // COMPUTED STATUS FLAGS
    // ═══════════════════════════════════════════════════════════════════
    /// <summary>True if any fault condition exists (Major, Minor, IO, Module)</summary>
    public bool HasFaults => (MajorFaultActive == true) || HasMinorFault || 
                             (IOTaskFaulted == true) || (ModuleFaultCount > 0);
    
    /// <summary>True if PLC is in healthy RUN mode with no faults</summary>
    public bool IsHealthy => (PlcModeCode == 1) && !HasFaults && IsConnected;
    
    /// <summary>True if scan load > 70% (danger zone)</summary>
    public bool IsOverloaded => ScanLoadPercent.HasValue && ScanLoadPercent > 70;
    
    /// <summary>True if communication latency > 500ms</summary>
    public bool HasHighLatency => CommunicationLatencyMs > 500;
    
    /// <summary>True if timeout rate > 1%</summary>
    public bool HasCommProblems => CommTimeoutRatePercent > 1;
}

/// <summary>
/// Health metrics for all PLCs (MQTT topic: plc/health/all)
/// </summary>
public class AllPlcHealthMetrics
{
    public DateTime Timestamp { get; set; }
    public int PlcCount { get; set; }
    public int ConnectedCount { get; set; }
    public int DisconnectedCount { get; set; }
    public int FaultedCount { get; set; }
    public List<PlcHealthMetrics> Plcs { get; set; } = new();
}

