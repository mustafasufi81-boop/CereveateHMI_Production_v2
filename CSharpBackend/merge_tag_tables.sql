-- Merge tag_metadata into tag_master
-- Add missing columns from tag_metadata to tag_master

ALTER TABLE historian_meta.tag_master 
ADD COLUMN IF NOT EXISTS min_value DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS max_value DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS deadband_enabled BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS deadband_value DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS alarm_enabled BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS alarm_hh_limit DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS alarm_h_limit DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS alarm_l_limit DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS alarm_ll_limit DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS alarm_hh_priority INTEGER DEFAULT 1,
ADD COLUMN IF NOT EXISTS alarm_h_priority INTEGER DEFAULT 2,
ADD COLUMN IF NOT EXISTS alarm_l_priority INTEGER DEFAULT 2,
ADD COLUMN IF NOT EXISTS alarm_ll_priority INTEGER DEFAULT 1,
ADD COLUMN IF NOT EXISTS tag_category TEXT,
ADD COLUMN IF NOT EXISTS process_unit TEXT,
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now();

-- Copy data from tag_metadata if any exists
UPDATE historian_meta.tag_master tm
SET 
    min_value = tmd.min_value,
    max_value = tmd.max_value,
    deadband_enabled = tmd.deadband_enabled,
    deadband_value = tmd.deadband_value,
    alarm_enabled = tmd.alarm_enabled,
    alarm_hh_limit = tmd.alarm_hh_limit,
    alarm_h_limit = tmd.alarm_h_limit,
    alarm_l_limit = tmd.alarm_l_limit,
    alarm_ll_limit = tmd.alarm_ll_limit,
    alarm_hh_priority = tmd.alarm_hh_priority,
    alarm_h_priority = tmd.alarm_h_priority,
    alarm_l_priority = tmd.alarm_l_priority,
    alarm_ll_priority = tmd.alarm_ll_priority,
    tag_category = tmd.tag_category,
    process_unit = tmd.process_unit,
    updated_at = tmd.updated_at
FROM historian_meta.tag_metadata tmd
WHERE tm.tag_id = tmd.tag_id;

-- Drop tag_metadata table (no longer needed)
DROP TABLE IF EXISTS historian_meta.tag_metadata CASCADE;
