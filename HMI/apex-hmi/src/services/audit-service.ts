import api from './api';

export interface AuditLogEntry {
  user_id: number;
  username: string;
  action_type: string;
  action_category: string;
  resource_type?: string;
  resource_id?: string;
  old_value?: string;
  new_value?: string;
  status: 'success' | 'failure';
  failure_reason?: string;
  ip_address?: string;
  session_id?: number;
  user_agent?: string;
  additional_context?: Record<string, any>;
}

class AuditService {
  /**
   * Log an alarm acknowledgment
   */
  async logAlarmAcknowledgment(
    userId: number,
    username: string,
    alarmId: string,
    tagId: string,
    alarmMessage: string,
    priority: number,
    sessionId?: number
  ) {
    try {
      await api.post('/audit/log', {
        user_id: userId,
        username,
        action_type: 'ALARM_ACKNOWLEDGMENT',
        action_category: 'alarm',
        resource_type: 'alarm',
        resource_id: alarmId,
        status: 'success',
        session_id: sessionId,
        additional_context: {
          tag_id: tagId,
          alarm_message: alarmMessage,
          priority
        }
      });
    } catch (error) {
      console.error('Failed to log alarm acknowledgment:', error);
    }
  }

  /**
   * Log a setpoint change
   */
  async logSetpointChange(
    userId: number,
    username: string,
    tagId: string,
    tagName: string,
    oldValue: number,
    newValue: number,
    unit: string,
    sessionId?: number
  ) {
    try {
      await api.post('/audit/log', {
        user_id: userId,
        username,
        action_type: 'SETPOINT_CHANGE',
        action_category: 'control',
        resource_type: 'tag',
        resource_id: tagId,
        old_value: oldValue.toString(),
        new_value: newValue.toString(),
        status: 'success',
        session_id: sessionId,
        additional_context: {
          tag_name: tagName,
          unit
        }
      });
    } catch (error) {
      console.error('Failed to log setpoint change:', error);
    }
  }

  /**
   * Log equipment operation (start/stop)
   */
  async logEquipmentOperation(
    userId: number,
    username: string,
    equipmentId: string,
    equipmentName: string,
    operation: 'START' | 'STOP' | 'RESTART' | 'EMERGENCY_STOP',
    sessionId?: number
  ) {
    try {
      await api.post('/audit/log', {
        user_id: userId,
        username,
        action_type: 'EQUIPMENT_OPERATION',
        action_category: 'control',
        resource_type: 'equipment',
        resource_id: equipmentId,
        new_value: operation,
        status: 'success',
        session_id: sessionId,
        additional_context: {
          equipment_name: equipmentName,
          operation
        }
      });
    } catch (error) {
      console.error('Failed to log equipment operation:', error);
    }
  }

  /**
   * Log mode change (manual/auto)
   */
  async logModeChange(
    userId: number,
    username: string,
    equipmentId: string,
    equipmentName: string,
    oldMode: string,
    newMode: string,
    sessionId?: number
  ) {
    try {
      await api.post('/audit/log', {
        user_id: userId,
        username,
        action_type: 'MODE_CHANGE',
        action_category: 'control',
        resource_type: 'equipment',
        resource_id: equipmentId,
        old_value: oldMode,
        new_value: newMode,
        status: 'success',
        session_id: sessionId,
        additional_context: {
          equipment_name: equipmentName
        }
      });
    } catch (error) {
      console.error('Failed to log mode change:', error);
    }
  }

  /**
   * Log page navigation
   */
  async logPageView(
    userId: number,
    username: string,
    pageName: string,
    pageUrl: string,
    sessionId?: number
  ) {
    try {
      await api.post('/audit/log', {
        user_id: userId,
        username,
        action_type: 'PAGE_VIEW',
        action_category: 'navigation',
        resource_type: 'page',
        resource_id: pageName,
        status: 'success',
        session_id: sessionId,
        additional_context: {
          url: pageUrl
        }
      });
    } catch (error) {
      console.error('Failed to log page view:', error);
    }
  }

  /**
   * Log generic action
   */
  async logAction(entry: Partial<AuditLogEntry>) {
    try {
      await api.post('/audit/log', entry);
    } catch (error) {
      console.error('Failed to log action:', error);
    }
  }
}

export const auditService = new AuditService();
