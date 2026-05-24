import { useState, useEffect, useCallback } from 'react';
import { 
  equipmentPermissionService, 
  PermissionLevel, 
  EquipmentPermission,
  PermissionCheck
} from '@/services/equipment-permission-service';

/**
 * Hook for checking equipment permissions
 */
export const useEquipmentPermission = (equipmentId?: string) => {
  const [loading, setLoading] = useState(false);
  const [permission, setPermission] = useState<EquipmentPermission | null>(null);
  const [permissionLevel, setPermissionLevel] = useState<PermissionLevel>('NONE');

  /**
   * Load permission for specified equipment
   */
  const loadPermission = useCallback(async (id: string) => {
    setLoading(true);
    try {
      const perm = await equipmentPermissionService.getEquipmentPermission(id);
      setPermission(perm);
      setPermissionLevel(perm?.permission_level || 'NONE');
    } catch (error) {
      console.error('Failed to load equipment permission:', error);
      setPermissionLevel('NONE');
    } finally {
      setLoading(false);
    }
  }, []);

  /**
   * Check if user has required permission level
   */
  const checkPermission = useCallback(async (
    id: string,
    requiredLevel: PermissionLevel
  ): Promise<PermissionCheck> => {
    return await equipmentPermissionService.checkPermission(id, requiredLevel);
  }, []);

  /**
   * Check if user has permission level (client-side)
   */
  const hasPermission = useCallback((requiredLevel: PermissionLevel): boolean => {
    return equipmentPermissionService.hasPermissionLevel(permissionLevel, requiredLevel);
  }, [permissionLevel]);

  /**
   * Get UI capabilities based on current permission
   */
  const capabilities = equipmentPermissionService.getUICapabilities(permissionLevel);

  // Auto-load permission when equipmentId changes
  useEffect(() => {
    if (equipmentId) {
      loadPermission(equipmentId);
    }
  }, [equipmentId, loadPermission]);

  return {
    loading,
    permission,
    permissionLevel,
    capabilities,
    hasPermission,
    checkPermission,
    loadPermission
  };
};

/**
 * Hook for managing permission-based UI visibility
 */
export const usePermissionGate = (
  equipmentId: string,
  requiredLevel: PermissionLevel
) => {
  const [canAccess, setCanAccess] = useState(false);
  const [checking, setChecking] = useState(true);
  const [reason, setReason] = useState<string | null>(null);

  useEffect(() => {
    const checkAccess = async () => {
      setChecking(true);
      try {
        const result = await equipmentPermissionService.checkPermission(
          equipmentId,
          requiredLevel
        );
        setCanAccess(result.has_permission);
        setReason(result.reason || null);
      } catch (error) {
        console.error('Permission check failed:', error);
        setCanAccess(false);
        setReason('Permission check failed');
      } finally {
        setChecking(false);
      }
    };

    checkAccess();
  }, [equipmentId, requiredLevel]);

  return {
    canAccess,
    checking,
    reason
  };
};
