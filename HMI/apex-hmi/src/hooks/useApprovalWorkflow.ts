import { useState, useCallback } from 'react';
import { 
  approvalService, 
  ApprovalRequest, 
  CriticalOperationCheck 
} from '@/services/approval-service';

/**
 * Hook for managing approval workflow
 */
export const useApprovalWorkflow = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [currentRequest, setCurrentRequest] = useState<ApprovalRequest | null>(null);

  /**
   * Check if an operation requires approval
   */
  const checkIfCritical = useCallback(async (
    operationCode: string
  ): Promise<CriticalOperationCheck> => {
    setLoading(true);
    setError(null);
    try {
      const result = await approvalService.checkCriticalOperation(operationCode);
      return result;
    } catch (err: any) {
      setError(err.message || 'Failed to check operation');
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  /**
   * Request approval for a critical operation
   */
  const requestApproval = useCallback(async (
    operationCode: string,
    equipmentId: string,
    equipmentName: string,
    justification: string
  ): Promise<ApprovalRequest> => {
    setLoading(true);
    setError(null);
    try {
      const request = await approvalService.requestApproval(
        operationCode,
        equipmentId,
        equipmentName,
        justification
      );
      setCurrentRequest(request);
      return request;
    } catch (err: any) {
      setError(err.message || 'Failed to request approval');
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  /**
   * Get approval status
   */
  const getApprovalStatus = useCallback(async (requestId: number): Promise<ApprovalRequest> => {
    try {
      const request = await approvalService.getApprovalRequest(requestId);
      setCurrentRequest(request);
      return request;
    } catch (err: any) {
      setError(err.message || 'Failed to get approval status');
      throw err;
    }
  }, []);

  /**
   * Clear current request
   */
  const clearRequest = useCallback(() => {
    setCurrentRequest(null);
    setError(null);
  }, []);

  return {
    loading,
    error,
    currentRequest,
    checkIfCritical,
    requestApproval,
    getApprovalStatus,
    clearRequest
  };
};

/**
 * Hook for executing critical operations with approval workflow
 */
export const useCriticalOperation = () => {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [pendingOperation, setPendingOperation] = useState<{
    code: string;
    equipmentId: string;
    equipmentName: string;
    callback: () => void | Promise<void>;
  } | null>(null);

  /**
   * Execute an operation, checking if it requires approval first
   */
  const executeWithApprovalCheck = useCallback(async (
    operationCode: string,
    equipmentId: string,
    equipmentName: string,
    callback: () => void | Promise<void>
  ) => {
    // Check if operation is critical
    const check = await approvalService.checkCriticalOperation(operationCode);

    if (check.is_critical && check.requires_approval) {
      // Show approval modal
      setPendingOperation({
        code: operationCode,
        equipmentId,
        equipmentName,
        callback
      });
      setIsModalOpen(true);
    } else {
      // Execute immediately
      await callback();
    }
  }, []);

  /**
   * Called when approval is granted
   */
  const onApprovalGranted = useCallback(async () => {
    if (pendingOperation) {
      await pendingOperation.callback();
      setPendingOperation(null);
      setIsModalOpen(false);
    }
  }, [pendingOperation]);

  /**
   * Called when approval times out or is rejected
   */
  const onApprovalFailed = useCallback((reason: string) => {
    console.warn('Approval failed:', reason);
    setPendingOperation(null);
    setIsModalOpen(false);
  }, []);

  /**
   * Cancel pending operation
   */
  const cancelOperation = useCallback(() => {
    setPendingOperation(null);
    setIsModalOpen(false);
  }, []);

  return {
    isModalOpen,
    pendingOperation,
    executeWithApprovalCheck,
    onApprovalGranted,
    onApprovalFailed,
    cancelOperation
  };
};
