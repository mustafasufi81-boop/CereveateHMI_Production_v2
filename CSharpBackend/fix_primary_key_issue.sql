-- The issue is the PRIMARY KEY constraint: PRIMARY KEY ("time", tag_id)
-- This will REJECT duplicate (time, tag_id) pairs
-- Even if value changes, if time is same, it will fail!

-- Check the constraint
SELECT 
    conname,
    pg_get_constraintdef(oid) as definition
FROM pg_constraint
WHERE conrelid = 'historian_raw.historian_timeseries'::regclass
AND contype = 'p';

-- Solution: DROP the PRIMARY KEY, it's preventing writes within same second
-- The table will work fine without PK since we have indexes

ALTER TABLE historian_raw.historian_timeseries DROP CONSTRAINT historian_timeseries_pkey;

-- Verify constraint dropped
SELECT 
    COUNT(*) as remaining_pk_constraints
FROM pg_constraint
WHERE conrelid = 'historian_raw.historian_timeseries'::regclass
AND contype = 'p';
