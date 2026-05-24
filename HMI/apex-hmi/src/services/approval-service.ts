import api from './api';

export interface ApprovalRequest {
  id: number;
  operation_code: string;
  equipment_id: string;
  equipment_name: string;
  requested_by_user_id: number;
  requested_by_username: string;
  justification: string;
  status: 'pending' | 'approved' | 'rejected' | 'expired';
  request_time: string;
  approval_time?: string;
  approved_by_user_id?: number;
  approved_by_username?: string;
  rejection_reason?: string;
  expires_at: string;
}

export interface CriticalOperationCheck {
  is_critical: boolean;
  operation_code: string;
  operation_name: string;
  requires_approval: boolean;
  approval_timeout_minutes: number;
}

class ApprovalService {
  /**
   * Check if an operation is critical and requires approval
   */
  async checkCriticalOperation(operationCode: string): Promise<CriticalOperationCheck> {
    try {
      const response = await api.get<CriticalOperationCheck>(
        `/approval/check/${operationCode}`
      );
      return response.data;
    } catch (error) {
      console.error('Failed to check critical operation:', error);
      // Default to non-critical if check fails
      return {
        is_critical: false,
        operation_code: operationCode,
        operation_name: operationCode,
        requires_approval: false,
        approval_timeout_minutes: 5
      };
    }
  }

  /**
   * Request approval for a critical operation
   */
  async requestApproval(
    operationCode: string,
    equipmentId: string,
    equipmentName: string,
    justification: string
  ): Promise<ApprovalRequest> {
    const response = await api.post<ApprovalRequest>('/approval/request', {
      operation_code: operationCode,
      equipment_id: equipmentId,
      equipment_name: equipmentName,
      justification
    });
    return response.data;
  }

  /**
   * Get approval request by ID
   */
  async getApprovalRequest(requestId: number): Promise<ApprovalRequest> {
    const response = await api.get<ApprovalRequest>(`/approval/${requestId}`);
    return response.data;
  }

  /**
   * Get pending approval requests for current user
   */
  async getMyRequests(): Promise<ApprovalRequest[]> {
    const response = await api.get<ApprovalRequest[]>('/approval/my-requests');
    return response.data;
  }

  /**
   * Get all pending approval requests (admin/approver only)
   */
  async getPendingRequests(): Promise<ApprovalRequest[]> {
    const response = await api.get<ApprovalRequest[]>('/approval/pending');
    return response.data;
  }

  /**
   * Approve a request (approver only)
   */
  async approveRequest(requestId: number, comments?: string): Promise<void> {
    await api.post(`/approval/approve/${requestId}`, { comments });
  }

  /**
   * Reject a request (approver only)
   */
  async rejectRequest(requestId: number, reason: string): Promise<void> {
    await api.post(`/approval/reject/${requestId}`, { reason });
  }

  /**
   * Poll for approval status (for use in modals)
   */
  async pollApprovalStatus(
    requestId: number,
    onStatusChange: (status: ApprovalRequest['status']) => void,
    intervalMs: number = 2000
  ): Promise<() => void> {
    const intervalId = setInterval(async () => {
      try {
        const request = await this.getApprovalRequest(requestId);
        onStatusChange(request.status);
        
        // Stop polling if not pending
        if (request.status !== 'pending') {
          clearInterval(intervalId);
        }
      } catch (error) {
        console.error('Failed to poll approval status:', error);
      }
    }, intervalMs);

    // Return cleanup function
    return () => clearInterval(intervalId);
  }
}

export const approvalService = new ApprovalService();
