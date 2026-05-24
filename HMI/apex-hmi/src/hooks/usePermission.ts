/**
 * usePermission - RBAC permission hook
 *
 * Usage:
 *   const canOperate = usePermission('hmi', 'canOperate');
 *   const canGenerate = usePermission('reports', 'canGenerate');
 *
 * Returns true when:
 *  - user is admin (always full access)
 *  - the module+action is granted in user.permissions
 * Returns false when user is not authenticated or lacks the permission.
 */
import { useAuth } from '@/context/auth-context';
import type { UserPermissions } from '@/services/auth-service';

type PermissionAction = 'canView' | 'canOperate' | 'canGenerate' | 'canConfigure';

export function usePermission(module: keyof UserPermissions, action: PermissionAction): boolean {
    const { user, isAuthenticated } = useAuth();

    if (!isAuthenticated || !user) return false;

    // Admins always have full access
    if (user.isAdmin) return true;

    const perms = user.permissions;
    if (!perms) return false;

    const mod = perms[module as string];
    if (!mod) return false;

    return mod[action] === true;
}

/** Convenience: returns all 4 actions for a module at once */
export function useModulePermissions(module: keyof UserPermissions) {
    const { user, isAuthenticated } = useAuth();

    const empty = { canView: false, canOperate: false, canGenerate: false, canConfigure: false };
    if (!isAuthenticated || !user) return empty;
    if (user.isAdmin) return { canView: true, canOperate: true, canGenerate: true, canConfigure: true };

    const perms = user.permissions;
    if (!perms) return empty;

    const mod = perms[module as string];
    if (!mod) return empty;

    return {
        canView:      mod.canView      ?? false,
        canOperate:   mod.canOperate   ?? false,
        canGenerate:  mod.canGenerate  ?? false,
        canConfigure: mod.canConfigure ?? false,
    };
}
