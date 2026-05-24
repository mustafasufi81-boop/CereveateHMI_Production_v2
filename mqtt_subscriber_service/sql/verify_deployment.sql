-- ============================================================================
-- Database Verification and Status Check
-- Run this to verify all MQTT subscriber tables are properly created
-- ============================================================================

\echo '======================================================================'
\echo 'MQTT Subscriber Database Verification'
\echo '======================================================================'
\echo ''

-- Set search path
SET search_path = historian_raw, historian_meta, public;

\echo '1. Checking Schemas...'
\echo '----------------------------------------------------------------------'
SELECT schema_name 
FROM information_schema.schemata 
WHERE schema_name IN ('historian_raw', 'historian_meta', 'historian_admin')
ORDER BY schema_name;

\echo ''
\echo '2. Checking Tables in historian_raw...'
\echo '----------------------------------------------------------------------'
SELECT 
    table_name,
    (SELECT COUNT(*) FROM information_schema.columns 
     WHERE table_schema='historian_raw' AND table_name=t.table_name) as columns,
    pg_size_pretty(pg_total_relation_size(quote_ident('historian_raw') || '.' || quote_ident(table_name))) as size
FROM information_schema.tables t
WHERE table_schema = 'historian_raw'
ORDER BY table_name;

\echo ''
\echo '3. Checking Tables in historian_meta...'
\echo '----------------------------------------------------------------------'
SELECT 
    table_name,
    (SELECT COUNT(*) FROM information_schema.columns 
     WHERE table_schema='historian_meta' AND table_name=t.table_name) as columns
FROM information_schema.tables t
WHERE table_schema = 'historian_meta'
ORDER BY table_name;

\echo ''
\echo '4. MQTT Topic Configuration Status...'
\echo '----------------------------------------------------------------------'
SELECT 
    topic_id,
    topic_name,
    qos,
    CASE WHEN is_active THEN 'Active' ELSE 'Inactive' END as status,
    thread_group,
    created_time
FROM historian_raw.mqtt_topic_config
ORDER BY topic_id;

\echo ''
\echo '5. Checking Indexes...'
\echo '----------------------------------------------------------------------'
SELECT 
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname IN ('historian_raw', 'historian_meta')
AND tablename IN ('mqtt_topic_config', 'mqtt_audit_main', 'mqtt_audit_history', 
                  'historian_timeseries', 'historian_events', 'tag_master')
ORDER BY tablename, indexname;

\echo ''
\echo '6. Checking Table Constraints...'
\echo '----------------------------------------------------------------------'
SELECT 
    tc.table_schema,
    tc.table_name,
    tc.constraint_name,
    tc.constraint_type
FROM information_schema.table_constraints tc
WHERE tc.table_schema IN ('historian_raw', 'historian_meta')
AND tc.table_name IN ('mqtt_topic_config', 'mqtt_audit_main', 'mqtt_audit_history', 
                      'historian_timeseries', 'historian_events')
ORDER BY tc.table_name, tc.constraint_type;

\echo ''
\echo '7. Checking TimescaleDB Hypertables...'
\echo '----------------------------------------------------------------------'
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
        RAISE NOTICE 'TimescaleDB extension is installed.';
        PERFORM 1;
    ELSE
        RAISE NOTICE 'TimescaleDB extension is NOT installed.';
    END IF;
END$$;

SELECT 
    hypertable_schema,
    hypertable_name,
    num_chunks,
    compression_enabled
FROM timescaledb_information.hypertables
WHERE hypertable_schema IN ('historian_raw')
ORDER BY hypertable_name;

\echo ''
\echo '8. Table Row Counts...'
\echo '----------------------------------------------------------------------'
SELECT 
    'mqtt_topic_config' as table_name,
    COUNT(*) as row_count
FROM historian_raw.mqtt_topic_config
UNION ALL
SELECT 
    'mqtt_audit_main',
    COUNT(*)
FROM historian_raw.mqtt_audit_main
UNION ALL
SELECT 
    'mqtt_audit_history',
    COUNT(*)
FROM historian_raw.mqtt_audit_history
UNION ALL
SELECT 
    'historian_timeseries',
    COUNT(*)
FROM historian_raw.historian_timeseries
UNION ALL
SELECT 
    'historian_events',
    COUNT(*)
FROM historian_raw.historian_events
UNION ALL
SELECT 
    'tag_master',
    COUNT(*)
FROM historian_meta.tag_master;

\echo ''
\echo '9. User Permissions Check...'
\echo '----------------------------------------------------------------------'
SELECT 
    grantee,
    table_schema,
    table_name,
    privilege_type
FROM information_schema.role_table_grants
WHERE grantee = 'mqtt_subscriber_user'
AND table_schema IN ('historian_raw', 'historian_meta')
ORDER BY table_schema, table_name, privilege_type;

\echo ''
\echo '10. Database Connection Info...'
\echo '----------------------------------------------------------------------'
SELECT 
    current_database() as database_name,
    current_user as current_user,
    version() as postgres_version;

\echo ''
\echo '======================================================================'
\echo 'Verification Complete'
\echo '======================================================================'
\echo ''
