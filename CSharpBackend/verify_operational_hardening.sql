-- Verification script for OPERATIONAL_HARDENING.sql deployment

\echo '=== OPERATIONAL HARDENING VERIFICATION ==='
\echo ''

-- Check schema version
\echo 'Schema Version:'
SELECT get_schema_version();
\echo ''

-- Check alarm columns
\echo 'Alarm Lifecycle Columns:'
SELECT 
    column_name,
    data_type
FROM information_schema.columns 
WHERE table_schema = 'historian_raw' 
  AND table_name = 'historian_events'
  AND column_name IN ('alarm_state', 'alarm_priority', 'acknowledged_by', 'parent_alarm_id')
ORDER BY column_name;
\echo ''

-- Check trip/interlock columns
\echo 'Trip/Interlock Columns in tag_master:'
SELECT 
    column_name,
    data_type
FROM information_schema.columns 
WHERE table_schema = 'historian_meta' 
  AND table_name = 'tag_master'
  AND column_name IN ('trip_category', 'interlock_type', 'equipment_criticality', 'is_trip_initiator')
ORDER BY column_name;
\echo ''

-- Check tables created
\echo 'Tables Created:'
SELECT 
    table_schema || '.' || table_name AS full_table_name
FROM information_schema.tables 
WHERE table_name IN ('trip_event_tracking', 'interlock_state_tracking', 'alarm_suppression_schedule', 'data_quality_limits')
ORDER BY table_schema, table_name;
\echo ''

-- Check views created
\echo 'Views Created:'
SELECT 
    table_schema || '.' || table_name AS full_view_name
FROM information_schema.views 
WHERE table_name IN ('vw_active_alarms', 'vw_system_events', 'vw_data_quality', 'vw_audit_trail', 'vw_trip_causality', 'vw_interlock_violations')
ORDER BY table_name;
\echo ''

-- Check functions created
\echo 'Functions Created:'
SELECT 
    routine_schema || '.' || routine_name AS full_function_name
FROM information_schema.routines 
WHERE routine_name IN ('acknowledge_alarm', 'cleanup_old_events', 'check_retention_health', 'validate_timeseries_sample')
ORDER BY routine_name;
\echo ''

-- Check unique constraint
\echo 'Unique Constraint on historian_timeseries:'
SELECT 
    conname AS constraint_name,
    pg_get_constraintdef(oid) AS constraint_definition
FROM pg_constraint 
WHERE conname = 'uq_timeseries_time_tag';
\echo ''

\echo '=== VERIFICATION COMPLETE ==='
