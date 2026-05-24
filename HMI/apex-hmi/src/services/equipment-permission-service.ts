import api from './api';

export type PermissionLevel = 
  | 'NONE'
  | 'VIEW'
  | 'OPERATE'
  | 'CONTROL'
  | 'CONFIGURE'
  | 'MAINTAIN'
  | 'ADMIN'
  | 'FULL_CONTROL';

export interface EquipmentPermission {
  equipment_id: string;
  equipment_name: string;
  permission_level: PermissionLevel;
  granted_by: 'direct' | 'role' | 'inherited';
  source_id?: string;
  source_name?: string;
}

export interface PermissionCheck {
  has_permission: boolean;
  user_permission_level: PermissionLevel;
  required_permission_level: PermissionLevel;
  equipment_id: string;
  equipment_name: string;
  reason?: string;
}

class EquipmentPermissionService {
  /**
   * Permission level hierarchy (lower number = more restrictive)
   */
  private readonly PERMISSION_HIERARCHY: Record<PermissionLevel, number> = {
    'NONE': 0,
    'VIEW': 1,
    'OPERATE': 2,
    'CONTROL': 3,
    'CONFIGURE': 4,
    'MAINTAIN': 5,
    'ADMIN': 6,
    'FULL_CONTROL': 7
  };

  /**
   * Check if user has required permission level for equipment
   */
  async checkPermission(
    equipmentId: string,
    requiredLevel: PermissionLevel
  ): Promise<PermissionCheck> {
    try {
      const response = await api.post<PermissionCheck>('/equipment/permission/check', {
        equipment_id: equipmentId,
        permission_level: requiredLevel
      });
      return response.data;
    } catch (error) {
      console.error('Failed to check equipment permission:', error);
      // Default to no permission on error
      return {
        has_permission: false,
        user_permission_level: 'NONE',
        required_permission_level: requiredLevel,
        equipment_id: equipmentId,
        equipment_name: equipmentId,
        reason: 'Permission check failed'
      };
    }
  }

  /**
   * Get user's permission level for equipment
   */
  async getEquipmentPermission(equipmentId: string): Promise<EquipmentPermission | null> {
    try {
      const response = await api.get<EquipmentPermission>(`/equipment/${equipmentId}/permissions`);
      return response.data;
    } catch (error) {
      console.error('Failed to get equipment permission:', error);
      return null;
    }
  }

  /**
   * Get all equipment permissions for current user
   */
  async getMyPermissions(): Promise<EquipmentPermission[]> {
    try {
      const response = await api.get<EquipmentPermission[]>('/equipment/my-permissions');
      return response.data;
    } catch (error) {
      console.error('Failed to get my permissions:', error);
      return [];
    }
  }

  /**
   * Check if user has at least the specified permission level (client-side helper)
   */
  hasPermissionLevel(
    userLevel: PermissionLevel,
    requiredLevel: PermissionLevel
  ): boolean {
    const userRank = this.PERMISSION_HIERARCHY[userLevel] || 0;
    const requiredRank = this.PERMISSION_HIERARCHY[requiredLevel] || 0;
    return userRank >= requiredRank;
  }

  /**
   * Get permission level name and description
   */
  getPermissionInfo(level: PermissionLevel): { name: string; description: string } {
    const info: Record<PermissionLevel, { name: string; description: string }> = {
      'NONE': {
        name: 'No Access',
        description: 'Cannot view or interact with equipment'
      },
      'VIEW': {
        name: 'View Only',
        description: 'Can view equipment status and data'
      },
      'OPERATE': {
        name: 'Operate',
        description: 'Can start, stop, and perform basic operations'
      },
      'CONTROL': {
        name: 'Control',
        description: 'Can adjust setpoints and control parameters'
      },
      'CONFIGURE': {
        name: 'Configure',
        description: 'Can modify configuration and settings'
      },
      'MAINTAIN': {
        name: 'Maintenance',
        description: 'Can perform maintenance operations'
      },
      'ADMIN': {
        name: 'Administrator',
        description: 'Can manage permissions and advanced settings'
      },
      'FULL_CONTROL': {
        name: 'Full Control',
        description: 'Complete access to all operations'
      }
    };
    
    return info[level] || info['NONE'];
  }

  /**
   * Determine what UI elements to show based on permission level
   */
  getUICapabilities(level: PermissionLevel): {
    canView: boolean;
    canOperate: boolean;
    canControl: boolean;
    canConfigure: boolean;
    canMaintain: boolean;
  } {
    const rank = this.PERMISSION_HIERARCHY[level] || 0;
    
    return {
      canView: rank >= this.PERMISSION_HIERARCHY['VIEW'],
      canOperate: rank >= this.PERMISSION_HIERARCHY['OPERATE'],
      canControl: rank >= this.PERMISSION_HIERARCHY['CONTROL'],
      canConfigure: rank >= this.PERMISSION_HIERARCHY['CONFIGURE'],
      canMaintain: rank >= this.PERMISSION_HIERARCHY['MAINTAIN']
    };
  }
}

export const equipmentPermissionService = new EquipmentPermissionService();
