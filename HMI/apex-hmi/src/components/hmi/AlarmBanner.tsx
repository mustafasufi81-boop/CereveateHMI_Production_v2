import { AlertTriangle, CheckCircle, ChevronLeft, ChevronRight } from "lucide-react";
import { useState } from "react";

interface Alarm {
  id: string;
  message: string;
  timestamp: string;
  severity: "critical" | "warning";
  status: "active" | "resolved";
  resolvedAt?: string;
}

interface AlarmBannerProps {
  alarms: Alarm[];
  onDismiss?: (id: string) => void;
}

export const AlarmBanner = ({ alarms, onDismiss }: AlarmBannerProps) => {
  const [isExpanded, setIsExpanded] = useState(true);
  
  if (alarms.length === 0) return null;

  const activeAlarms = alarms.filter(a => a.status === "active");
  const resolvedAlarms = alarms.filter(a => a.status === "resolved");

  return (
    <div className={`fixed left-0 top-0 bottom-0 z-50 flex transition-all duration-300 ${
      isExpanded ? "w-80" : "w-10"
    }`}>
      {/* Expanded alarm panel */}
      <div className={`flex-1 bg-hmi-panel/98 border-r border-hmi-border backdrop-blur-sm overflow-hidden flex flex-col ${
        isExpanded ? "opacity-100" : "opacity-0 w-0"
      }`}>
        {/* Header */}
        <div className={`p-3 border-b ${
          activeAlarms.length > 0 ? "bg-status-alarm/20 border-status-alarm/40" : "border-hmi-border"
        }`}>
          <div className="flex items-center gap-2">
            <AlertTriangle className={`w-5 h-5 ${activeAlarms.length > 0 ? "text-status-alarm" : "text-muted-foreground"}`} />
            <span className="font-semibold text-sm uppercase tracking-wide">
              Alarms
            </span>
          </div>
          <div className="text-xs text-muted-foreground mt-1">
            {activeAlarms.length} Active • {resolvedAlarms.length} Resolved
          </div>
        </div>

        {/* Scrollable alarm list */}
        <div className="flex-1 overflow-y-auto p-3 space-y-4">
          {/* Active Alarms Section */}
          {activeAlarms.length > 0 && (
            <div>
              <h3 className="text-xs font-semibold text-status-alarm uppercase tracking-wide mb-2 flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-status-alarm animate-pulse" />
                Active ({activeAlarms.length})
              </h3>
              <div className="space-y-2">
                {activeAlarms.map((alarm) => (
                  <div 
                    key={alarm.id} 
                    className={`p-2 rounded ${
                      alarm.severity === "critical" 
                        ? "bg-status-alarm/20 border border-status-alarm/40" 
                        : "bg-status-warning/20 border border-status-warning/40"
                    }`}
                  >
                    <div className="flex items-start gap-2">
                      <AlertTriangle className={`w-4 h-4 mt-0.5 shrink-0 ${
                        alarm.severity === "critical" ? "text-status-alarm" : "text-status-warning"
                      }`} />
                      <div className="flex-1 min-w-0">
                        <p className="font-mono text-xs text-foreground break-words">{alarm.message}</p>
                        <div className="flex items-center gap-2 mt-1">
                          <span className={`text-[10px] px-1.5 py-0.5 rounded uppercase font-semibold ${
                            alarm.severity === "critical" 
                              ? "bg-status-alarm/30 text-status-alarm" 
                              : "bg-status-warning/30 text-status-warning"
                          }`}>
                            {alarm.severity}
                          </span>
                          <span className="text-[10px] text-muted-foreground font-mono">{alarm.timestamp}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Resolved Alarms Section */}
          {resolvedAlarms.length > 0 && (
            <div>
              <h3 className="text-xs font-semibold text-status-normal uppercase tracking-wide mb-2 flex items-center gap-2">
                <CheckCircle className="w-3 h-3" />
                Resolved ({resolvedAlarms.length})
              </h3>
              <div className="space-y-2">
                {resolvedAlarms.map((alarm) => (
                  <div 
                    key={alarm.id} 
                    className="p-2 rounded bg-status-normal/10 border border-status-normal/20 opacity-70"
                  >
                    <div className="flex items-start gap-2">
                      <CheckCircle className="w-4 h-4 mt-0.5 shrink-0 text-status-normal" />
                      <div className="flex-1 min-w-0">
                        <p className="font-mono text-xs text-muted-foreground break-words">{alarm.message}</p>
                        <div className="flex flex-col gap-0.5 mt-1 text-[10px] text-muted-foreground font-mono">
                          <span>Started: {alarm.timestamp}</span>
                          <span>Resolved: {alarm.resolvedAt}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Toggle button */}
      <button 
        className={`w-10 shrink-0 flex flex-col items-center justify-center gap-2 transition-colors ${
          activeAlarms.length > 0 
            ? "bg-status-alarm/90 hover:bg-status-alarm text-white" 
            : "bg-hmi-panel hover:bg-hmi-border text-muted-foreground"
        } border-r border-hmi-border`}
        onClick={() => setIsExpanded(!isExpanded)}
      >
        {isExpanded ? (
          <ChevronLeft className="w-4 h-4" />
        ) : (
          <>
            <ChevronRight className="w-4 h-4" />
            <AlertTriangle className="w-4 h-4" />
            {activeAlarms.length > 0 && (
              <span className="text-xs font-bold">{activeAlarms.length}</span>
            )}
          </>
        )}
      </button>
    </div>
  );
};
