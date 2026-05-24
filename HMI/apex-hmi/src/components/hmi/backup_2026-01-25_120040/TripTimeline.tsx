import { useState, useEffect } from "react";
import { AlertTriangle, Clock, Flame, Shield, StopCircle, TrendingDown, Zap } from "lucide-react";
import { cn } from "@/lib/utils";

interface TripEvent {
  trip_event_id: number;
  trip_time: string;
  trip_tag_id: string;
  trip_tag_name: string;
  trip_category: "PROCESS_TRIP" | "SAFETY_TRIP" | "EMERGENCY_TRIP";
  equipment_affected: string;
  trip_duration_seconds: number | null;
  trip_cleared_at: string | null;
  production_loss_mw: number | null;
  root_cause_tag_id: string | null;
  root_cause_tag_name: string | null;
  operator_notes: string | null;
  initiating_alarm_type: string | null;
  alarm_raised_at: string | null;
  alarm_to_trip_seconds: number | null;
  alarm_priority: number | null;
}

interface TripTimelineProps {
  className?: string;
}

export const TripTimeline = ({ className }: TripTimelineProps) => {
  const [trips, setTrips] = useState<TripEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [isExpanded, setIsExpanded] = useState(true);

  useEffect(() => {
    const fetchTrips = async () => {
      try {
        const response = await fetch('/api/alarms/trips?limit=20');
        const data = await response.json();
        
        if (data.success && data.trips) {
          setTrips(data.trips);
        } else {
          setTrips([]);
        }
        setLoading(false);
      } catch (error) {
        console.error("Failed to fetch trips:", error);
        setTrips([]);
        setLoading(false);
      }
    };

    fetchTrips();
    
    // Refresh every 30 seconds
    const interval = setInterval(fetchTrips, 30000);
    return () => clearInterval(interval);
  }, []);

  const getTripCategoryConfig = (category: string) => {
    switch (category) {
      case "EMERGENCY_TRIP":
        return {
          bgColor: "bg-red-900/40",
          borderColor: "border-red-600",
          textColor: "text-red-400",
          iconColor: "text-red-500",
          icon: StopCircle,
          label: "EMERGENCY"
        };
      case "SAFETY_TRIP":
        return {
          bgColor: "bg-orange-900/40",
          borderColor: "border-orange-600",
          textColor: "text-orange-400",
          iconColor: "text-orange-500",
          icon: Shield,
          label: "SAFETY"
        };
      case "PROCESS_TRIP":
        return {
          bgColor: "bg-yellow-900/40",
          borderColor: "border-yellow-600",
          textColor: "text-yellow-400",
          iconColor: "text-yellow-500",
          icon: Flame,
          label: "PROCESS"
        };
      default:
        return {
          bgColor: "bg-slate-900/40",
          borderColor: "border-slate-600",
          textColor: "text-slate-400",
          iconColor: "text-slate-500",
          icon: AlertTriangle,
          label: "UNKNOWN"
        };
    }
  };

  const formatTimestamp = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleString();
  };

  const formatDuration = (seconds: number | null) => {
    if (!seconds) return "N/A";
    if (seconds < 60) return `${seconds}s`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m`;
    const hours = Math.floor(minutes / 60);
    return `${hours}h ${minutes % 60}m`;
  };

  return (
    <div className={cn("relative", className)}>
      {/* Trip Header */}
      <div
        className={cn(
          "flex items-center justify-between px-3 py-2 rounded-t-lg border transition-all cursor-pointer",
          trips.length > 0
            ? "bg-red-900/60 border-red-500"
            : "bg-slate-800/60 border-slate-600"
        )}
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-2">
          <Zap className={cn(
            "w-4 h-4",
            trips.length > 0 ? "text-red-400" : "text-slate-400"
          )} />
          <div>
            <h3 className="text-xs font-bold text-white uppercase tracking-wide">
              Trip Events
            </h3>
            <p className="text-[10px] text-slate-300">
              {trips.length === 0 ? "No recent trips" : `${trips.length} trips in history`}
            </p>
          </div>
        </div>
        
        <span className="text-xs text-slate-400">
          {isExpanded ? "▼" : "▶"}
        </span>
      </div>

      {/* Trip List */}
      {isExpanded && (
        <div className="bg-gradient-to-br from-slate-900/95 via-slate-800/95 to-slate-900/95 border border-t-0 border-slate-600 rounded-b-lg shadow-xl">
          {loading ? (
            <div className="p-4 text-center text-slate-400">
              <div className="animate-spin w-4 h-4 border-2 border-primary border-t-transparent rounded-full mx-auto mb-2" />
              <span className="text-xs">Loading...</span>
            </div>
          ) : trips.length === 0 ? (
            <div className="p-4 text-center">
              <Shield className="w-6 h-6 text-green-500 mx-auto mb-2" />
              <p className="text-xs font-semibold text-green-400">No Trip Events</p>
              <p className="text-[10px] text-slate-400 mt-1">System operating normally</p>
            </div>
          ) : (
            <div className="max-h-[400px] overflow-y-auto custom-scrollbar">
              <div className="p-2 space-y-2">
                {trips.map((trip) => {
                  const config = getTripCategoryConfig(trip.trip_category);
                  const Icon = config.icon;

                  return (
                    <div
                      key={trip.trip_event_id}
                      className={cn(
                        "relative p-3 rounded-lg border-2 transition-all",
                        config.bgColor,
                        config.borderColor,
                        "shadow-lg"
                      )}
                    >
                      {/* Category Badge */}
                      <div className="absolute top-2 right-2">
                        <span className={cn(
                          "text-[9px] font-bold px-2 py-1 rounded uppercase tracking-wider",
                          config.textColor,
                          "bg-black/40 border",
                          config.borderColor
                        )}>
                          {config.label}
                        </span>
                      </div>

                      <div className="flex gap-3">
                        {/* Icon */}
                        <div className="flex-shrink-0 mt-0.5">
                          <Icon className={cn("w-6 h-6", config.iconColor)} />
                        </div>

                        {/* Content */}
                        <div className="flex-1 min-w-0 pr-16">
                          {/* Equipment */}
                          <div className="flex items-center gap-2 mb-2">
                            <span className="font-mono text-sm font-bold text-white">
                              {trip.equipment_affected}
                            </span>
                          </div>

                          {/* Trip Details */}
                          <div className="space-y-1 text-xs">
                            <div className="flex items-center gap-2 text-slate-300">
                              <Clock className="w-3 h-3" />
                              <span className="text-[10px]">{formatTimestamp(trip.trip_time)}</span>
                            </div>

                            {trip.trip_duration_seconds && (
                              <div className="flex items-center gap-2">
                                <span className="text-[10px] text-slate-400">Duration:</span>
                                <span className="text-[10px] font-semibold text-white">
                                  {formatDuration(trip.trip_duration_seconds)}
                                </span>
                              </div>
                            )}

                            {trip.production_loss_mw && (
                              <div className="flex items-center gap-2">
                                <TrendingDown className="w-3 h-3 text-red-400" />
                                <span className="text-[10px] text-slate-400">Loss:</span>
                                <span className="text-[10px] font-bold text-red-400">
                                  {trip.production_loss_mw.toFixed(2)} MW
                                </span>
                              </div>
                            )}
                          </div>

                          {/* Causality */}
                          {trip.initiating_alarm_type && (
                            <div className="mt-2 pt-2 border-t border-slate-700/50">
                              <div className="text-[10px] text-slate-400 mb-1">Initiated by:</div>
                              <div className="flex items-center gap-2">
                                <span className="font-mono text-[10px] text-orange-400 bg-orange-900/30 px-2 py-0.5 rounded">
                                  {trip.initiating_alarm_type}
                                </span>
                                {trip.alarm_to_trip_seconds && (
                                  <span className="text-[9px] text-slate-500">
                                    ({formatDuration(trip.alarm_to_trip_seconds)} after alarm)
                                  </span>
                                )}
                              </div>
                            </div>
                          )}

                          {/* Root Cause */}
                          {trip.root_cause_tag_name && (
                            <div className="mt-1">
                              <span className="text-[10px] text-slate-400">Root Cause: </span>
                              <span className="font-mono text-[10px] text-blue-400">
                                {trip.root_cause_tag_name}
                              </span>
                            </div>
                          )}

                          {/* Operator Notes */}
                          {trip.operator_notes && (
                            <div className="mt-2 text-[10px] text-slate-300 italic">
                              "{trip.operator_notes}"
                            </div>
                          )}
                        </div>
                      </div>
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
