import { useState, useEffect } from "react";
import { AlertTriangle, Clock, Flame, Shield, StopCircle, TrendingDown, Zap, FileText, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { TripEventCard } from "./TripEventCard";

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
  // Phase 1 fields
  rated_capacity_mw: number | null;
  revenue_per_mwh: number | null;
  production_loss_mwh: number | null;
  revenue_impact: number | null;
  acknowledged_at: string | null;
  acknowledged_by: string | null;
  cleared_by: string | null;
  initiating_alarm_severity: number | null;
  initiating_alarm_value: number | null;
  initiating_alarm_setpoint: number | null;
  automated_diagnosis: any;
  causality_chain: any[];
  interlock_status_at_trip: any[];
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

  return (
    <div className={cn("relative flex flex-col h-full", className)}>
      {/* Trip Header */}
      <div
        className={cn(
          "flex items-center justify-between px-3 py-1 rounded-t-lg border transition-all cursor-pointer",
          trips.length > 0
            ? "bg-fuchsia-900/60 border-fuchsia-500"
            : "bg-purple-900/60 border-purple-600"
        )}
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-2">
          <Zap className={cn(
            "w-3 h-3",
            trips.length > 0 ? "text-fuchsia-400" : "text-purple-400"
          )} />
          <div>
            <h3 className="text-[10px] font-bold text-white uppercase tracking-wide">
              Trip Events
            </h3>
            <p className="text-[9px] text-slate-300">
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
        <div className="flex-1 overflow-hidden bg-gradient-to-br from-slate-900/95 via-slate-800/95 to-slate-900/95 border border-t-0 border-slate-600 rounded-b-lg shadow-xl">
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
            <div className="overflow-y-auto custom-scrollbar" style={{ height: '100%' }}>
              <div className="p-2 space-y-2">
                {trips.map((trip) => (
                  <TripEventCard key={trip.trip_event_id} trip={trip} />
                ))}
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
