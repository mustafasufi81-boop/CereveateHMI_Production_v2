-- Create tag_imports table to track which tags from which files have been imported
CREATE TABLE IF NOT EXISTS tag_imports (
    id SERIAL PRIMARY KEY,
    file_path TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    tag_id TEXT NOT NULL,
    records_imported INTEGER DEFAULT 0,
    import_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(file_path, file_hash, tag_id)
);

CREATE INDEX IF NOT EXISTS idx_tag_imports_file_tag 
ON tag_imports(file_path, tag_id);

CREATE INDEX IF NOT EXISTS idx_tag_imports_timestamp 
ON tag_imports(import_timestamp DESC);

SELECT 'tag_imports table created' as status;
