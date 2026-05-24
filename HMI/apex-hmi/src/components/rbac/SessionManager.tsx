import React, { useState, useEffect } from 'react';
import { Power, Monitor, Shield, RefreshCw } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useAuth } from '@/context/auth-context';
import api from '@/services/api';

interface Session {
  session_id: number;
  user_id: number;
  username: string;
  role_name: string;
  ip_address: string;
  device_type: string;
  browser: string;
  login_time: string;
  last_activity: string;
  idle_minutes: number;
  session_duration_minutes: number;
  idle_timeout_minutes: number;
  absolute_timeout_minutes: number;
  is_idle_expired: boolean;
  is_absolute_expired: boolean;
}

interface SessionManagerProps {
  className?: string;
}

export const SessionManager: React.FC<SessionManagerProps> = ({ className }) => {
  const { user } = useAuth();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(false);
  const [currentUserId, setCurrentUserId] = useState<string | null>(null);

  useEffect(() => {
    if (user?.id) {
      setCurrentUserId(user.id);
    }
    fetchSessions();
    
    // Refresh sessions every 30 seconds
    const interval = setInterval(fetchSessions, 30000);
    return () => clearInterval(interval);
  }, [user]);

  const fetchSessions = async () => {
    setLoading(true);
    try {
      // Use /api/session/active - it handles both admin (all sessions) and regular users (own sessions)
      const response = await api.get('/session/active');
      setSessions(response.data.sessions || []);
    } catch (error) {
      console.error('Failed to fetch sessions:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleEndSession = async (sessionId: number) => {
    if (!confirm('Are you sure you want to end this session?')) return;
    
    try {
      await api.post(`/session/end-by-id/${sessionId}`);
      fetchSessions();
    } catch (error: any) {
      console.error('Failed to end session:', error);
      alert(error.response?.data?.message || 'Failed to end session');
    }
  };

  const handleEndAllSessions = async () => {
    if (!confirm('End all other sessions? This will log you out from all other devices.')) return;
    
    try {
      const response = await api.post('/session/end-all');
      alert(response.data.message);
      fetchSessions();
    } catch (error: any) {
      console.error('Failed to end all sessions:', error);
      alert(error.response?.data?.message || 'Failed to end all sessions');
    }
  };

  const isCurrentSession = (session: Session) => {
    // Check if this session belongs to the current user
    return currentUserId && session.user_id.toString() === currentUserId && sessions.indexOf(session) === 0;
  };

  const getSessionAge = (durationMinutes: number) => {
    const hours = Math.floor(durationMinutes / 60);
    const minutes = Math.floor(durationMinutes % 60);
    return hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`;
  };

  const getLastActivityTime = (idleMinutes: number) => {
    if (idleMinutes < 1) return 'Just now';
    if (idleMinutes < 60) return `${Math.floor(idleMinutes)}m ago`;
    const hours = Math.floor(idleMinutes / 60);
    const mins = Math.floor(idleMinutes % 60);
    return hours > 0 ? `${hours}h ${mins}m ago` : `${mins}m ago`;
  };

  return (
    <div className={cn('bg-[#2A2A2C] border border-[#404040] rounded p-4', className)}>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Monitor className="w-5 h-5 text-[#E5E5E5]" />
          <h2 className="text-lg font-bold text-[#E5E5E5]">Active Sessions</h2>
          <span className="text-xs text-[#999]">({sessions.length} active)</span>
        </div>
        <div className="flex items-center gap-2">
          <button 
            onClick={fetchSessions}
            disabled={loading}
            className="px-3 py-1 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 rounded text-sm text-white flex items-center gap-1"
          >
            <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} />
            Refresh
          </button>
          <button 
            onClick={handleEndAllSessions}
            disabled={sessions.length <= 1}
            className="px-3 py-1 bg-red-600 hover:bg-red-700 disabled:bg-gray-600 rounded text-sm text-white"
          >
            <Power className="inline w-4 h-4 mr-1" />
            End All Others
          </button>
        </div>
      </div>

      {loading && sessions.length === 0 ? (
        <div className="text-center py-8 text-[#666]">Loading sessions...</div>
      ) : sessions.length === 0 ? (
        <div className="text-center py-8 text-[#666]">No active sessions</div>
      ) : (
        <div className="space-y-3">
          {sessions.map(session => {
            const isCurrent = isCurrentSession(session);
            const isExpiring = session.idle_minutes > (session.idle_timeout_minutes * 0.8);
            return (
              <div 
                key={session.session_id}
                className={cn(
                  'border rounded p-3',
                  isCurrent ? 'border-green-500 bg-green-500/10' : 'border-[#404040] bg-[#1C1C1E]',
                  isExpiring && 'border-yellow-500/50'
                )}
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-2">
                      {isCurrent && (
                        <Shield className="w-4 h-4 text-green-500" />
                      )}
                      <span className={cn('text-sm font-semibold', isCurrent ? 'text-green-400' : 'text-[#E5E5E5]')}>
                        {session.username}
                      </span>
                      {user?.isAdmin && (
                        <span className="text-xs text-[#999] bg-[#2A2A2C] px-2 py-0.5 rounded">
                          {session.role_name}
                        </span>
                      )}
                      <span className="text-xs text-[#999]">
                        {getSessionAge(session.session_duration_minutes)} old
                      </span>
                    </div>
                    
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      <div>
                        <span className="text-[#999]">IP Address: </span>
                        <span className="text-[#E5E5E5]">{session.ip_address || 'Unknown'}</span>
                      </div>
                      <div>
                        <span className="text-[#999]">Last Activity: </span>
                        <span className={cn('text-[#E5E5E5]', isExpiring && 'text-yellow-500')}>
                          {getLastActivityTime(session.idle_minutes)}
                        </span>
                      </div>
                      <div>
                        <span className="text-[#999]">Device: </span>
                        <span className="text-[#E5E5E5]">{session.device_type || 'Unknown'}</span>
                      </div>
                      <div>
                        <span className="text-[#999]">Browser: </span>
                        <span className="text-[#E5E5E5]">{session.browser || 'Unknown'}</span>
                      </div>
                      {isExpiring && (
                        <div className="col-span-2">
                          <span className="text-yellow-500 text-xs">
                            ⚠️ Session will expire soon due to inactivity
                          </span>
                        </div>
                      )}
                    </div>
                  </div>
                  
                  {user?.isAdmin && (
                    <button 
                      onClick={() => handleEndSession(session.session_id)}
                      className="ml-2 px-2 py-1 bg-red-600 hover:bg-red-700 rounded text-xs text-white"
                    >
                      <Power className="inline w-3 h-3 mr-1" />
                      End
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <div className="mt-4 pt-4 border-t border-[#404040]">
        <div className="flex items-center gap-2 text-xs text-[#999]">
          <Shield className="w-4 h-4" />
          <span>
            Sessions automatically expire after 30 minutes of inactivity. 
            Concurrent logins are limited for security.
          </span>
        </div>
      </div>
    </div>
  );
};
