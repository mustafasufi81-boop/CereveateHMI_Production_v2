BEGIN;
SET timescaledb.max_tuples_decompressed_per_dml_transaction TO 0;

WITH duplicate_rows AS (
    SELECT id
    FROM (
        SELECT id,
               ROW_NUMBER() OVER (PARTITION BY tag_code, "timestamp" ORDER BY id) AS rn
        FROM sensor_data
    ) ranked
    WHERE rn > 1
)
DELETE FROM sensor_data
WHERE id IN (SELECT id FROM duplicate_rows);

CREATE UNIQUE INDEX IF NOT EXISTS sensor_data_timestamp_tag_code_idx
    ON sensor_data ("timestamp", tag_code);

ALTER TABLE tag_imports
    ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'UNKNOWN';

ALTER TABLE tag_imports
    ADD COLUMN IF NOT EXISTS error_message TEXT;

COMMIT;
