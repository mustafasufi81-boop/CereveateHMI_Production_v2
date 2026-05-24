import { useState, useEffect } from "react";
import { AlertTriangle, Bell, Clock, XCircle, AlertCircle, CheckCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/context/auth-context";

interface Alarm {
  id: number;
  tag_name: string;
  tag_id: string;
  event_type: string;
  alarm_state: "ACTIVE" | "ACKNOWLEDGED" | "CLEARED" | "SUPPRESSED" | null;
  alarm_priority: number; // 1=Low, 2=Med, 3=High, 4=Urgent, 5=Critical
  severity: "CRITICAL" | "HIGH" | "URGENT" | "WARNING" | "LOW";
  message: string;
  alarm_setpoint?: number;
  alarm_actual_value?: number;
  acknowledged_by?: string;
  acknowledged_at?: string;
  cleared_at?: string;
  raised_at: string;
  duration_minutes: number;
  status: "ONGOING" | "CLEARED";
}

interface AlarmPanelProps {
  className?: string;
}

export const AlarmPanel = ({ className }: AlarmPanelProps) => {
  const [alarms, setAlarms] = useState<Alarm[]>([]);
  const [isExpanded, setIsExpanded] = useState(true);
  const [loading, setLoading] = useState(true);
  const [acknowledging, setAcknowledging] = useState<number | null>(null);
  const { user } = useAuth();

  // Fetch alarms from backend
  useEffect(() => {
    const fetchAlarms = async () => {
      try {
        console.log("Fetching alarms from API...");
        const response = await fetch('/api/alarms/active?limit=10');
        console.log("Response status:", response.status);
        
        const data = await response.json();
        console.log("API response:", JSON.stringify(data, null, 2));
        console.log("data.success:", data.success);
        console.log("data.alarms:", data.alarms);
        console.log("data.alarms length:", data.alarms?.length);
        
        if (data.success && data.alarms && data.alarms.length > 0) {
          console.log(`Setting ${data.alarms.length} alarms:`, data.alarms);
          setAlarms(data.alarms);
        } else {
          console.warn("No alarms returned from API or empty array", {
            success: data.success,
            alarmsExists: !!data.alarms,
            alarmsLength: data.alarms?.length
          });
          setAlarms([]);
        }
        setLoading(false);
      } catch (error) {
        console.error("Failed to fetch alarms:", error);
        // Fallback to mock data if API fails
        const mockAlarms: Alarm[] = [
          {
            id: 1,
            tag_name: "VT-105",
            tag_id: "VT-105",
            event_type: "HIGH_LIMIT",
            alarm_state: "ACTIVE",
            alarm_priority: 5,
            severity: "CRITICAL",
            message: "Vibration High Limit Exceeded",
            alarm_actual_value: 8.2,
            raised_at: new Date(Date.now() - 2 * 60000).toISOString(),
            duration_minutes: 2,
            status: "ONGOING",
          },
          {
            id: 2,
            tag_name: "TT-101",
            tag_id: "TT-101",
            event_type: "WARNING",
            alarm_state: "ACTIVE",
            alarm_priority: 2,
            severity: "WARNING",
            message: "Temperature Approaching High Limit",
            alarm_actual_value: 92.5,
            raised_at: new Date(Date.now() - 5 * 60000).toISOString(),
            duration_minutes: 5,
            status: "ONGOING",
          },
          {
            id: 3,
            tag_name: "PT-201",
            tag_id: "PT-201",
            event_type: "LOW_LIMIT",
            alarm_state: "ACTIVE",
            alarm_priority: 3,
            severity: "HIGH",
            message: "Pressure Drop Detected",
            alarm_actual_value: 3.2,
            raised_at: new Date(Date.now() - 8 * 60000).toISOString(),
            duration_minutes: 8,
            status: "ONGOING",
          },
          {
            id: 4,
            tag_name: "ST-102",
            tag_id: "ST-102",
            event_type: "DEVIATION",
            alarm_state: "ACTIVE",
            alarm_priority: 2,
            severity: "WARNING",
            message: "Speed Deviation from Setpoint",
            alarm_actual_value: 1050,
            raised_at: new Date(Date.now() - 12 * 60000).toISOString(),
            duration_minutes: 12,
            status: "ONGOING",
          },
          {
            id: 5,
            tag_name: "FT-202",
            tag_id: "FT-202",
            event_type: "WARNING",
            alarm_state: "ACTIVE",
            alarm_priority: 1,
            severity: "LOW",
            message: "Flow Rate Below Optimal",
            alarm_actual_value: 145,
            raised_at: new Date(Date.now() - 15 * 60000).toISOString(),
            duration_minutes: 15,
            status: "ONGOING",
          },
        ];
        
        setAlarms(mockAlarms);
        setLoading(false);
      }
    };

    fetchAlarms();
    
    // Refresh alarms every 10 seconds
    const interval = setInterval(fetchAlarms, 10000);
    return () => clearInterval(interval);
  }, []);

  const getPriorityConfig = (alarm: Alarm) => {
    // Use alarm_priority if available, otherwise map severity to priority
    let priority = alarm.alarm_priority;
    if (priority === null || priority === undefined) {
      // Map severity to priority for old alarms
      switch (alarm.severity) {
        case 'CRITICAL': priority = 1; break;
        case 'HIGH': priority = 2; break;
        case 'URGENT': priority = 2; break;
        case 'WARNING': priority = 3; break;
        case 'LOW': priority = 4; break;
        default: priority = 5;
      }
    }
    
    switch (priority) {
      case 1: // CRITICAL
        return {
          bgColor: "bg-red-900/40",
          borderColor: "border-red-500",
          textColor: "text-red-400",
          iconColor: "text-red-500",
          glowColor: "shadow-red-500/50",
          icon: XCircle,
          label: "CRITICAL"
        };
      case 2: // HIGH
        return {
          bgColor: "bg-orange-900/40",
          borderColor: "border-orange-500",
          textColor: "text-orange-400",
          iconColor: "text-orange-500",
          glowColor: "shadow-orange-500/50",
          icon: AlertTriangle,
          label: "HIGH"
        };
      case 3: // MEDIUM
        return {
          bgColor: "bg-yellow-900/40",
          borderColor: "border-yellow-500",
          textColor: "text-yellow-400",
          iconColor: "text-yellow-500",
          glowColor: "shadow-yellow-500/50",
          icon: AlertCircle,
          label: "MEDIUM"
        };
      case 4: // LOW
        return {
          bgColor: "bg-blue-900/40",
          borderColor: "border-blue-500",
          textColor: "text-blue-400",
          iconColor: "text-blue-500",
          glowColor: "shadow-blue-500/50",
          icon: Bell,
          label: "LOW"
        };
      default: // INFO
        return {
          bgColor: "bg-slate-900/40",
          borderColor: "border-slate-500",
          textColor: "text-slate-400",
          iconColor: "text-slate-500",
          glowColor: "shadow-slate-500/50",
          icon: Bell,
          label: "INFO"
        };
    }
  };

  const formatTimestamp = (timestamp: string) => {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMinutes = Math.floor((now.getTime() - date.getTime()) / 60000);
    
    if (diffMinutes < 1) return "Just now";
    if (diffMinutes < 60) return `${diffMinutes}m ago`;
    if (diffMinutes < 1440) return `${Math.floor(diffMinutes / 60)}h ago`;
    return date.toLocaleDateString();
  };

  const formatDuration = (minutes: number | null) => {
    if (!minutes) return "N/A";
    if (minutes < 60) return `${Math.floor(minutes)}m`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ${Math.floor(minutes % 60)}m`;
    const days = Math.floor(hours / 24);
    return `${days}d ${hours % 24}h`;
  };

  const handleAcknowledge = async (alarmId: number, event: React.MouseEvent) => {
    event.stopPropagation();
    
    // Use logged-in username, fallback to 'operator' if not logged in
    const username = user?.username || 'operator';
    
    setAcknowledging(alarmId);
    
    try {
      const response = await fetch(
        `/api/alarms/acknowledge/${alarmId}?user=${encodeURIComponent(username)}`,
        { method: 'POST' }
      );
      
      const data = await response.json();
      
      if (data.success) {
        // Update local state to mark alarm as acknowledged
        setAlarms(prevAlarms => 
          prevAlarms.map(alarm => 
            alarm.id === alarmId 
              ? { ...alarm, alarm_state: 'ACKNOWLEDGED', acknowledged_by: username, acknowledged_at: new Date().toISOString() }
              : alarm
          )
        );
      } else {
        console.error("Failed to acknowledge alarm:", data.error);
        alert("Failed to acknowledge alarm: " + data.error);
      }
    } catch (error) {
      console.error("Error acknowledging alarm:", error);
      alert("Failed to acknowledge alarm. Please try again.");
    } finally {
      setAcknowledging(null);
    }
  };

  // Treat NULL alarm_state as ACTIVE (old alarms before lifecycle implementation)
  const activeAlarms = alarms.filter(a => a.alarm_state === 'ACTIVE' || a.alarm_state === null);
  const criticalCount = activeAlarms.filter(a => a.alarm_priority === 1 || (a.alarm_priority === null && a.severity === 'CRITICAL')).length;

  return (
    <div className={cn("relative", className)}>
      {/* Alarm Header Bar - Compact for Sidebar */}
      <div
        className={cn(
          "flex items-center justify-between px-3 py-2 rounded-t-lg border transition-all cursor-pointer",
          criticalCount > 0
            ? "bg-red-900/60 border-red-500 animate-pulse"
            : activeAlarms.length > 0
            ? "bg-orange-900/60 border-orange-500"
            : "bg-slate-800/60 border-slate-600"
        )}
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-2">
          <div className="relative">
            <Bell className={cn(
              "w-4 h-4",
              criticalCount > 0 ? "text-red-400 animate-pulse" : 
              activeAlarms.length > 0 ? "text-orange-400" : "text-slate-400"
            )} />
            {activeAlarms.length > 0 && (
              <span className="absolute -top-1 -right-1 w-3 h-3 bg-red-600 text-white text-[8px] font-bold rounded-full flex items-center justify-center animate-pulse">
                {activeAlarms.length}
              </span>
            )}
          </div>
          <div>
            <h3 className="text-xs font-bold text-white uppercase tracking-wide">
              Alarms
            </h3>
            <p className="text-[10px] text-slate-300">
              {criticalCount > 0 && <span className="text-red-400 font-bold">{criticalCount} Critical </span>}
              {activeAlarms.length === 0 ? "Normal" : `${activeAlarms.length} Active`}
            </p>
          </div>
        </div>
        
        <span className="text-xs text-slate-400">
          {isExpanded ? "▼" : "▶"}
        </span>
      </div>

      {/* Alarm List - Compact */}
      {isExpanded && (
        <div className="bg-gradient-to-br from-slate-900/95 via-slate-800/95 to-slate-900/95 border border-t-0 border-slate-600 rounded-b-lg shadow-xl">
          {loading ? (
            <div className="p-4 text-center text-slate-400">
              <div className="animate-spin w-4 h-4 border-2 border-primary border-t-transparent rounded-full mx-auto mb-2" />
              <span className="text-xs">Loading...</span>
            </div>
          ) : activeAlarms.length === 0 ? (
            <div className="p-4 text-center">
              <Bell className="w-6 h-6 text-green-500 mx-auto mb-2" />
              <p className="text-xs font-semibold text-green-400">No Active Alarms</p>
              <p className="text-[10px] text-slate-400 mt-1">System Normal</p>
            </div>
          ) : (
            <div className="overflow-y-auto" style={{ maxHeight: 'calc(40vh - 60px)' }}>
              <div className="p-2 space-y-2">
                {alarms.slice(0, 10).map((alarm) => {
                  const config = getPriorityConfig(alarm);
                  const Icon = config.icon;

                  return (
                    <div
                      key={alarm.id}
                      className={cn(
                        "relative p-2.5 rounded-lg border-2 transition-all",
                        config.bgColor,
                        config.borderColor,
                        "shadow-lg hover:shadow-xl"
                      )}
                    >
                      <div className="flex gap-2">
                        {/* Icon */}
                        <div className="flex-shrink-0">
                          <Icon className={cn("w-5 h-5", config.iconColor)} />
                        </div>

                        {/* Content */}
                        <div className="flex-1 min-w-0">
                          {/* Header Row: Tag Name Only */}
                          <div className="flex items-center gap-2 mb-1.5">
                            <span 
                              className="font-mono text-xs font-bold text-amber-400 bg-slate-950/90 px-2.5 py-1 rounded border border-amber-600/50 max-w-[180px] overflow-hidden text-ellipsis whitespace-nowrap"
                              title={alarm.tag_name}
                            >
                              {alarm.tag_name}
                            </span>
                          </div>

                          {/* Message */}
                          <p className={cn(
                            "text-xs font-semibold leading-snug mb-1.5",
                            "text-slate-100",
                            "break-words"
                          )}>
                            {alarm.message}
                          </p>

                          {/* Setpoint vs Actual */}
                          {alarm.alarm_setpoint !== null && alarm.alarm_actual_value !== null && (
                            <div className="flex items-center gap-3 mb-1.5 text-[9px]">
                              <div className="flex items-center gap-1">
                                <span className="text-slate-400">SP:</span>
                                <span className="font-mono font-bold text-white">{alarm.alarm_setpoint.toFixed(2)}</span>
                              </div>
                              <div className="flex items-center gap-1">
                                <span className="text-slate-400">PV:</span>
                                <span className={cn("font-mono font-bold", config.textColor)}>
                                  {alarm.alarm_actual_value.toFixed(2)}
                                </span>
                                {alarm.alarm_actual_value > alarm.alarm_setpoint ? (
                                  <svg className="w-3 h-3 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
                                  </svg>
                                ) : (
                                  <svg className="w-3 h-3 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 17h8m0 0V9m0 8l-8-8-4 4-6-6" />
                                  </svg>
                                )}
                              </div>
                            </div>
                          )}

                          {/* Footer - Single Row Layout */}
                          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 pt-1.5 border-t border-slate-700/50">
                            {/* Timestamp */}
                            <div className="flex items-center gap-1 text-[10px] text-slate-300 font-medium">
                              <Clock className="w-3 h-3" />
                              <span className="whitespace-nowrap">{formatTimestamp(alarm.raised_at)}</span>
                            </div>
                            
                            {/* Duration */}
                            {alarm.duration_minutes && (
                              <span className="text-[10px] text-slate-400 font-mono whitespace-nowrap">
                                {formatDuration(alarm.duration_minutes)}
                              </span>
                            )}
                            
                            {/* Spacer */}
                            <div className="flex-1 min-w-[8px]"></div>
                            
                            {/* Right Side: Badges and Button */}
                            <div className="flex items-center gap-1.5">
                              {alarm.alarm_state === 'ACKNOWLEDGED' && (
                                <span className="text-[9px] font-bold px-2 py-0.5 rounded uppercase tracking-wider text-blue-300 bg-blue-900/70 border border-blue-500 whitespace-nowrap">
                                  ACK
                                </span>
                              )}
                              <span className={cn(
                                "text-[9px] font-bold px-2 py-0.5 rounded uppercase tracking-wider whitespace-nowrap",
                                "text-white",
                                "bg-black/60 border-2",
                                config.borderColor
                              )}>
                                {config.label}
                              </span>
                              
                              {/* Acknowledge Button or Acknowledged By */}
                              {(alarm.alarm_state === 'ACTIVE' || alarm.alarm_state === null) ? (
                                <button
                                  onClick={(e) => handleAcknowledge(alarm.id, e)}
                                  disabled={acknowledging === alarm.id}
                                  className={cn(
                                    "flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold whitespace-nowrap",
                                    "bg-slate-700 hover:bg-slate-600 text-white",
                                    "border border-slate-500 hover:border-slate-400",
                                    "transition-all duration-200",
                                    "disabled:opacity-50 disabled:cursor-not-allowed",
                                    acknowledging === alarm.id && "animate-pulse"
                                  )}
                                >
                                  {acknowledging === alarm.id ? (
                                    <>
                                      <div className="animate-spin w-2.5 h-2.5 border-2 border-white border-t-transparent rounded-full" />
                                      <span>ACK...</span>
                                    </>
                                  ) : (
                                    <>
                                      <CheckCircle className="w-3 h-3" />
                                      <span>ACK</span>
                                    </>
                                  )}
                                </button>
                              ) : alarm.alarm_state === 'ACKNOWLEDGED' && alarm.acknowledged_by ? (
                                <div className="text-[10px] text-blue-300 font-semibold whitespace-nowrap">
                                  By: {alarm.acknowledged_by}
                                </div>
                              ) : null}
                            </div>
                          </div>
                        </div>
                      </div>

                      {/* Pulsing animation for critical alarms */}
                      {(alarm.alarm_priority === 1 || (alarm.alarm_priority === null && alarm.severity === 'CRITICAL')) && (alarm.alarm_state === 'ACTIVE' || alarm.alarm_state === null) && (
                        <div className="absolute inset-0 rounded-lg border-2 border-red-500 animate-pulse opacity-30 pointer-events-none" />
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
