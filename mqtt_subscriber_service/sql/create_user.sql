-- ============================================================================
-- Create MQTT Subscriber Database User
-- Run this script as superuser (postgres) to create the service user
-- ============================================================================

\echo '======================================================================'
\echo 'Creating MQTT Subscriber Database User'
\echo '======================================================================'
\echo ''

-- Create user with login capability
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'opc_app_user') THEN
        CREATE USER opc_app_user WITH 
            LOGIN
            PASSWORD 'MqttSub$ecure2026!'  -- CHANGE THIS PASSWORD!
            CONNECTION LIMIT 10;
        
        RAISE NOTICE 'User opc_app_user created successfully.';
    ELSE
        RAISE NOTICE 'User opc_app_user already exists.';
    END IF;
END$$;

\echo ''
\echo 'Granting schema permissions...'

-- Grant schema usage
GRANT USAGE ON SCHEMA historian_raw TO opc_app_user;
GRANT USAGE ON SCHEMA historian_meta TO opc_app_user;

\echo 'Schema usage granted.'

\echo ''
\echo 'Granting table permissions...'

-- Grant SELECT on configuration tables (READ-ONLY)
GRANT SELECT ON historian_raw.mqtt_topic_config TO opc_app_user;
GRANT SELECT ON historian_meta.tag_master TO opc_app_user;

-- Grant INSERT/UPDATE on audit tables
GRANT INSERT, UPDATE ON historian_raw.mqtt_audit_main TO opc_app_user;
GRANT INSERT ON historian_raw.mqtt_audit_history TO opc_app_user;

-- Grant INSERT on historian data tables
GRANT INSERT ON historian_raw.historian_timeseries TO opc_app_user;
GRANT INSERT, UPDATE ON historian_raw.historian_events TO opc_app_user;

\echo 'Table permissions granted.'

\echo ''
\echo 'Granting sequence permissions...'

-- Grant sequence usage for SERIAL/BIGSERIAL columns
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA historian_raw TO opc_app_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA historian_meta TO opc_app_user;

\echo 'Sequence permissions granted.'

\echo ''
\echo 'Verifying user permissions...'

-- Verify permissions
SELECT 
    grantee,
    table_schema,
    table_name,
    privilege_type
FROM information_schema.role_table_grants
WHERE grantee = 'opc_app_user'
AND table_schema IN ('historian_raw', 'historian_meta')
ORDER BY table_schema, table_name, privilege_type;

\echo ''
\echo '======================================================================'
\echo 'User Creation Complete'
\echo '======================================================================'
\echo ''
\echo 'IMPORTANT: Update your config/config.yaml with these credentials:'
\echo '  database:'
\echo '    host: localhost'
\echo '    port: 5432'
\echo '    database: Cereveate'
\echo '    user: opc_app_user'
\echo '    password: MqttSub$ecure2026!  # CHANGE THIS!'
\echo ''
\echo 'SECURITY WARNING: Change the default password immediately!'
\echo '======================================================================'
\echo ''
