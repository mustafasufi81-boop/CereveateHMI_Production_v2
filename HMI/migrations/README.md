# Database Migration Guide

This directory contains database migration scripts for the Authentication and RBAC (Role-Based Access Control) system.

## Overview

The migration system creates and manages the following database tables:

### Core Tables

1. **`users`** - User accounts with authentication credentials
   - Username and password hash
   - MFA (Multi-Factor Authentication) settings
   - Security questions for password recovery
   - Backup key for account recovery
   - Account lockout and security tracking
   - User status (pending/approved/revoked)
   - Role assignment

2. **`roles`** - User roles for access control
   - Role name and description
   - Admin flag for full system access
   - Timestamps for tracking

3. **`role_tag_permissions`** - Plant/Area level tag access
   - Controls which plant/area combinations a role can access
   - View and write permissions

4. **`role_specific_tag_permissions`** - Individual tag access
   - Granular control for specific tags
   - View and write permissions

5. **`role_alarm_permissions`** - Alarm category access
   - Controls alarm visibility and actions
   - View, acknowledge, and silence permissions

6. **`system_alerts`** - System-generated alerts
   - Tracks security events (lockouts, password resets, etc.)
   - User-associated alerts with read status

## Migration Files

- **`001_init_auth_rbac.sql`** - Initial migration that creates all tables, indexes, constraints, and default roles

## Running Migrations

### Prerequisites

- Python 3.x installed
- PostgreSQL database running
- Database configuration in `config.json`

### Using the Migration Runner

```bash
# Run all pending migrations
python run_migrations.py

# Specify custom config file
python run_migrations.py --config /path/to/config.json

# Specify custom migrations directory
python run_migrations.py --migrations-dir /path/to/migrations
```

### Manual Migration

If you prefer to run migrations manually:

```bash
# Connect to PostgreSQL
psql -h localhost -U your_user -d your_database

# Run the migration file
\i migrations/001_init_auth_rbac.sql
```

## Creating an Admin User

After running the migrations, you'll need to create an initial admin user to access the system.

### Using the Admin User Script

```bash
# Interactive mode (prompts for username and password)
python create_admin_user.py

# With command-line arguments
python create_admin_user.py --username admin --password YourSecurePassword123

# Specify custom config file
python create_admin_user.py --config /path/to/config.json
```

The script will:
- ✅ Create a new user with hashed password
- ✅ Generate a 6-digit backup recovery key
- ✅ Automatically assign the Admin role
- ✅ Approve the user for immediate access
- ✅ Display the backup key (save this securely!)

**Important:** The backup key is only shown once during creation. Store it securely for account recovery.

### Security Recommendations

After creating the admin user:
1. **Enable MFA** - Set up multi-factor authentication on first login
2. **Change Password** - If you used a temporary password, change it immediately
3. **Save Backup Key** - Store the 6-digit backup key in a secure location
4. **Create Additional Users** - Don't share the admin account; create separate users with appropriate roles

## Migration Tracking

The migration runner automatically creates a `migrations` table to track which migrations have been applied:

```sql
SELECT * FROM historian_meta.migrations ORDER BY applied_at DESC;
```

This prevents re-running migrations that have already been applied.

## Default Roles

The migration creates three default roles:

1. **Admin** - Full system administrator with all permissions
2. **Operator** - Standard operator with limited permissions  
3. **Viewer** - Read-only access to system data

## Database Schema

All tables are created in the `historian_meta` schema.

### Key Features

- **Foreign Key Constraints**: Ensures referential integrity
- **Unique Constraints**: Prevents duplicate role-permission combinations
- **Indexes**: Optimizes query performance for common lookups
- **Triggers**: Automatically updates `updated_at` timestamps
- **Cascading Deletes**: Removes related permissions when roles are deleted

## Security Considerations

- Passwords are stored as bcrypt hashes (handled by application layer)
- Security question answers are hashed (handled by application layer)
- Backup keys are hashed with expiration dates
- Account lockout after failed login attempts
- MFA support with TOTP secrets

## Troubleshooting

### Migration Fails

1. Check database connection in `config.json`
2. Ensure PostgreSQL is running
3. Verify database user has CREATE TABLE permissions
4. Check migration logs for specific errors

### Re-running Failed Migrations

The migration runner tracks success/failure. To re-run a failed migration:

```sql
-- Check migration status
SELECT * FROM historian_meta.migrations WHERE success = FALSE;

-- Remove failed migration record to retry
DELETE FROM historian_meta.migrations WHERE filename = 'migration_name.sql';
```

Then run the migration runner again.

## Adding New Migrations

1. Create a new `.sql` file in the `migrations/` directory
2. Use a numbered prefix (e.g., `002_add_feature.sql`)
3. Include `CREATE TABLE IF NOT EXISTS` for safety
4. Add appropriate indexes and constraints
5. Test the migration on a development database first
6. Run the migration runner to apply

## Related Files

- **`HMI/services/auth_service.py`** - Authentication service implementation
- **`HMI/services/rbac_service.py`** - RBAC service implementation
- **`HMI/config.json`** - Database configuration

## Support

For issues or questions about the migration system, refer to the main project documentation or contact the development team.
