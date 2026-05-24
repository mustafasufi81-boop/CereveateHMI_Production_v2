-- Recreate missing historian_admin tables

-- Create historian_admin schema if doesn't exist
CREATE SCHEMA IF NOT EXISTS historian_admin;

-- Create events log table
CREATE TABLE IF NOT EXISTS historian_admin.events (
    id BIGSERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    message TEXT NOT NULL,
    details JSONB,
    writer_name TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Create writer checkpoints table
CREATE TABLE IF NOT EXISTS historian_admin.writer_checkpoints (
    writer_name TEXT PRIMARY KEY,
    last_processed_at TIMESTAMPTZ NOT NULL,
    last_mapping_version INTEGER NOT NULL,
    info JSONB,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Create spool tracking table
CREATE TABLE IF NOT EXISTS historian_admin.spool_applied (
    id BIGSERIAL PRIMARY KEY,
    file_hash TEXT NOT NULL UNIQUE,
    file_path TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    rows_applied BIGINT NOT NULL,
    shard_index INTEGER
);

-- Grant permissions
GRANT USAGE ON SCHEMA historian_admin TO cereveate;
GRANT ALL ON ALL TABLES IN SCHEMA historian_admin TO cereveate;
GRANT ALL ON ALL SEQUENCES IN SCHEMA historian_admin TO cereveate;

SELECT 'historian_admin tables recreated successfully' as status;
