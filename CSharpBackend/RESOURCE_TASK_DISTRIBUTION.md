# Resource Task Distribution & Allocation (3-Month Plan)

This document outlines the task distribution for the team over the next 3 months (Dec-25 to Feb-26). The total effort hours remain consistent with the resource projection.

## 1. Shahnawaz Mustafa (Engineer / Consultant)
**Monthly Effort:** 160 Hours
**Primary Focus:** Database Architecture, Schema Design, and Analytics/ML Foundation.

### Task Allocation
*   **Database Schema Management (40 Hours)**
    *   Review and optimize core database schemas (`add_opc_timestamp_column.sql`, `add_plc_columns.sql`).
    *   Manage `create_historian_schema.sql` regarding partition strategies.
    *   Oversee `fix_primary_key_issue.sql` and `fix_duplicate_key.sql` implementation.
*   **Core System Optimization (60 Hours)**
    *   Implement optimization strategies from `10K_TAGS_OPTIMIZATION_SUMMARY.md`.
    *   Design robust data pipelines for high-volume tag ingestion.
    *   Develop strategies for system generalization and scalability.
*   **Consulting & Review (60 Hours)**
    *   Review team code submissions.
    *   Coordinate with John Agusta on `ARCHITECTURE_PLC_CURRENT_VS_FUTURE.md`.
    *   Documentation updates for API and Config guides.

---

## 2. John Agusta (Senior Engineer / Consultant)
**Monthly Effort:** 120 Hours
**Primary Focus:** System Architecture, Security, and Strategic Planning.

### Task Allocation
*   **System Architecture (50 Hours)**
    *   Finalize `DECOUPLED_MQTT_ARCHITECTURE.md`.
    *   Define the roadmap for `ARCHITECTURE_OPC_CURRENT_VS_FUTURE.md`.
    *   Review `CRITICAL_CONFIG_SOURCE.md`.
*   **Security & Network Configuration (30 Hours)**
    *   Review and approve `ADD_FIREWALL_RULE_OPC.bat` strategies.
    *   Audit `CHECK_NETWORK_CONFIG.bat` results.
*   **Stability & Commercialization (40 Hours)**
    *   Lead the `COMMERCIAL_STABILITY_IMPLEMENTATION.md`.
    *   Oversee `EVENTS_VS_ALARMS_ANALYSIS.md` high-level logic.
    *   Project management and stakeholder reporting.

---

## 3. Md Shakil Ahmad (Engineer)
**Monthly Effort:** 176 Hours
**Primary Focus:** Backend Development, Python Scripting, and Data Integrity.

### Task Allocation
*   **Script Maintenance & Development (70 Hours)**
    *   Maintain and upgrade core scripts: `check_db_schema.py`, `check_system_errors.py`.
    *   Implement logic for `ALARM_TRIP_IMPLEMENTATION_PLAN.md`.
    *   Develop `cleanup_batch.py` and `cleanup_fast.py` based on performance needs.
*   **Data Integrity & Logic (60 Hours)**
    *   Execute and monitor `check_duplicates.py` and `check_mappings.py`.
    *   Implement `APPLICATION_LOGIC_IMPLEMENTATION_GUIDE.md`.
    *   Work on `fix_primary_key_issue.sql` execution.
*   **System Health Monitoring (46 Hours)**
    *   Implement tools described in `HEALTH_MONITORING_SYSTEM.md`.
    *   Analyze logs from `build_errors.txt` and fix underlying code issues.
    *   Daily operational checks.

---

## 4. Saquib Jawed (Engineer)
**Monthly Effort:** 168 Hours
**Primary Focus:** Testing, Validation, Historical Data Analysis, and Reporting.

### Task Allocation
*   **Data Validation & Testing (70 Hours)**
    *   Run and analyze `check_live_data.py`, `check_recent_data.py`, and `check_last_writes.py`.
    *   Validate `5_SECOND_DELAY_FIX_SUMMARY.md` effectiveness.
    *   Perform sampling rate checks using `check_scan_rates.py` and `check_24h_sampling.py`.
*   **Historical Data Analysis (50 Hours)**
    *   Work on `HISTORIAN_DATA_FLOW_ANALYSIS.md` validation.
    *   Execute `check_historical_data.py` and report anomalies.
    *   Verify `ARCHIVE_CONFIGURATION_GUIDE.md` procedures.
*   **Optimization & Reporting (48 Hours)**
    *   Conduct tests for `10K_TAGS_OPTIMIZATION_SUMMARY.md`.
    *   Generate weekly reports on system stability.
    *   Support `HMI_RAW_DATA_SAMPLING_FIX.md` testing cycles.
