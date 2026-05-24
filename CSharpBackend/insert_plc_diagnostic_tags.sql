-- ═══════════════════════════════════════════════════════════════════════════
-- PLC DIAGNOSTIC TAGS FOR ROCKWELL/ALLEN-BRADLEY
-- ═══════════════════════════════════════════════════════════════════════════
-- 
-- These tags read ACTUAL PLC REGISTER VALUES for health monitoring.
-- NOT calculated gateway-side metrics!
--
-- PREREQUISITE: 
-- Create these tags in your PLC program using GSV (Get System Value) instructions:
--
-- Example Ladder Logic:
--   GSV(Task, MainTask, AvgScanTime, Diag_AvgScanTime);
--   GSV(Task, MainTask, MaxScanTime, Diag_MaxScanTime);
--   GSV(Task, MainTask, LastScanTime, Diag_LastScanTime);
--   GSV(Task, MainTask, Rate, Diag_TaskPeriod);
--   GSV(Task, MainTask, OverrunCount, Diag_OverrunCount);
--   GSV(Controller, , Status, Diag_ControllerStatus);
--
-- ═══════════════════════════════════════════════════════════════════════════

-- Get PLC ID (assuming Rockwel_PLC_001 exists)
DO $$
DECLARE
    plc_id_var TEXT := 'Rockwel_PLC_001';
BEGIN

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. PLC MODE & FAULT STATUS (Priority 1-3)
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO historian_meta.tag_master (
    tag_id, tag_name, data_type, deadband_value, db_logging_interval_ms, 
    enabled, created_by, plc_id, plc_protocol
) VALUES
-- Controller Status (RUN=1, PROGRAM=2, FAULT=4)
('Diag_ControllerStatus', 'PLC Controller Status', 'int', 0, 3000, true, 'system', plc_id_var, 'Rockwell'),
-- Controller Mode (derived for display)
('Diag_ControllerMode', 'PLC Controller Mode', 'int', 0, 3000, true, 'system', plc_id_var, 'Rockwell'),
-- Major Fault Active
('Diag_MajorFault', 'PLC Major Fault', 'bool', 0, 3000, true, 'system', plc_id_var, 'Rockwell'),
-- Minor Fault Bits
('Diag_MinorFaultBits', 'PLC Minor Fault Bits', 'int', 0, 3000, true, 'system', plc_id_var, 'Rockwell')

ON CONFLICT (tag_id) DO UPDATE SET
    enabled = true,
    plc_id = plc_id_var,
    plc_protocol = 'Rockwell',
    db_logging_interval_ms = 3000;

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. TASK SCAN TIMES (Priority 4-7) - Values in MICROSECONDS from GSV
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO historian_meta.tag_master (
    tag_id, tag_name, data_type, deadband_value, db_logging_interval_ms, 
    enabled, created_by, plc_id, plc_protocol
) VALUES
-- Average Scan Time (microseconds) - GSV(Task, MainTask, AvgScanTime, tag)
('Diag_AvgScanTime', 'Task Avg Scan Time (us)', 'int', 100, 3000, true, 'system', plc_id_var, 'Rockwell'),
-- Maximum Scan Time (microseconds)
('Diag_MaxScanTime', 'Task Max Scan Time (us)', 'int', 100, 3000, true, 'system', plc_id_var, 'Rockwell'),
-- Last Scan Time (microseconds)
('Diag_LastScanTime', 'Task Last Scan Time (us)', 'int', 100, 3000, true, 'system', plc_id_var, 'Rockwell'),
-- Task Period/Rate (microseconds)
('Diag_TaskPeriod', 'Task Period (us)', 'int', 0, 3000, true, 'system', plc_id_var, 'Rockwell'),
-- Task Overrun Counter
('Diag_OverrunCount', 'Task Overrun Count', 'int', 0, 3000, true, 'system', plc_id_var, 'Rockwell'),
-- Watchdog Time
('Diag_WatchdogTime', 'Task Watchdog Time (us)', 'int', 0, 3000, false, 'system', plc_id_var, 'Rockwell')

ON CONFLICT (tag_id) DO UPDATE SET
    enabled = true,
    plc_id = plc_id_var,
    plc_protocol = 'Rockwell',
    db_logging_interval_ms = 3000;

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. I/O & MODULE STATUS (Priority 12-14)
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO historian_meta.tag_master (
    tag_id, tag_name, data_type, deadband_value, db_logging_interval_ms, 
    enabled, created_by, plc_id, plc_protocol
) VALUES
-- I/O Task Faulted
('Diag_IOTaskFaulted', 'I/O Task Faulted', 'bool', 0, 3000, true, 'system', plc_id_var, 'Rockwell'),
-- Module Fault Count
('Diag_ModuleFaultCount', 'Module Fault Count', 'int', 0, 3000, true, 'system', plc_id_var, 'Rockwell'),
-- Power Supply Status
('Diag_PowerSupplyStatus', 'Power Supply Status', 'int', 0, 3000, true, 'system', plc_id_var, 'Rockwell')

ON CONFLICT (tag_id) DO UPDATE SET
    enabled = true,
    plc_id = plc_id_var,
    plc_protocol = 'Rockwell',
    db_logging_interval_ms = 3000;

-- ─────────────────────────────────────────────────────────────────────────────
-- 4. SYSTEM RESOURCES (Priority 10-11, 15)
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO historian_meta.tag_master (
    tag_id, tag_name, data_type, deadband_value, db_logging_interval_ms, 
    enabled, created_by, plc_id, plc_protocol
) VALUES
-- Free Memory
('Diag_FreeMemory', 'Free Memory (bytes)', 'int', 0, 10000, false, 'system', plc_id_var, 'Rockwell'),
-- Temperature
('Diag_Temperature', 'Chassis Temperature (C)', 'double', 1, 10000, false, 'system', plc_id_var, 'Rockwell'),
-- Open CIP Connections
('Diag_OpenConnections', 'Open CIP Connections', 'int', 0, 10000, false, 'system', plc_id_var, 'Rockwell'),
-- Max CIP Connections
('Diag_MaxConnections', 'Max CIP Connections', 'int', 0, 10000, false, 'system', plc_id_var, 'Rockwell')

ON CONFLICT (tag_id) DO UPDATE SET
    enabled = EXCLUDED.enabled,
    plc_id = plc_id_var,
    plc_protocol = 'Rockwell';

RAISE NOTICE 'Inserted/Updated diagnostic tags for PLC: %', plc_id_var;

END $$;

-- ═══════════════════════════════════════════════════════════════════════════
-- VERIFY DIAGNOSTIC TAGS
-- ═══════════════════════════════════════════════════════════════════════════

SELECT tag_id, tag_name, data_type, enabled, db_logging_interval_ms, plc_id
FROM historian_meta.tag_master
WHERE tag_id LIKE 'Diag_%'
ORDER BY tag_id;

-- ═══════════════════════════════════════════════════════════════════════════
-- HEALTH METRICS FORMULAS (for reference)
-- ═══════════════════════════════════════════════════════════════════════════
/*
| Metric              | Source Tag           | Formula                                    |
|---------------------|----------------------|--------------------------------------------|
| PLC Mode            | Diag_ControllerStatus| RUN=1, PROGRAM=2, FAULT=4                 |
| Major Fault         | Diag_MajorFault      | true = fault                               |
| Avg Scan Time (ms)  | Diag_AvgScanTime     | value / 1000 (GSV returns microseconds)    |
| Max Scan Time (ms)  | Diag_MaxScanTime     | value / 1000                               |
| Scan Load %         | AvgScanTime/TaskPeriod| (Diag_AvgScanTime / Diag_TaskPeriod) × 100|
| Task Overrun        | Diag_OverrunCount    | delta > 0 = missed real-time               |
| I/O Fault           | Diag_IOTaskFaulted   | true = fieldbus issue                      |
| Module Faults       | Diag_ModuleFaultCount| > 0 = I/O module issue                     |
*/
