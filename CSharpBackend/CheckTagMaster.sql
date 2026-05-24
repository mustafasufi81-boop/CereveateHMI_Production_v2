-- Check exact column names in tag_master table
SELECT column_name, data_type, is_nullable
FROM information_schema.columns 
WHERE table_schema = 'historian_meta' 
  AND table_name = 'tag_master'
ORDER BY ordinal_position;

-- Show current data in tag_master
SELECT * FROM historian_meta.tag_master;
