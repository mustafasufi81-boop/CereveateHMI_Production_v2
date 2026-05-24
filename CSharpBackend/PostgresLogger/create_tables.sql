-- Create file_imports table
CREATE TABLE IF NOT EXISTS file_imports (
    id SERIAL PRIMARY KEY,
    file_path TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    file_size BIGINT,
    import_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    records_imported INTEGER DEFAULT 0,
    status TEXT DEFAULT 'PENDING',
    error_message TEXT,
    UNIQUE(file_path, file_hash)
);

CREATE INDEX IF NOT EXISTS idx_file_imports_timestamp 
ON file_imports(import_timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_file_imports_status 
ON file_imports(status);

-- Create tag_catalog table
CREATE TABLE IF NOT EXISTS tag_catalog (
    tag_id TEXT PRIMARY KEY,
    first_seen TIMESTAMPTZ NOT NULL,
    last_seen TIMESTAMPTZ NOT NULL,
    last_file TEXT
);

CREATE INDEX IF NOT EXISTS idx_tag_catalog_last_seen 
ON tag_catalog(last_seen DESC);

-- Verify tables created
SELECT 'file_imports' as table_name, COUNT(*) as row_count FROM file_imports
UNION ALL
SELECT 'tag_catalog' as table_name, COUNT(*) as row_count FROM tag_catalog;
