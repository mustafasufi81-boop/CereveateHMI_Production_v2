import React, { useState, useEffect } from 'react';
import { CheckCircle, XCircle, Clock, AlertTriangle, Info } from 'lucide-react';
import { cn } from '@/lib/utils';
import api from '@/services/api';

interface PendingApproval {
  operation_id: string;
  operation_name: string;
  severity: string;
  requested_by: number;
  requester_username: string;
  target_equipment: string;
  target_tag: string;
  target_value: any;
  current_value: any;
  justification: string;
  priority: string;
  requested_at: string;
  expires_at: string;
  timeout_minutes: number;
}

interface ApprovalDashboardProps {
  className?: string;
}

export const ApprovalDashboard: React.FC<ApprovalDashboardProps> = ({ className }) => {
  const [pendingApprovals, setPendingApprovals] = useState<PendingApproval[]>([]);
  const [myRequests, setMyRequests] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<'pending' | 'my-requests'>('pending');

  useEffect(() => {
    fetchPendingApprovals();
    fetchMyRequests();
    
    // Refresh every 10 seconds
    const interval = setInterval(() => {
      fetchPendingApprovals();
      fetchMyRequests();
    }, 10000);
    return () => clearInterval(interval);
  }, []);

  const fetchPendingApprovals = async () => {
    try {
      const response = await api.get('/approval/pending');
      setPendingApprovals(response.data.approvals || []);
    } catch (error) {
      console.error('Failed to fetch pending approvals:', error);
    }
  };

  const fetchMyRequests = async () => {
    try {
      const response = await api.get('/approval/my-requests');
      setMyRequests(response.data.requests || []);
    } catch (error) {
      console.error('Failed to fetch my requests:', error);
    }
  };

  const handleApprove = async (operationId: string) => {
    if (!confirm('Approve this critical operation?')) return;
    
    try {
      const response = await api.post(`/approval/approve/${operationId}`);
      alert(response.data.message || 'Operation approved');
      fetchPendingApprovals();
      fetchMyRequests();
    } catch (error: any) {
      console.error('Failed to approve:', error);
      alert(error.response?.data?.message || 'Failed to approve operation');
    }
  };

  const handleDeny = async (operationId: string) => {
    const reason = prompt('Enter denial reason:');
    if (!reason) return;
    
    try {
      const response = await api.post(`/approval/deny/${operationId}`, {
        denial_reason: reason
      });
      alert(response.data.message || 'Operation denied');
      fetchPendingApprovals();
      fetchMyRequests();
    } catch (error: any) {
      console.error('Failed to deny:', error);
      alert(error.response?.data?.message || 'Failed to deny operation');
    }
  };

  const getTimeRemaining = (expiresAt: string) => {
    const expires = new Date(expiresAt);
    const now = new Date();
    const diff = expires.getTime() - now.getTime();
    const minutes = Math.floor(diff / (1000 * 60));
    if (minutes < 0) return 'Expired';
    if (minutes < 1) return '< 1m';
    return `${minutes}m`;
  };

  const getPriorityColor = (priority: string) => {
    switch (priority) {
      case 'urgent': return 'bg-red-500 text-white';
      case 'high': return 'bg-orange-500 text-white';
      case 'normal': return 'bg-blue-500 text-white';
      case 'low': return 'bg-gray-500 text-white';
      default: return 'bg-gray-500 text-white';
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'approved': return 'text-green-400';
      case 'denied': return 'text-red-400';
      case 'expired': return 'text-gray-400';
      case 'pending': return 'text-yellow-400';
      case 'executed': return 'text-blue-400';
      default: return 'text-gray-400';
    }
  };

  return (
    <div className={cn('bg-[#2A2A2C] border border-[#404040] rounded p-4', className)}>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-bold text-[#E5E5E5]">Critical Operation Approvals</h2>
        <div className="flex gap-2">
          <button 
            onClick={() => setActiveTab('pending')}
            className={cn(
              'px-3 py-1 rounded text-sm',
              activeTab === 'pending' 
                ? 'bg-blue-600 text-white' 
                : 'bg-[#1C1C1E] text-[#999] hover:text-white'
            )}
          >
            Pending ({pendingApprovals.length})
          </button>
          <button 
            onClick={() => setActiveTab('my-requests')}
            className={cn(
              'px-3 py-1 rounded text-sm',
              activeTab === 'my-requests' 
                ? 'bg-blue-600 text-white' 
                : 'bg-[#1C1C1E] text-[#999] hover:text-white'
            )}
          >
            My Requests ({myRequests.length})
          </button>
        </div>
      </div>

      {activeTab === 'pending' && (
        <div className="space-y-3">
          {pendingApprovals.length === 0 ? (
            <div className="text-center py-8 text-[#666]">
              <Info className="inline w-8 h-8 mb-2" />
              <p>No pending approvals</p>
            </div>
          ) : (
            pendingApprovals.map(approval => (
              <div 
                key={approval.operation_id}
                className="border border-[#404040] rounded p-3 bg-[#1C1C1E]"
              >
                <div className="flex items-start justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <AlertTriangle className="w-5 h-5 text-orange-500" />
                    <span className="font-semibold text-[#E5E5E5]">{approval.operation_name}</span>
                    <span className={cn('px-2 py-0.5 rounded text-xs', getPriorityColor(approval.priority))}>
                      {approval.priority}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 text-xs">
                    <Clock className="w-4 h-4 text-yellow-500" />
                    <span className="text-yellow-500">{getTimeRemaining(approval.expires_at)}</span>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2 text-xs mb-3">
                  <div>
                    <span className="text-[#999]">Requested by: </span>
                    <span className="text-[#E5E5E5]">{approval.requester_username}</span>
                  </div>
                  <div>
                    <span className="text-[#999]">Equipment: </span>
                    <span className="text-[#E5E5E5]">{approval.target_equipment}</span>
                  </div>
                  <div>
                    <span className="text-[#999]">Tag: </span>
                    <span className="text-[#E5E5E5]">{approval.target_tag}</span>
                  </div>
                  <div>
                    <span className="text-[#999]">Change: </span>
                    <span className="text-red-400">{approval.current_value}</span>
                    <span className="text-[#999]"> → </span>
                    <span className="text-green-400">{approval.target_value}</span>
                  </div>
                </div>

                <div className="mb-3 p-2 bg-[#2A2A2C] rounded">
                  <span className="text-xs text-[#999]">Justification: </span>
                  <p className="text-xs text-[#E5E5E5] mt-1">{approval.justification}</p>
                </div>

                <div className="flex gap-2">
                  <button 
                    onClick={() => handleApprove(approval.operation_id)}
                    className="flex-1 px-3 py-2 bg-green-600 hover:bg-green-700 rounded text-sm text-white"
                  >
                    <CheckCircle className="inline w-4 h-4 mr-1" />
                    Approve
                  </button>
                  <button 
                    onClick={() => handleDeny(approval.operation_id)}
                    className="flex-1 px-3 py-2 bg-red-600 hover:bg-red-700 rounded text-sm text-white"
                  >
                    <XCircle className="inline w-4 h-4 mr-1" />
                    Deny
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {activeTab === 'my-requests' && (
        <div className="space-y-3">
          {myRequests.length === 0 ? (
            <div className="text-center py-8 text-[#666]">
              <Info className="inline w-8 h-8 mb-2" />
              <p>No approval requests</p>
            </div>
          ) : (
            myRequests.map(request => (
              <div 
                key={request.operation_id}
                className="border border-[#404040] rounded p-3 bg-[#1C1C1E]"
              >
                <div className="flex items-start justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-[#E5E5E5]">{request.operation_name}</span>
                    <span className={cn('text-sm', getStatusColor(request.status))}>
                      {request.status}
                    </span>
                  </div>
                  <span className="text-xs text-[#999]">
                    {new Date(request.requested_at).toLocaleString()}
                  </span>
                </div>

                <div className="text-xs text-[#999]">
                  <p>Equipment: {request.target_equipment} | Tag: {request.target_tag}</p>
                  {request.approver_username && (
                    <p className="mt-1">Approver: {request.approver_username}</p>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
};
