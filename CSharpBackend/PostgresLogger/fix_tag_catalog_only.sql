-- FIX tag_catalog table - Add only the 3 missing columns
-- This is the ONLY schema fix needed based on actual database state

ALTER TABLE tag_catalog 
ADD COLUMN IF NOT EXISTS record_count BIGINT DEFAULT 0;

ALTER TABLE tag_catalog 
ADD COLUMN IF NOT EXISTS is_mapped BOOLEAN DEFAULT FALSE;

ALTER TABLE tag_catalog 
ADD COLUMN IF NOT EXISTS last_updated TIMESTAMPTZ DEFAULT NOW();

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_tag_catalog_is_mapped ON tag_catalog(is_mapped);
CREATE INDEX IF NOT EXISTS idx_tag_catalog_last_updated ON tag_catalog(last_updated DESC);
CREATE INDEX IF NOT EXISTS idx_tag_catalog_record_count ON tag_catalog(record_count DESC);

-- Verify the fix
SELECT column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'tag_catalog' 
ORDER BY ordinal_position;
