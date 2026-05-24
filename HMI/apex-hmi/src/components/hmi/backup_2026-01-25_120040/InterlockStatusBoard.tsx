import { useState, useEffect } from "react";
import { Shield, ShieldAlert, ShieldCheck, ShieldOff, Clock, User, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";

interface InterlockState {
  interlock_event_id: number;
  event_time: string;
  interlock_tag_id: string;
  interlock_tag_name: string;
  interlock_type: "PERMISSIVE" | "CONDITIONAL" | "SEQUENTIAL" | "PROTECTIVE";
  interlock_state: "SATISFIED" | "VIOLATED" | "BYPASSED" | "UNKNOWN";
  previous_state: string | null;
  state_duration_seconds: number | null;
  affected_equipment: string;
  bypass_reason: string | null;
  bypass_authorized_by: string | null;
  bypass_expires_at: string | null;
  bypass_remaining_seconds: number | null;
  related_trip_event_id: number | null;
  status: "EXPIRED_BYPASS" | "ACTIVE_BYPASS" | "VIOLATION" | "NORMAL";
}

interface InterlockStatusBoardProps {
  className?: string;
}

export const InterlockStatusBoard = ({ className }: InterlockStatusBoardProps) => {
  const [interlocks, setInterlocks] = useState<InterlockState[]>([]);
  const [loading, setLoading] = useState(true);
  const [isExpanded, setIsExpanded] = useState(true);

  useEffect(() => {
    const fetchInterlocks = async () => {
      try {
        const response = await fetch('/api/alarms/interlocks?limit=20');
        const data = await response.json();
        
        if (data.success && data.interlocks) {
          setInterlocks(data.interlocks);
        } else {
          setInterlocks([]);
        }
        setLoading(false);
      } catch (error) {
        console.error("Failed to fetch interlocks:", error);
        setInterlocks([]);
        setLoading(false);
      }
    };

    fetchInterlocks();
    
    // Refresh every 5 seconds (critical safety info)
    const interval = setInterval(fetchInterlocks, 5000);
    return () => clearInterval(interval);
  }, []);

  const getInterlockConfig = (interlock: InterlockState) => {
    if (interlock.status === "VIOLATION") {
      return {
        bgColor: "bg-red-900/40",
        borderColor: "border-red-600",
        textColor: "text-red-400",
        iconColor: "text-red-500",
        icon: ShieldAlert,
        statusLabel: "VIOLATED",
        statusColor: "text-red-400 bg-red-900/60"
      };
    }
    if (interlock.status === "EXPIRED_BYPASS") {
      return {
        bgColor: "bg-orange-900/40",
        borderColor: "border-orange-600",
        textColor: "text-orange-400",
        iconColor: "text-orange-500",
        icon: AlertTriangle,
        statusLabel: "EXPIRED BYPASS",
        statusColor: "text-orange-400 bg-orange-900/60"
      };
    }
    if (interlock.status === "ACTIVE_BYPASS") {
      return {
        bgColor: "bg-yellow-900/40",
        borderColor: "border-yellow-600",
        textColor: "text-yellow-400",
        iconColor: "text-yellow-500",
        icon: ShieldOff,
        statusLabel: "BYPASSED",
        statusColor: "text-yellow-400 bg-yellow-900/60"
      };
    }
    return {
      bgColor: "bg-green-900/40",
      borderColor: "border-green-600",
      textColor: "text-green-400",
      iconColor: "text-green-500",
      icon: ShieldCheck,
      statusLabel: "SATISFIED",
      statusColor: "text-green-400 bg-green-900/60"
    };
  };

  const getInterlockTypeLabel = (type: string) => {
    switch (type) {
      case "PERMISSIVE":
        return { label: "PERMISSIVE", desc: "Must be true to start" };
      case "CONDITIONAL":
        return { label: "CONDITIONAL", desc: "Must stay true while running" };
      case "SEQUENTIAL":
        return { label: "SEQUENTIAL", desc: "Order dependency" };
      case "PROTECTIVE":
        return { label: "PROTECTIVE", desc: "Fault protection" };
      default:
        return { label: type, desc: "" };
    }
  };

  const formatDuration = (seconds: number | null) => {
    if (!seconds || seconds < 0) return "N/A";
    if (seconds < 60) return `${Math.floor(seconds)}s`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m`;
    const hours = Math.floor(minutes / 60);
    return `${hours}h ${minutes % 60}m`;
  };

  const formatTimestamp = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleString();
  };

  const violations = interlocks.filter(i => i.status === "VIOLATION");
  const bypasses = interlocks.filter(i => i.status === "ACTIVE_BYPASS" || i.status === "EXPIRED_BYPASS");

  return (
    <div className={cn("relative", className)}>
      {/* Interlock Header */}
      <div
        className={cn(
          "flex items-center justify-between px-3 py-2 rounded-t-lg border transition-all cursor-pointer",
          violations.length > 0
            ? "bg-red-900/60 border-red-500 animate-pulse"
            : bypasses.length > 0
            ? "bg-yellow-900/60 border-yellow-500"
            : "bg-slate-800/60 border-slate-600"
        )}
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-2">
          <Shield className={cn(
            "w-4 h-4",
            violations.length > 0 ? "text-red-400 animate-pulse" : 
            bypasses.length > 0 ? "text-yellow-400" : "text-slate-400"
          )} />
          <div>
            <h3 className="text-xs font-bold text-white uppercase tracking-wide">
              Interlocks
            </h3>
            <p className="text-[10px] text-slate-300">
              {violations.length > 0 && <span className="text-red-400 font-bold">{violations.length} Violated </span>}
              {bypasses.length > 0 && <span className="text-yellow-400 font-bold">{bypasses.length} Bypassed </span>}
              {violations.length === 0 && bypasses.length === 0 && "All normal"}
            </p>
          </div>
        </div>
        
        <span className="text-xs text-slate-400">
          {isExpanded ? "▼" : "▶"}
        </span>
      </div>

      {/* Interlock List */}
      {isExpanded && (
        <div className="bg-gradient-to-br from-slate-900/95 via-slate-800/95 to-slate-900/95 border border-t-0 border-slate-600 rounded-b-lg shadow-xl">
          {loading ? (
            <div className="p-4 text-center text-slate-400">
              <div className="animate-spin w-4 h-4 border-2 border-primary border-t-transparent rounded-full mx-auto mb-2" />
              <span className="text-xs">Loading...</span>
            </div>
          ) : interlocks.length === 0 ? (
            <div className="p-4 text-center">
              <ShieldCheck className="w-6 h-6 text-green-500 mx-auto mb-2" />
              <p className="text-xs font-semibold text-green-400">All Interlocks Satisfied</p>
              <p className="text-[10px] text-slate-400 mt-1">Safety systems normal</p>
            </div>
          ) : (
            <div className="max-h-[400px] overflow-y-auto custom-scrollbar">
              <div className="p-2 space-y-2">
                {interlocks.map((interlock) => {
                  const config = getInterlockConfig(interlock);
                  const typeInfo = getInterlockTypeLabel(interlock.interlock_type);
                  const Icon = config.icon;

                  return (
                    <div
                      key={interlock.interlock_event_id}
                      className={cn(
                        "relative p-3 rounded-lg border-2 transition-all",
                        config.bgColor,
                        config.borderColor,
                        "shadow-lg"
                      )}
                    >
                      {/* Status Badge */}
                      <div className="absolute top-2 right-2">
                        <span className={cn(
                          "text-[9px] font-bold px-2 py-1 rounded uppercase tracking-wider",
                          config.statusColor,
                          "border",
                          config.borderColor
                        )}>
                          {config.statusLabel}
                        </span>
                      </div>

                      <div className="flex gap-3">
                        {/* Icon */}
                        <div className="flex-shrink-0 mt-0.5">
                          <Icon className={cn("w-6 h-6", config.iconColor)} />
                        </div>

                        {/* Content */}
                        <div className="flex-1 min-w-0 pr-24">
                          {/* Tag Name */}
                          <div className="flex items-center gap-2 mb-1">
                            <span className="font-mono text-xs font-bold text-white bg-slate-950/80 px-2 py-1 rounded border border-slate-600">
                              {interlock.interlock_tag_name || interlock.interlock_tag_id}
                            </span>
                          </div>

                          {/* Equipment */}
                          <div className="text-xs text-slate-300 mb-2">
                            {interlock.affected_equipment}
                          </div>

                          {/* Type */}
                          <div className="flex items-center gap-2 mb-2">
                            <span className="text-[9px] font-bold px-2 py-0.5 rounded bg-slate-700 text-slate-300 border border-slate-600">
                              {typeInfo.label}
                            </span>
                            <span className="text-[9px] text-slate-400">{typeInfo.desc}</span>
                          </div>

                          {/* Bypass Information */}
                          {(interlock.status === "ACTIVE_BYPASS" || interlock.status === "EXPIRED_BYPASS") && (
                            <div className="mt-2 pt-2 border-t border-slate-700/50 space-y-1">
                              {interlock.bypass_reason && (
                                <div className="text-[10px] text-yellow-300">
                                  <span className="font-semibold">Reason:</span> {interlock.bypass_reason}
                                </div>
                              )}
                              {interlock.bypass_authorized_by && (
                                <div className="flex items-center gap-1 text-[10px] text-slate-300">
                                  <User className="w-3 h-3" />
                                  <span>By: {interlock.bypass_authorized_by}</span>
                                </div>
                              )}
                              {interlock.bypass_expires_at && (
                                <div className="flex items-center gap-1 text-[10px]">
                                  <Clock className="w-3 h-3" />
                                  {interlock.status === "EXPIRED_BYPASS" ? (
                                    <span className="text-red-400 font-bold">EXPIRED</span>
                                  ) : (
                                    <>
                                      <span className="text-slate-400">Expires in:</span>
                                      <span className="font-bold text-yellow-400">
                                        {formatDuration(interlock.bypass_remaining_seconds)}
                                      </span>
                                    </>
                                  )}
                                </div>
                              )}
                            </div>
                          )}

                          {/* Timestamp */}
                          <div className="mt-2 text-[10px] text-slate-500">
                            {formatTimestamp(interlock.event_time)}
                          </div>
                        </div>
                      </div>

                      {/* Pulsing animation for violations */}
                      {interlock.status === "VIOLATION" && (
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

      <style>{`
        .custom-scrollbar::-webkit-scrollbar {
          width: 8px;
        }
        .custom-scrollbar::-webkit-scrollbar-track {
          background: rgba(15, 23, 42, 0.5);
          border-radius: 4px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb {
          background: rgba(100, 116, 139, 0.6);
          border-radius: 4px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover {
          background: rgba(148, 163, 184, 0.8);
        }
      `}</style>
    </div>
  );
};
