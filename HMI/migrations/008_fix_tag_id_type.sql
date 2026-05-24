-- =====================================================
-- Migration: Fix tag_id Type Mismatch
-- Description: Change role_specific_tag_permissions.tag_id from INTEGER to VARCHAR
-- to match tag_master.tag_id type
-- =====================================================

-- Drop existing constraints and indexes
ALTER TABLE historian_meta.role_specific_tag_permissions 
DROP CONSTRAINT IF EXISTS role_specific_tag_permissions_role_id_tag_id_key;

DROP INDEX IF EXISTS historian_meta.idx_role_specific_tag_perms_tag;
DROP INDEX IF EXISTS historian_meta.idx_role_specific_tag_permissions_tag_id;

-- Change column type from INTEGER to VARCHAR(100)
ALTER TABLE historian_meta.role_specific_tag_permissions 
ALTER COLUMN tag_id TYPE VARCHAR(100) USING tag_id::VARCHAR(100);

-- Recreate unique constraint
ALTER TABLE historian_meta.role_specific_tag_permissions
ADD CONSTRAINT role_specific_tag_permissions_role_id_tag_id_key UNIQUE(role_id, tag_id);

-- Recreate index
CREATE INDEX idx_role_specific_tag_permissions_tag_id 
ON historian_meta.role_specific_tag_permissions(tag_id);

-- Verify the change
DO $$
BEGIN
    RAISE NOTICE '✅ Migration complete: tag_id column type changed to VARCHAR(100)';
END $$;
