-- Update Morning Shift (A) to be 5 AM to 1 PM (05:00 - 13:00)
UPDATE historian_meta.shifts
SET start_time = '05:00:00',
    end_time = '13:00:00'
WHERE shift_code = 'A' AND shift_name LIKE '%Morning%';

-- Verify the update
SELECT id, shift_code, shift_name, start_time, end_time, is_active
FROM historian_meta.shifts
ORDER BY start_time;
