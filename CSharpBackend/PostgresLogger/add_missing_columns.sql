-- ============================================================================
-- Add missing columns to existing sensor_data table (NO DROP!)
-- ============================================================================

-- Add columns only if they don't exist
ALTER TABLE sensor_data ADD COLUMN IF NOT EXISTS tag_code TEXT;
ALTER TABLE sensor_data ADD COLUMN IF NOT EXISTS ingest_timestamp TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE sensor_data ADD COLUMN IF NOT EXISTS plant TEXT;
ALTER TABLE sensor_data ADD COLUMN IF NOT EXISTS asset TEXT;
ALTER TABLE sensor_data ADD COLUMN IF NOT EXISTS subsystem TEXT;
ALTER TABLE sensor_data ADD COLUMN IF NOT EXISTS unit TEXT;
ALTER TABLE sensor_data ADD COLUMN IF NOT EXISTS value NUMERIC;
ALTER TABLE sensor_data ADD COLUMN IF NOT EXISTS quality TEXT DEFAULT 'Good';
ALTER TABLE sensor_data ADD COLUMN IF NOT EXISTS shift TEXT;
ALTER TABLE sensor_data ADD COLUMN IF NOT EXISTS batch_id TEXT;

-- Done! Now run the importer
SELECT 'Columns added successfully. Run: python services/background_importer_v2.py' as next_step;
