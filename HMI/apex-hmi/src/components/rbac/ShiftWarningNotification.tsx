import React, { useState, useEffect } from 'react';
import { AlertCircle, Clock, X } from 'lucide-react';
import { cn } from '@/lib/utils';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

interface ShiftInfo {
  shift_id: number;
  shift_name: string;
  start_time: string;
  end_time: string;
}

interface ShiftAccessCheck {
  has_access: boolean;
  current_shift: ShiftInfo | null;
  user_shifts: ShiftInfo[];
  warning_message: string | null;
}

interface ShiftWarningNotificationProps {
  className?: string;
  onShiftChange?: (shiftInfo: ShiftAccessCheck) => void;
}

export const ShiftWarningNotification: React.FC<ShiftWarningNotificationProps> = ({ 
  className,
  onShiftChange 
}) => {
  const [shiftInfo, setShiftInfo] = useState<ShiftAccessCheck | null>(null);
  const [dismissed, setDismissed] = useState(false);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    checkShiftAccess();
    
    // Check every 5 minutes
    const interval = setInterval(checkShiftAccess, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (shiftInfo && !shiftInfo.has_access && !dismissed) {
      setVisible(true);
      if (onShiftChange) {
        onShiftChange(shiftInfo);
      }
    } else {
      setVisible(false);
    }
  }, [shiftInfo, dismissed]);

  const checkShiftAccess = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE_URL}/api/shift/check-access`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      
      if (response.ok) {
        const data = await response.json();
        setShiftInfo(data);
        
        // Reset dismissed state if shift changes
        if (data.current_shift) {
          setDismissed(false);
        }
      }
    } catch (error) {
      console.error('Failed to check shift access:', error);
    }
  };

  const handleDismiss = () => {
    setDismissed(true);
    setVisible(false);
  };

  if (!visible || !shiftInfo || shiftInfo.has_access) {
    return null;
  }

  const severityLevel = shiftInfo.warning_message?.toLowerCase().includes('not assigned') 
    ? 'error' 
    : 'warning';

  return (
    <div className={cn(
      'fixed top-4 right-4 z-50 max-w-md',
      'bg-[#2A2A2C] border-2 rounded-lg shadow-2xl p-4',
      severityLevel === 'error' ? 'border-red-500' : 'border-yellow-500',
      'animate-in slide-in-from-right duration-300',
      className
    )}>
      <div className="flex items-start gap-3">
        <AlertCircle className={cn(
          'w-6 h-6 flex-shrink-0 mt-0.5',
          severityLevel === 'error' ? 'text-red-500' : 'text-yellow-500'
        )} />
        
        <div className="flex-1">
          <div className="flex items-center justify-between mb-2">
            <h3 className={cn(
              'font-bold',
              severityLevel === 'error' ? 'text-red-400' : 'text-yellow-400'
            )}>
              Shift Access Warning
            </h3>
            <button 
              onClick={handleDismiss}
              className="text-[#999] hover:text-white"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <p className="text-sm text-[#E5E5E5] mb-3">
            {shiftInfo.warning_message}
          </p>

          {shiftInfo.current_shift && (
            <div className="bg-[#1C1C1E] rounded p-2 mb-3">
              <div className="flex items-center gap-2 text-xs">
                <Clock className="w-4 h-4 text-blue-400" />
                <div>
                  <p className="text-[#999]">Current Shift:</p>
                  <p className="text-[#E5E5E5] font-semibold">
                    {shiftInfo.current_shift.shift_name}
                  </p>
                  <p className="text-[#999]">
                    {shiftInfo.current_shift.start_time} - {shiftInfo.current_shift.end_time}
                  </p>
                </div>
              </div>
            </div>
          )}

          {shiftInfo.user_shifts && shiftInfo.user_shifts.length > 0 && (
            <div className="bg-[#1C1C1E] rounded p-2">
              <p className="text-xs text-[#999] mb-2">Your Assigned Shifts:</p>
              <div className="space-y-1">
                {shiftInfo.user_shifts.map(shift => (
                  <div key={shift.shift_id} className="text-xs">
                    <span className="text-[#E5E5E5] font-semibold">{shift.shift_name}</span>
                    <span className="text-[#666]"> ({shift.start_time} - {shift.end_time})</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="mt-3 pt-3 border-t border-[#404040]">
            <p className="text-xs text-[#666]">
              {severityLevel === 'error' 
                ? '⛔ You may not be able to perform certain operations outside your assigned shifts.'
                : '⚠️ Limited access - contact your supervisor if you need shift reassignment.'
              }
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
