-- Migration: Add role_specific_tag_permissions table
-- This table allows admins to grant access to specific tags for roles

CREATE TABLE IF NOT EXISTS historian_meta.role_specific_tag_permissions (
    id SERIAL PRIMARY KEY,
    role_id INTEGER NOT NULL REFERENCES historian_meta.roles(id) ON DELETE CASCADE,
    tag_id VARCHAR(100) NOT NULL,
    can_view BOOLEAN DEFAULT TRUE,
    can_write BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(role_id, tag_id)
);

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_role_specific_tag_permissions_role_id 
ON historian_meta.role_specific_tag_permissions(role_id);

CREATE INDEX IF NOT EXISTS idx_role_specific_tag_permissions_tag_id 
ON historian_meta.role_specific_tag_permissions(tag_id);
