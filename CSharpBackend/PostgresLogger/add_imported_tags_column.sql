-- Add column to track which tags were imported from each file
ALTER TABLE file_imports 
ADD COLUMN IF NOT EXISTS imported_tags TEXT[];

-- Add index for faster queries
CREATE INDEX IF NOT EXISTS idx_file_imports_imported_tags 
ON file_imports USING GIN (imported_tags);

SELECT 'Column added successfully' as status;
