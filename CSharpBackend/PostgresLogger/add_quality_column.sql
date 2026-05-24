-- Add missing quality column to sensor_data table
ALTER TABLE sensor_data ADD COLUMN IF NOT EXISTS quality TEXT DEFAULT 'Good';
