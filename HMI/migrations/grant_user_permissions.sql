-- Grant admin access to user 2 to bypass RBAC filtering
-- This will allow user to see all tags in the asset hierarchy

UPDATE historian_meta.users
SET is_admin = true
WHERE id = 2;

-- Verify the update
SELECT id, username, is_admin 
FROM historian_meta.users 
WHERE id = 2;
