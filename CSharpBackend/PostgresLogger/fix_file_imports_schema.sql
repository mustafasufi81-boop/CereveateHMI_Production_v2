-- FIX file_imports table schema to match high_performance_importer requirements
-- This adds missing columns needed for the importer to work

-- Add missing columns (IF NOT EXISTS equivalent)
DO $$ 
BEGIN
    -- Add worker_id column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='file_imports' AND column_name='worker_id') THEN
        ALTER TABLE file_imports ADD COLUMN worker_id TEXT;
    END IF;
    
    -- Add lock_acquired_at column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='file_imports' AND column_name='lock_acquired_at') THEN
        ALTER TABLE file_imports ADD COLUMN lock_acquired_at TIMESTAMPTZ;
    END IF;
    
    -- Add started_at column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='file_imports' AND column_name='started_at') THEN
        ALTER TABLE file_imports ADD COLUMN started_at TIMESTAMPTZ;
    END IF;
    
    -- Add completed_at column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='file_imports' AND column_name='completed_at') THEN
        ALTER TABLE file_imports ADD COLUMN completed_at TIMESTAMPTZ;
    END IF;
    
    -- Add processing_time_ms column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='file_imports' AND column_name='processing_time_ms') THEN
        ALTER TABLE file_imports ADD COLUMN processing_time_ms NUMERIC;
    END IF;
    
    -- Add tags_imported column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='file_imports' AND column_name='tags_imported') THEN
        ALTER TABLE file_imports ADD COLUMN tags_imported INTEGER DEFAULT 0;
    END IF;
    
    -- Add tags_skipped column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='file_imports' AND column_name='tags_skipped') THEN
        ALTER TABLE file_imports ADD COLUMN tags_skipped INTEGER DEFAULT 0;
    END IF;
    
    -- Add file_format column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='file_imports' AND column_name='file_format') THEN
        ALTER TABLE file_imports ADD COLUMN file_format TEXT;
    END IF;
    
    -- Add total_tags_in_file column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='file_imports' AND column_name='total_tags_in_file') THEN
        ALTER TABLE file_imports ADD COLUMN total_tags_in_file INTEGER DEFAULT 0;
    END IF;
    
    -- Add total_rows_in_file column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='file_imports' AND column_name='total_rows_in_file') THEN
        ALTER TABLE file_imports ADD COLUMN total_rows_in_file INTEGER DEFAULT 0;
    END IF;
    
    -- Add enqueued_at column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='file_imports' AND column_name='enqueued_at') THEN
        ALTER TABLE file_imports ADD COLUMN enqueued_at TIMESTAMPTZ DEFAULT NOW();
    END IF;
END $$;

-- Create additional indexes for performance
CREATE INDEX IF NOT EXISTS idx_file_imports_worker ON file_imports(worker_id);
CREATE INDEX IF NOT EXISTS idx_file_imports_started ON file_imports(started_at);
CREATE INDEX IF NOT EXISTS idx_file_imports_completed ON file_imports(completed_at);

-- Show schema
SELECT column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'file_imports' 
ORDER BY ordinal_position;
