-- COMPREHENSIVE SCHEMA FIX FOR PostgresLogger
-- Fixes tag_catalog and tag_file_catalog tables

-- ====================================================================================
-- FIX TAG_CATALOG TABLE
-- ====================================================================================
DO $$ 
BEGIN
    -- Add record_count column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='tag_catalog' AND column_name='record_count') THEN
        ALTER TABLE tag_catalog ADD COLUMN record_count BIGINT DEFAULT 0;
    END IF;
    
    -- Add is_mapped column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='tag_catalog' AND column_name='is_mapped') THEN
        ALTER TABLE tag_catalog ADD COLUMN is_mapped BOOLEAN DEFAULT FALSE;
    END IF;
    
    -- Add last_updated column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='tag_catalog' AND column_name='last_updated') THEN
        ALTER TABLE tag_catalog ADD COLUMN last_updated TIMESTAMPTZ DEFAULT NOW();
    END IF;
END $$;

-- ====================================================================================
-- CREATE TAG_FILE_CATALOG TABLE IF NOT EXISTS
-- ====================================================================================
CREATE TABLE IF NOT EXISTS tag_file_catalog (
    id SERIAL PRIMARY KEY,
    file_path TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    tag_id TEXT NOT NULL,
    record_count INTEGER DEFAULT 0,
    tag_count INTEGER DEFAULT 0,
    first_timestamp TIMESTAMPTZ,
    last_timestamp TIMESTAMPTZ,
    last_updated TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(file_path, file_hash, tag_id)
);

CREATE INDEX IF NOT EXISTS idx_tag_file_catalog_tag ON tag_file_catalog(tag_id);
CREATE INDEX IF NOT EXISTS idx_tag_file_catalog_file ON tag_file_catalog(file_path);
CREATE INDEX IF NOT EXISTS idx_tag_file_catalog_updated ON tag_file_catalog(last_updated DESC);

GRANT ALL PRIVILEGES ON TABLE tag_file_catalog TO cereveate;
GRANT USAGE, SELECT ON SEQUENCE tag_file_catalog_id_seq TO cereveate;

-- ====================================================================================
-- VERIFICATION
-- ====================================================================================
\echo '\n=== tag_catalog schema ==='
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'tag_catalog' 
ORDER BY ordinal_position;

\echo '\n=== tag_file_catalog schema ==='
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'tag_file_catalog' 
ORDER BY ordinal_position;

\echo '\n=== file_imports schema ==='
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'file_imports' 
ORDER BY ordinal_position;
