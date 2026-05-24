-- ============================================================================
-- Fix sensor_data table columns WITHOUT dropping data
-- This adds missing columns and renames existing ones
-- ============================================================================

-- First, check what columns we have now
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'sensor_data' 
ORDER BY ordinal_position;

-- Add missing columns if they don't exist
ALTER TABLE sensor_data ADD COLUMN IF NOT EXISTS tag_code TEXT;
ALTER TABLE sensor_data ADD COLUMN IF NOT EXISTS ingest_timestamp TIMESTAMPTZ DEFAULT NOW();

-- If you have tag_name column, you can copy it to tag_code
-- UPDATE sensor_data SET tag_code = tag_name WHERE tag_code IS NULL;

-- Verify the structure
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns 
WHERE table_name = 'sensor_data' 
ORDER BY ordinal_position;

-- ============================================================================
-- NOTE: If columns are too different, we need to know what exists now
-- Run the SELECT queries above first and tell me what columns you see
-- ============================================================================
