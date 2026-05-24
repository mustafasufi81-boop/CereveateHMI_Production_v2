-- Create tag_file_catalog table to track which tags exist in which files
-- This table stores one row per tag-file combination
CREATE TABLE IF NOT EXISTS tag_file_catalog (
    tag_id TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    first_seen TIMESTAMPTZ NOT NULL,
    last_seen TIMESTAMPTZ NOT NULL,
    record_count INTEGER DEFAULT 0,
    file_size_bytes BIGINT DEFAULT 0,
    last_updated TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (tag_id, file_path, file_hash)
);

-- Indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_tag_file_catalog_tag ON tag_file_catalog(tag_id);
CREATE INDEX IF NOT EXISTS idx_tag_file_catalog_file ON tag_file_catalog(file_path);
CREATE INDEX IF NOT EXISTS idx_tag_file_catalog_hash ON tag_file_catalog(file_hash);
CREATE INDEX IF NOT EXISTS idx_tag_file_catalog_updated ON tag_file_catalog(last_updated DESC);

-- View to see all files for each tag
CREATE OR REPLACE VIEW tag_files_view AS
SELECT 
    tag_id,
    COUNT(DISTINCT file_path) as file_count,
    SUM(record_count) as total_records,
    MIN(first_seen) as earliest_data,
    MAX(last_seen) as latest_data,
    STRING_AGG(DISTINCT SUBSTRING(file_path FROM '[^/\\]+$'), ', ' ORDER BY SUBSTRING(file_path FROM '[^/\\]+$')) as files
FROM tag_file_catalog
GROUP BY tag_id;
