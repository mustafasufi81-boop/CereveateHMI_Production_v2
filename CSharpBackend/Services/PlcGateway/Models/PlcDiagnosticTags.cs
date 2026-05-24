namespace PlcGateway.Models;

/// <summary>
/// PLC Diagnostic Tag Definitions for Health Monitoring
/// 
/// These are ACTUAL PLC REGISTER ADDRESSES - not calculated values!
/// The gateway reads these directly from the PLC to get true health status.
/// 
/// ROCKWELL/ALLEN-BRADLEY (ControlLogix/CompactLogix):
/// - Uses CIP protocol and GSV (Get System Value) instructions
/// - Task objects expose scan time, overrun counts
/// - Controller object exposes mode, faults
/// 
/// IMPORTANT: These tags must be configured in the PLC program!
/// Some values require GSV instructions to copy system data to user tags.
/// </summary>
public static class PlcDiagnosticTags
{
    // ═══════════════════════════════════════════════════════════════════
    // ROCKWELL DIAGNOSTIC TAG ADDRESSES
    // ═══════════════════════════════════════════════════════════════════
    
    /// <summary>
    /// Standard Rockwell diagnostic tag addresses.
    /// These should be created in the PLC program using GSV instructions.
    /// 
    /// Example PLC ladder logic:
    /// GSV(Task, MainTask, AvgScanTime, Diag_AvgScanTime);
    /// GSV(Task, MainTask, MaxScanTime, Diag_MaxScanTime);
    /// GSV(Controller, , Status, Diag_ControllerStatus);
    /// </summary>
    public static class Rockwell
    {
        // ─────────────────────────────────────────────────────────────────
        // PLC Mode & Status (Priority 1-3)
        // ─────────────────────────────────────────────────────────────────
        
        /// <summary>
        /// Controller Status - GSV(Controller, , Status, tag)
        /// Bits: RUN=1, PROGRAM=2, FAULT=4
        /// </summary>
        public const string ControllerStatus = "Diag_ControllerStatus";
        
        /// <summary>
        /// Major Fault Active - BOOL
        /// true = PLC has major fault
        /// </summary>
        public const string MajorFault = "Diag_MajorFault";
        
        /// <summary>
        /// Minor Fault Bits - INT
        /// Non-zero = warning conditions
        /// </summary>
        public const string MinorFaultBits = "Diag_MinorFaultBits";
        
        /// <summary>
        /// Controller Mode - Derived from status
        /// 0=Unknown, 1=RUN, 2=PROGRAM, 4=FAULT
        /// </summary>
        public const string ControllerMode = "Diag_ControllerMode";
        
        // ─────────────────────────────────────────────────────────────────
        // Task Scan Times (Priority 4-7)
        // ─────────────────────────────────────────────────────────────────
        
        /// <summary>
        /// Average Scan Time (microseconds) - GSV(Task, MainTask, AvgScanTime, tag)
        /// Convert to ms: value / 1000
        /// Rising value = CPU stress
        /// </summary>
        public const string AvgScanTime = "Diag_AvgScanTime";
        
        /// <summary>
        /// Maximum Scan Time (microseconds) - GSV(Task, MainTask, MaxScanTime, tag)
        /// Convert to ms: value / 1000
        /// Spikes indicate overload
        /// </summary>
        public const string MaxScanTime = "Diag_MaxScanTime";
        
        /// <summary>
        /// Last Scan Time (microseconds) - GSV(Task, MainTask, LastScanTime, tag)
        /// Most recent scan duration
        /// </summary>
        public const string LastScanTime = "Diag_LastScanTime";
        
        /// <summary>
        /// Task Period (microseconds) - GSV(Task, MainTask, Rate, tag)
        /// Configured scan rate for the task
        /// </summary>
        public const string TaskPeriod = "Diag_TaskPeriod";
        
        /// <summary>
        /// Task Overrun Count - GSV(Task, MainTask, OverrunCount, tag)
        /// Increments when scan exceeds period
        /// delta > 0 = missed real-time
        /// </summary>
        public const string OverrunCount = "Diag_OverrunCount";
        
        /// <summary>
        /// Watchdog Time (microseconds) - GSV(Task, MainTask, Watchdog, tag)
        /// Task watchdog timer setting
        /// </summary>
        public const string WatchdogTime = "Diag_WatchdogTime";
        
        // ─────────────────────────────────────────────────────────────────
        // I/O & Module Status (Priority 12-14)
        // ─────────────────────────────────────────────────────────────────
        
        /// <summary>
        /// I/O Task Faulted - BOOL
        /// true = fieldbus communication issue
        /// </summary>
        public const string IOTaskFaulted = "Diag_IOTaskFaulted";
        
        /// <summary>
        /// Module Fault Count - INT
        /// Number of I/O modules with faults
        /// </summary>
        public const string ModuleFaultCount = "Diag_ModuleFaultCount";
        
        /// <summary>
        /// Power Supply Status - INT
        /// 0 = OK, non-zero = issue
        /// </summary>
        public const string PowerSupplyStatus = "Diag_PowerSupplyStatus";
        
        // ─────────────────────────────────────────────────────────────────
        // System Resources (Priority 10-11, 15)
        // ─────────────────────────────────────────────────────────────────
        
        /// <summary>
        /// Free Memory (bytes) - GSV(Program, MainProgram, MajorFaultRecord, tag)
        /// Available program memory
        /// </summary>
        public const string FreeMemory = "Diag_FreeMemory";
        
        /// <summary>
        /// Chassis Temperature (°C) - If available
        /// Hardware temperature
        /// </summary>
        public const string Temperature = "Diag_Temperature";
        
        /// <summary>
        /// Open CIP Connections - Number of active connections
        /// Near limit = risk
        /// </summary>
        public const string OpenConnections = "Diag_OpenConnections";
        
        /// <summary>
        /// Max CIP Connections - Connection limit
        /// </summary>
        public const string MaxConnections = "Diag_MaxConnections";
    }
    
    /// <summary>
    /// Get all diagnostic tag addresses as a list
    /// </summary>
    public static List<DiagnosticTagDefinition> GetRockwellDiagnosticTags()
    {
        return new List<DiagnosticTagDefinition>
        {
            // PLC Mode & Faults
            new(Rockwell.ControllerStatus, "Controller Status", "DINT", "GSV(Controller,,Status)", true),
            new(Rockwell.ControllerMode, "Controller Mode", "INT", "RUN=1, PROGRAM=2, FAULT=4", true),
            new(Rockwell.MajorFault, "Major Fault", "BOOL", "true = fault active", true),
            new(Rockwell.MinorFaultBits, "Minor Fault Bits", "INT", "bit flags", false),
            
            // Scan Times (values in microseconds from GSV)
            new(Rockwell.AvgScanTime, "Avg Scan Time", "DINT", "microseconds", true),
            new(Rockwell.MaxScanTime, "Max Scan Time", "DINT", "microseconds", true),
            new(Rockwell.LastScanTime, "Last Scan Time", "DINT", "microseconds", false),
            new(Rockwell.TaskPeriod, "Task Period", "DINT", "microseconds", true),
            new(Rockwell.OverrunCount, "Overrun Count", "DINT", "counter", true),
            new(Rockwell.WatchdogTime, "Watchdog Time", "DINT", "microseconds", false),
            
            // I/O Status
            new(Rockwell.IOTaskFaulted, "I/O Task Faulted", "BOOL", "fieldbus issue", true),
            new(Rockwell.ModuleFaultCount, "Module Fault Count", "INT", "count", true),
            new(Rockwell.PowerSupplyStatus, "Power Supply Status", "INT", "0=OK", false),
            
            // Resources
            new(Rockwell.FreeMemory, "Free Memory", "DINT", "bytes", false),
            new(Rockwell.Temperature, "Temperature", "REAL", "°C", false),
            new(Rockwell.OpenConnections, "Open Connections", "INT", "count", false),
            new(Rockwell.MaxConnections, "Max Connections", "INT", "limit", false)
        };
    }
}

/// <summary>
/// Definition of a diagnostic tag
/// </summary>
public class DiagnosticTagDefinition
{
    public string Address { get; }
    public string Description { get; }
    public string DataType { get; }
    public string Source { get; }
    public bool IsCritical { get; }
    
    public DiagnosticTagDefinition(string address, string description, string dataType, string source, bool isCritical)
    {
        Address = address;
        Description = description;
        DataType = dataType;
        Source = source;
        IsCritical = isCritical;
    }
}
