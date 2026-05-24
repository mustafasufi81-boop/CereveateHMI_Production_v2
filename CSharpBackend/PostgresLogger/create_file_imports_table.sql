-- Create file_imports table for tracking imported parquet files
-- Run this before starting the background importer

-- Drop table if exists (for clean start)
-- DROP TABLE IF EXISTS file_imports;

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

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_file_imports_timestamp 
ON file_imports(import_timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_file_imports_status 
ON file_imports(status);

CREATE INDEX IF NOT EXISTS idx_file_imports_path 
ON file_imports(file_path);

-- Grant permissions
GRANT ALL PRIVILEGES ON TABLE file_imports TO cereveate;
GRANT USAGE, SELECT ON SEQUENCE file_imports_id_seq TO cereveate;

-- Verification
SELECT 
    COUNT(*) as total_imports,
    status,
    SUM(records_imported) as total_records
FROM file_imports
GROUP BY status;
