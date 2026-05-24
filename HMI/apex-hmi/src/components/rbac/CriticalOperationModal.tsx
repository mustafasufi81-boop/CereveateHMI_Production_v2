import React, { useState, useEffect } from 'react';
import { AlertTriangle, X, Clock, Info } from 'lucide-react';
import { cn } from '@/lib/utils';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

interface CriticalOperationModalProps {
  isOpen: boolean;
  onClose: () => void;
  operationCode: string;
  operationName: string;
  targetEquipment: string;
  targetTag: string;
  currentValue: any;
  targetValue: any;
  onApprovalReceived?: (approvalData: any) => void;
}

interface CriticalOperation {
  id: number;
  operation_code: string;
  operation_name: string;
  severity: string;
  requires_role: string;
  timeout_minutes: number;
  description: string;
}

export const CriticalOperationModal: React.FC<CriticalOperationModalProps> = ({
  isOpen,
  onClose,
  operationCode,
  operationName,
  targetEquipment,
  targetTag,
  currentValue,
  targetValue,
  onApprovalReceived
}) => {
  const [justification, setJustification] = useState('');
  const [priority, setPriority] = useState<'normal' | 'high' | 'urgent'>('normal');
  const [submitting, setSubmitting] = useState(false);
  const [operationInfo, setOperationInfo] = useState<CriticalOperation | null>(null);
  const [pendingApproval, setPendingApproval] = useState<any>(null);
  const [pollingInterval, setPollingInterval] = useState<any>(null);

  useEffect(() => {
    if (isOpen && operationCode) {
      fetchOperationInfo();
    }
    return () => {
      if (pollingInterval) clearInterval(pollingInterval);
    };
  }, [isOpen, operationCode]);

  const fetchOperationInfo = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE_URL}/api/approval/check/${operationCode}`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      const data = await response.json();
      if (data.is_critical) {
        setOperationInfo(data.operation);
      }
    } catch (error) {
      console.error('Failed to fetch operation info:', error);
    }
  };

  const checkApprovalStatus = async (operationId: string) => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE_URL}/api/approval/operation/${operationId}`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      const data = await response.json();
      
      if (data.approval) {
        if (data.approval.status === 'approved') {
          // Approval received!
          if (pollingInterval) clearInterval(pollingInterval);
          if (onApprovalReceived) {
            onApprovalReceived(data.approval);
          }
          alert('✅ Operation approved! You may now proceed.');
          onClose();
        } else if (data.approval.status === 'denied') {
          if (pollingInterval) clearInterval(pollingInterval);
          alert(`❌ Operation denied: ${data.approval.denial_reason}`);
          setPendingApproval(null);
        } else if (data.approval.status === 'expired') {
          if (pollingInterval) clearInterval(pollingInterval);
          alert('⏱️ Approval request expired');
          setPendingApproval(null);
        }
      }
    } catch (error) {
      console.error('Failed to check approval status:', error);
    }
  };

  const handleSubmit = async () => {
    if (!justification.trim()) {
      alert('Please provide justification for this operation');
      return;
    }

    setSubmitting(true);
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE_URL}/api/approval/request`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          operation_code: operationCode,
          target_equipment: targetEquipment,
          target_tag: targetTag,
          current_value: currentValue,
          target_value: targetValue,
          justification,
          priority
        })
      });

      const data = await response.json();
      
      if (response.ok) {
        setPendingApproval(data);
        alert(`✅ Approval request submitted!\nOperation ID: ${data.operation_id}\nExpires in: ${data.timeout_minutes} minutes`);
        
        // Start polling for approval status
        const interval = setInterval(() => {
          checkApprovalStatus(data.operation_id);
        }, 5000); // Check every 5 seconds
        setPollingInterval(interval);
      } else {
        alert(`Failed to request approval: ${data.message}`);
      }
    } catch (error) {
      console.error('Failed to request approval:', error);
      alert('Failed to request approval');
    } finally {
      setSubmitting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50">
      <div className="bg-[#2A2A2C] border-2 border-red-500 rounded-lg p-6 max-w-lg w-full mx-4">
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-3">
            <AlertTriangle className="w-8 h-8 text-red-500" />
            <div>
              <h2 className="text-xl font-bold text-[#E5E5E5]">Critical Operation Approval Required</h2>
              <p className="text-sm text-[#999]">{operationName}</p>
            </div>
          </div>
          <button 
            onClick={onClose}
            className="text-[#999] hover:text-white"
          >
            <X className="w-6 h-6" />
          </button>
        </div>

        {!pendingApproval ? (
          <>
            {operationInfo && (
              <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded">
                <div className="flex items-center gap-2 mb-2">
                  <Info className="w-4 h-4 text-red-400" />
                  <span className="text-sm font-semibold text-red-400">Operation Details</span>
                </div>
                <div className="text-xs text-[#E5E5E5] space-y-1">
                  <p>Severity: <span className="text-red-400">{operationInfo.severity}</span></p>
                  <p>Required Role: <span className="text-yellow-400">{operationInfo.requires_role}</span></p>
                  <p>Timeout: <span className="text-yellow-400">{operationInfo.timeout_minutes} minutes</span></p>
                  <p className="mt-2">{operationInfo.description}</p>
                </div>
              </div>
            )}

            <div className="mb-4 p-3 bg-[#1C1C1E] rounded">
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div>
                  <span className="text-[#999]">Equipment:</span>
                  <p className="text-[#E5E5E5]">{targetEquipment}</p>
                </div>
                <div>
                  <span className="text-[#999]">Tag:</span>
                  <p className="text-[#E5E5E5]">{targetTag}</p>
                </div>
                <div className="col-span-2">
                  <span className="text-[#999]">Value Change:</span>
                  <p>
                    <span className="text-red-400">{String(currentValue)}</span>
                    <span className="text-[#999]"> → </span>
                    <span className="text-green-400">{String(targetValue)}</span>
                  </p>
                </div>
              </div>
            </div>

            <div className="mb-4">
              <label className="block text-sm text-[#999] mb-2">Priority</label>
              <select 
                value={priority}
                onChange={(e) => setPriority(e.target.value as any)}
                className="w-full bg-[#1C1C1E] border border-[#404040] rounded px-3 py-2 text-[#E5E5E5]"
              >
                <option value="normal">Normal</option>
                <option value="high">High</option>
                <option value="urgent">Urgent</option>
              </select>
            </div>

            <div className="mb-4">
              <label className="block text-sm text-[#999] mb-2">Justification *</label>
              <textarea 
                value={justification}
                onChange={(e) => setJustification(e.target.value)}
                placeholder="Explain why this operation is necessary..."
                rows={4}
                className="w-full bg-[#1C1C1E] border border-[#404040] rounded px-3 py-2 text-[#E5E5E5] resize-none"
              />
            </div>

            <div className="flex gap-2">
              <button 
                onClick={handleSubmit}
                disabled={submitting || !justification.trim()}
                className="flex-1 px-4 py-2 bg-red-600 hover:bg-red-700 disabled:bg-gray-600 rounded text-white"
              >
                {submitting ? 'Requesting...' : 'Request Approval'}
              </button>
              <button 
                onClick={onClose}
                className="px-4 py-2 bg-[#404040] hover:bg-[#505050] rounded text-white"
              >
                Cancel
              </button>
            </div>
          </>
        ) : (
          <div className="text-center py-6">
            <Clock className="w-16 h-16 text-yellow-500 mx-auto mb-4 animate-pulse" />
            <h3 className="text-lg font-bold text-[#E5E5E5] mb-2">Waiting for Approval...</h3>
            <p className="text-sm text-[#999] mb-4">
              Operation ID: <span className="text-[#E5E5E5]">{pendingApproval.operation_id}</span>
            </p>
            <p className="text-xs text-[#666]">
              Checking for approval every 5 seconds...<br />
              Expires in: {pendingApproval.timeout_minutes} minutes
            </p>
            <button 
              onClick={onClose}
              className="mt-6 px-4 py-2 bg-[#404040] hover:bg-[#505050] rounded text-white text-sm"
            >
              Close (will keep checking in background)
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
