import React, { useState, useEffect } from 'react';
import { Search, Filter, Download } from 'lucide-react';
import { cn } from '@/lib/utils';
import api from '@/services/api';

interface AuditLog {
  id: number;
  user_id: number;
  username: string;
  action_type: string;
  description: string;
  details?: any;
  ip_address: string;
  session_token?: string;
  created_at: string;
}

interface AuditLogViewerProps {
  className?: string;
}

export const AuditLogViewer: React.FC<AuditLogViewerProps> = ({ className }) => {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [actionTypeFilter, setActionTypeFilter] = useState('');
  const [dateRange, setDateRange] = useState({ start: '', end: '' });
  const [actionTypes, setActionTypes] = useState<string[]>([]);

  useEffect(() => {
    fetchActionTypes();
    fetchLogs();
  }, []);

  const fetchActionTypes = async () => {
    try {
      const response = await api.get('/audit/action-types');
      if (response.data.action_types) {
        setActionTypes(response.data.action_types.map((at: any) => at.action_type));
      }
    } catch (error) {
      console.error('Failed to fetch action types:', error);
    }
  };

  const fetchLogs = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (searchTerm) params.append('username', searchTerm);
      if (actionTypeFilter) params.append('action_type', actionTypeFilter);
      if (dateRange.start) params.append('start_date', dateRange.start);
      if (dateRange.end) params.append('end_date', dateRange.end);
      params.append('limit', '100');

      const response = await api.get(`/audit/search?${params}`);
      setLogs(response.data.logs || []);
    } catch (error) {
      console.error('Failed to fetch audit logs:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = () => {
    fetchLogs();
  };

  const getSeverityColor = (actionType: string) => {
    if (actionType.includes('delete') || actionType.includes('revoke')) return 'bg-red-500/20 text-red-400';
    if (actionType.includes('create') || actionType.includes('add')) return 'bg-green-500/20 text-green-400';
    if (actionType.includes('update') || actionType.includes('modify')) return 'bg-yellow-500/20 text-yellow-400';
    return 'bg-blue-500/20 text-blue-400';
  };

  return (
    <div className={cn('bg-[#2A2A2C] border border-[#404040] rounded p-4', className)}>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-bold text-[#E5E5E5]">Audit Log Trail</h2>
        <button 
          onClick={handleSearch}
          className="px-3 py-1 bg-blue-600 hover:bg-blue-700 rounded text-sm text-white"
        >
          <Download className="inline w-4 h-4 mr-1" />
          Export
        </button>
      </div>

      {/* Filters */}
      <div className="grid grid-cols-4 gap-2 mb-4">
        <div>
          <label className="text-xs text-[#999]">Search Username</label>
          <input 
            type="text" 
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Username..."
            className="w-full bg-[#1C1C1E] border border-[#404040] rounded px-2 py-1 text-sm text-[#E5E5E5]"
          />
        </div>
        
        <div>
          <label className="text-xs text-[#999]">Action Type</label>
          <select 
            value={actionTypeFilter}
            onChange={(e) => setActionTypeFilter(e.target.value)}
            className="w-full bg-[#1C1C1E] border border-[#404040] rounded px-2 py-1 text-sm text-[#E5E5E5]"
          >
            <option value="">All Actions</option>
            {actionTypes.map(type => (
              <option key={type} value={type}>{type}</option>
            ))}
          </select>
        </div>
        
        <div>
          <label className="text-xs text-[#999]">Start Date</label>
          <input 
            type="date" 
            value={dateRange.start}
            onChange={(e) => setDateRange({...dateRange, start: e.target.value})}
            className="w-full bg-[#1C1C1E] border border-[#404040] rounded px-2 py-1 text-sm text-[#E5E5E5]"
          />
        </div>
        
        <div>
          <label className="text-xs text-[#999]">End Date</label>
          <input 
            type="date" 
            value={dateRange.end}
            onChange={(e) => setDateRange({...dateRange, end: e.target.value})}
            className="w-full bg-[#1C1C1E] border border-[#404040] rounded px-2 py-1 text-sm text-[#E5E5E5]"
          />
        </div>
      </div>

      <button 
        onClick={handleSearch}
        disabled={loading}
        className="w-full mb-4 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 rounded text-sm text-white"
      >
        <Search className="inline w-4 h-4 mr-2" />
        Search Logs
      </button>

      {/* Audit Log Table */}
      <div className="overflow-auto max-h-[600px]">
        <table className="w-full text-sm">
          <thead className="bg-[#1C1C1E] sticky top-0">
            <tr>
              <th className="text-left px-2 py-2 text-[#999]">Timestamp</th>
              <th className="text-left px-2 py-2 text-[#999]">User</th>
              <th className="text-left px-2 py-2 text-[#999]">Action</th>
              <th className="text-left px-2 py-2 text-[#999]">Description</th>
              <th className="text-left px-2 py-2 text-[#999]">IP Address</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={5} className="text-center py-8 text-[#666]">
                  Loading audit logs...
                </td>
              </tr>
            ) : logs.length === 0 ? (
              <tr>
                <td colSpan={5} className="text-center py-8 text-[#666]">
                  No audit logs found
                </td>
              </tr>
            ) : (
              logs.map(log => (
                <tr key={log.id} className="border-b border-[#404040] hover:bg-[#333]">
                  <td className="px-2 py-2 text-[#E5E5E5]">
                    {new Date(log.created_at).toLocaleString()}
                  </td>
                  <td className="px-2 py-2 text-[#E5E5E5]">{log.username}</td>
                  <td className="px-2 py-2">
                    <span className={cn('px-2 py-1 rounded text-xs', getSeverityColor(log.action_type))}>
                      {log.action_type}
                    </span>
                  </td>
                  <td className="px-2 py-2 text-[#E5E5E5]">{log.description}</td>
                  <td className="px-2 py-2 text-[#999]">{log.ip_address}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
