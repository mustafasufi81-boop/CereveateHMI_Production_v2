-- Add opc_timestamp column to historian_timeseries table
-- This column stores the original OPC server timestamp for audit trail
-- The main 'time' column uses poll timestamp (respects DbLoggingIntervalMs)

ALTER TABLE historian_raw.historian_timeseries
ADD COLUMN IF NOT EXISTS opc_timestamp timestamptz;

-- Add index for efficient queries on OPC timestamp
CREATE INDEX IF NOT EXISTS idx_historian_timeseries_opc_timestamp 
ON historian_raw.historian_timeseries (opc_timestamp);

-- Verify column was added
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'historian_raw'
  AND table_name = 'historian_timeseries'
  AND column_name = 'opc_timestamp';

-- Sample query to verify data (after restart)
-- SELECT tag_id, time, opc_timestamp, value_num 
-- FROM historian_raw.historian_timeseries 
-- ORDER BY time DESC 
-- LIMIT 10;
