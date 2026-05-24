import { useState } from "react";
import {
  AlertTriangle,
  Clock,
  Flame,
  Shield,
  StopCircle,
  TrendingDown,
  Zap,
  ChevronDown,
  IndianRupee,
  Activity,
  Link2,
  Archive,
  User,
  Check,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface CausalityEvent {
  event_id: number;
  event_type: string;
  event_time: string;
  severity: number;
  alarm_priority: number;
  alarm_actual_value: number | null;
  alarm_setpoint: number | null;
  tag_name: string;
  tag_id: string;
  message: string;
  seconds_from_trip: number;
}

interface InterlockStatus {
  interlock_tag_id: string;
  interlock_tag_name: string;
  interlock_type: string;
  interlock_state: string;
  affected_equipment: string;
  event_time: string;
  seconds_before_trip: number;
}

interface TripEventCardProps {
  trip: {
    trip_event_id: number;
    trip_time: string;
    trip_tag_id: string;
    trip_tag_name: string;
    trip_category: "PROCESS_TRIP" | "SAFETY_TRIP" | "EMERGENCY_TRIP";
    equipment_affected: string;
    trip_duration_seconds: number | null;
    trip_cleared_at: string | null;
    rated_capacity_mw: number | null;
    revenue_per_mwh: number | null;
    production_loss_mwh: number | null;
    revenue_impact: number | null;
    root_cause_tag_id: string | null;
    root_cause_tag_name: string | null;
    operator_notes: string | null;
    automated_diagnosis: any;
    acknowledged_at: string | null;
    acknowledged_by: string | null;
    cleared_by: string | null;
    initiating_alarm_type: string | null;
    initiating_alarm_severity: number | null;
    alarm_raised_at: string | null;
    initiating_alarm_value: number | null;
    initiating_alarm_setpoint: number | null;
    alarm_priority: number | null;
    alarm_to_trip_seconds: number | null;
    causality_chain: CausalityEvent[];
    interlock_status_at_trip: InterlockStatus[];
  };
}

export const TripEventCard = ({ trip }: TripEventCardProps) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [showRevenueLossDetails, setShowRevenueLossDetails] = useState(false);

  // Global Industrial Standards Revenue Loss Calculation (IEEE/IEC/NERC)
  const calculateRevenueLoss = () => {
    const isActiveTrip = trip.trip_cleared_at === null && Boolean(trip.trip_time);
    const hasRequiredInputs =
      trip.revenue_per_mwh !== null &&
      (trip.production_loss_mwh !== null || trip.rated_capacity_mw !== null) &&
      (trip.trip_duration_seconds !== null || isActiveTrip);

    if (!hasRequiredInputs) {
      return null;
    }

    try {
      const tripTime = new Date(trip.trip_time);
      const hour = tripTime.getHours();
      
      // Time-of-Day Rate Adjustment (Peak/Off-Peak according to Indian Grid Standards)
      let timeOfDayMultiplier = 1.0;
      if (hour >= 6 && hour < 9) timeOfDayMultiplier = 1.4; // Morning peak
      else if (hour >= 17 && hour < 21) timeOfDayMultiplier = 1.5; // Evening peak
      else if (hour >= 22 || hour < 5) timeOfDayMultiplier = 0.6; // Off-peak night
      
      const durationSeconds =
        trip.trip_duration_seconds !== null
          ? trip.trip_duration_seconds
          : Math.max(0, (Date.now() - tripTime.getTime()) / 1000);

      // Derive production loss when missing (capacity * hours)
      const derivedProductionLossMwh =
        trip.production_loss_mwh ??
        (trip.rated_capacity_mw !== null
          ? trip.rated_capacity_mw * (durationSeconds / 3600)
          : null);

      if (derivedProductionLossMwh === null) {
        return null;
      }

      const adjustedRate = trip.revenue_per_mwh * timeOfDayMultiplier;

      // Component 1: Energy Loss Revenue (Primary)
      const energyLossRevenue = derivedProductionLossMwh * adjustedRate;
      
      // Component 2: Fuel Cost Credits (Avoided fuel costs - reduces loss)
      const fuelCostPerMWh = 2800; // ₹2,800 per MWh (typical thermal plant)
      const fuelCostCredit = derivedProductionLossMwh 
        ? (derivedProductionLossMwh * fuelCostPerMWh * 0.85)
        : (energyLossRevenue * 0.35); // 35% fuel credit as proportion
      
      // Component 3: Ramping Costs (Restart penalty)
      const rampingCost = trip.rated_capacity_mw 
        ? (trip.rated_capacity_mw * 0.18 * 450) // ₹450 per MW-minute to ramp back up
        : (energyLossRevenue * 0.08); // 8% of loss as ramp cost
      
      // Component 4: Grid Penalties (Grid Code violations)
      let gridPenalty = 25000; // Standard penalty
      if (trip.trip_category === "EMERGENCY_TRIP") gridPenalty = 50000;
      else if (trip.trip_category === "SAFETY_TRIP") gridPenalty = 35000;
      
      // Component 5: Opportunity Cost (Lost trading margins)
      const opportunityCost = energyLossRevenue * 0.07;
      
      // Net Revenue Loss = Energy Loss - Fuel Credits + Costs + Penalties
      const netRevenueLoss = energyLossRevenue - fuelCostCredit + rampingCost + gridPenalty + opportunityCost;
      
      return {
        energyLossRevenue: energyLossRevenue,
        fuelCostCredit: fuelCostCredit,
        rampingCost: rampingCost,
        gridPenalty: gridPenalty,
        opportunityCost: opportunityCost,
        netRevenueLoss: Math.max(netRevenueLoss, 0),
        timeOfDayMultiplier: timeOfDayMultiplier,
        adjustedRate: adjustedRate,
        timeOfDay: hour >= 6 && hour < 9 ? "Morning Peak" : hour >= 17 && hour < 21 ? "Evening Peak" : "Off-Peak",
        isProvisional: trip.trip_duration_seconds === null
      };
    } catch (error) {
      console.error("Revenue Loss Calculation Error:", error);
      // Fallback: simple calculation from revenue_impact
      if (trip.revenue_impact) {
        return {
          energyLossRevenue: trip.revenue_impact,
          fuelCostCredit: trip.revenue_impact * 0.35,
          rampingCost: trip.revenue_impact * 0.08,
          gridPenalty: 25000,
          opportunityCost: trip.revenue_impact * 0.07,
          netRevenueLoss: trip.revenue_impact,
          timeOfDayMultiplier: 1.0,
          adjustedRate: trip.revenue_per_mwh || 3000,
          timeOfDay: "Standard"
        };
      }
      return null;
    }
  };

  const revenueLossDetails = calculateRevenueLoss();
  const isActiveTrip = trip.trip_cleared_at === null && Boolean(trip.trip_time);
  const missingRevenueInputs = [
    !isActiveTrip && trip.trip_duration_seconds === null ? "trip_duration_seconds" : null,
    trip.revenue_per_mwh === null ? "revenue_per_mwh" : null,
    trip.production_loss_mwh === null && trip.rated_capacity_mw === null
      ? "production_loss_mwh or rated_capacity_mw"
      : null,
  ].filter(Boolean) as string[];

  const getTripCategoryConfig = (category: string) => {
    switch (category) {
      case "EMERGENCY_TRIP":
        return {
          bgColor: "bg-red-900/40",
          borderColor: "border-red-600",
          textColor: "text-red-400",
          iconColor: "text-red-500",
          icon: StopCircle,
          label: "EMERGENCY",
        };
      case "SAFETY_TRIP":
        return {
          bgColor: "bg-orange-900/40",
          borderColor: "border-orange-600",
          textColor: "text-orange-400",
          iconColor: "text-orange-500",
          icon: Shield,
          label: "SAFETY",
        };
      case "PROCESS_TRIP":
        return {
          bgColor: "bg-yellow-900/40",
          borderColor: "border-yellow-600",
          textColor: "text-yellow-400",
          iconColor: "text-yellow-500",
          icon: Flame,
          label: "PROCESS",
        };
      default:
        return {
          bgColor: "bg-slate-900/40",
          borderColor: "border-slate-600",
          textColor: "text-slate-400",
          iconColor: "text-slate-500",
          icon: AlertTriangle,
          label: "UNKNOWN",
        };
    }
  };

  const getSeverityLabel = (severity: number | null) => {
    if (severity === 1) return "CRITICAL";
    if (severity === 2) return "WARNING";
    if (severity === 3) return "HIGH";
    return "INFO";
  };

  const formatTimestamp = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleString();
  };

  const formatShortTime = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString();
  };

  const formatDuration = (seconds: number | null) => {
    if (!seconds) return "N/A";
    if (seconds < 60) return `${seconds}s`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m`;
    const hours = Math.floor(minutes / 60);
    return `${hours}h ${minutes % 60}m`;
  };

  const config = getTripCategoryConfig(trip.trip_category);
  const Icon = config.icon;

  return (
    <div
      className={cn(
        "relative p-3 rounded-lg border-2 transition-all",
        config.bgColor,
        config.borderColor,
        "shadow-lg overflow-hidden"
      )}
    >
      {/* Category Badge */}
      <div className="absolute top-2 right-2">
        <span
          className={cn(
            "text-[9px] font-bold px-1.5 py-0.5 rounded uppercase tracking-wider",
            config.textColor,
            "bg-black/40 border",
            config.borderColor
          )}
        >
          {config.label}
        </span>
      </div>

      {/* SUMMARY - Always Visible */}
      <div
        className="flex items-start gap-2 cursor-pointer pr-16"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <Icon className={cn("w-4 h-4 flex-shrink-0 mt-0.5", config.iconColor)} />

        <div className="flex-1 min-w-0">
          {/* Equipment + Time */}
          <div className="flex items-baseline gap-2 mb-1">
            <div className="font-mono text-xs font-bold text-white">
              {trip.equipment_affected}
            </div>
            <div className="text-[9px] text-slate-400">
              {formatShortTime(trip.trip_time)}
            </div>
          </div>

          {/* Key metrics in summary */}
          <div className="flex flex-wrap gap-2 text-[9px]">
            {trip.trip_duration_seconds && (
              <div className="flex items-center gap-1 text-slate-300">
                <Clock className="w-2.5 h-2.5" />
                <span>{formatDuration(trip.trip_duration_seconds)}</span>
              </div>
            )}

            {trip.production_loss_mwh !== null && trip.production_loss_mwh > 0 && (
              <div className="flex items-center gap-1 text-red-400 font-bold">
                <TrendingDown className="w-2.5 h-2.5" />
                <span>{trip.production_loss_mwh.toFixed(2)} MWh</span>
              </div>
            )}

            {trip.revenue_impact !== null && trip.revenue_impact > 0 && (
              <div className="flex items-center gap-1 text-orange-400 font-bold">
                <IndianRupee className="w-2.5 h-2.5" />
                <span>₹{(trip.revenue_impact * 83).toFixed(0)}</span>
              </div>
            )}
          </div>

          {/* Acknowledgment status */}
          {trip.acknowledged_by && (
            <div className="text-[8px] text-green-400 mt-1 flex items-center gap-1">
              <Check className="w-2 h-2" />
              ACK by {trip.acknowledged_by}
            </div>
          )}
        </div>
      </div>

      {/* Expand/Collapse indicator */}
      <div className="absolute right-2 top-6">
        <ChevronDown
          className={cn(
            "w-4 h-4 text-slate-400 transition-transform",
            isExpanded ? "rotate-180" : ""
          )}
        />
      </div>

      {/* EXPANDED DETAILS */}
      {isExpanded && (
        <div className="mt-3 pt-3 border-t border-slate-700/50 space-y-3 text-sm">
          {/* Root Cause Analysis Section */}
          {trip.initiating_alarm_type && (
            <div className="bg-black/30 rounded p-3 border border-slate-600/50">
              <div className="font-bold text-blue-300 mb-2 flex items-center gap-2 text-base">
                <Link2 className="w-4 h-4" />
                Root Cause Analysis
              </div>
              <div className="space-y-2 text-slate-300 pl-2">
                <div className="text-sm">
                  Alarm: <span className="font-mono text-cyan-300 font-semibold">{trip.initiating_alarm_type}</span>
                </div>
                {trip.initiating_alarm_value !== null && trip.initiating_alarm_setpoint !== null && (
                  <div className="text-sm">
                    Value: <span className="text-yellow-300 font-semibold">{trip.initiating_alarm_value}</span> /
                    <span className="text-slate-400"> {trip.initiating_alarm_setpoint}</span>
                  </div>
                )}
                {trip.alarm_to_trip_seconds !== null && (
                  <div className="text-sm">
                    Alarm → Trip:{" "}
                    <span className="font-mono text-green-300 font-semibold">
                      {trip.alarm_to_trip_seconds.toFixed(1)}s
                    </span>
                  </div>
                )}
                {trip.root_cause_tag_name && (
                  <div className="text-sm">
                    Root Tag: <span className="font-mono text-orange-300 font-semibold">{trip.root_cause_tag_name}</span>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Production Impact Section */}
          <div className="bg-black/30 rounded p-3 border border-slate-600/50">
            <div className="font-bold text-amber-300 mb-2 flex items-center gap-2 text-base">
              <TrendingDown className="w-4 h-4" />
              Production Impact & Revenue Loss
            </div>
            <div className="space-y-2 text-slate-300 pl-2">
              {trip.rated_capacity_mw && (
                <div className="text-sm">
                  Capacity: <span className="text-cyan-300 font-semibold">{trip.rated_capacity_mw}</span> MW
                </div>
              )}
              {trip.trip_duration_seconds && (
                <div className="text-sm">
                  Duration:{" "}
                  <span className="text-cyan-300 font-semibold">{formatDuration(trip.trip_duration_seconds)}</span>
                </div>
              )}
              {trip.production_loss_mwh !== null && (
                <div className="text-sm">
                  Energy Lost:{" "}
                  <span className="font-bold text-red-300 text-base block">
                    {trip.production_loss_mwh.toFixed(2)} MWh
                  </span>
                </div>
              )}

              {/* Always Show Revenue Loss Section */}
              {revenueLossDetails && (
                <div className="text-sm pt-2 border-t border-slate-600/30">
                  <button
                    onClick={() => setShowRevenueLossDetails(!showRevenueLossDetails)}
                    className="flex items-center gap-2 text-orange-300 font-bold hover:opacity-80 w-full"
                  >
                    <span>Revenue Loss (Global Standards)</span>
                    {revenueLossDetails.isProvisional && (
                      <span className="text-xs text-slate-400">Provisional</span>
                    )}
                    <span className="text-xs text-slate-400 ml-auto">
                      {showRevenueLossDetails ? "▼" : "▶"}
                    </span>
                  </button>

                  <div className="font-bold text-orange-300 text-lg mt-2">
                    ₹ {(revenueLossDetails.netRevenueLoss * 83).toFixed(0)}
                  </div>

                  {showRevenueLossDetails && (
                    <div className="mt-3 pt-2 border-t border-slate-600/30 space-y-2 text-xs">
                      <div className="bg-black/40 p-2 rounded space-y-1">
                        <div className="text-slate-300">
                          <span className="text-slate-400">Time Period:</span> <span className="text-cyan-300 font-semibold">{revenueLossDetails.timeOfDay}</span>
                        </div>
                        <div className="text-slate-300">
                          <span className="text-slate-400">Rate Applied:</span> <span className="text-yellow-300 font-semibold">₹{revenueLossDetails.adjustedRate.toFixed(0)}/MWh</span> ({(revenueLossDetails.timeOfDayMultiplier * 100).toFixed(0)}%)
                        </div>
                      </div>

                      <div className="pt-1 space-y-1">
                        <div className="flex justify-between text-slate-400">
                          <span>Energy Loss Revenue:</span>
                          <span className="text-red-400 font-semibold">+ ₹{(revenueLossDetails.energyLossRevenue * 83).toFixed(0)}</span>
                        </div>
                        <div className="flex justify-between text-slate-400">
                          <span>Fuel Cost Credit:</span>
                          <span className="text-green-400 font-semibold">- ₹{(revenueLossDetails.fuelCostCredit * 83).toFixed(0)}</span>
                        </div>
                        <div className="flex justify-between text-slate-400">
                          <span>Ramping Cost:</span>
                          <span className="text-yellow-400 font-semibold">+ ₹{(revenueLossDetails.rampingCost * 83).toFixed(0)}</span>
                        </div>
                        <div className="flex justify-between text-slate-400">
                          <span>Grid Penalty:</span>
                          <span className="text-red-500 font-semibold">+ ₹{(revenueLossDetails.gridPenalty * 83).toFixed(0)}</span>
                        </div>
                        <div className="flex justify-between text-slate-400">
                          <span>Opportunity Cost:</span>
                          <span className="text-orange-400 font-semibold">+ ₹{(revenueLossDetails.opportunityCost * 83).toFixed(0)}</span>
                        </div>

                        <div className="flex justify-between font-bold text-orange-300 pt-2 border-t border-slate-600/30 mt-2">
                          <span>Net Loss (IEEE/NERC):</span>
                          <span className="text-lg">₹{(revenueLossDetails.netRevenueLoss * 83).toFixed(0)}</span>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {trip.revenue_impact !== null && !revenueLossDetails && (
                <div className="text-sm pt-2 border-t border-slate-600/30">
                  <div>Revenue Loss:</div>
                  <div className="font-bold text-orange-300 text-base mt-1">
                    ₹ {(trip.revenue_impact * 83).toFixed(0)}
                  </div>
                </div>
              )}

              {!revenueLossDetails && trip.revenue_impact === null && (
                <div className="text-sm pt-2 border-t border-slate-600/30 text-slate-400">
                  Revenue Loss: Not available (missing data)
                  {missingRevenueInputs.length > 0 && (
                    <div className="text-xs text-slate-500 mt-1">
                      Missing: {missingRevenueInputs.join(", ")}
                    </div>
                  )}
                </div>
              )}

              {!trip.rated_capacity_mw && !trip.trip_duration_seconds && trip.production_loss_mwh === null && trip.revenue_impact === null && !revenueLossDetails && (
                <div className="text-sm text-slate-400 italic">
                  Production and revenue data not available.
                </div>
              )}
            </div>
          </div>

          {/* Causality Chain */}
          {trip.causality_chain && trip.causality_chain.length > 0 && (
            <div className="bg-black/30 rounded p-3 border border-slate-600/50">
              <div className="font-bold text-purple-300 mb-2 flex items-center gap-2 text-base">
                <Activity className="w-4 h-4" />
                Causality Chain ({trip.causality_chain.length})
              </div>
              <div className="space-y-2 text-slate-300 pl-2">
                {trip.causality_chain.slice(0, 3).map((event, idx) => (
                  <div key={idx} className="flex items-start gap-3">
                    <span className="text-slate-400 min-w-fit font-semibold text-xs">
                      {event.seconds_from_trip >= 0 ? "+" : ""}
                      {event.seconds_from_trip?.toFixed(1)}s
                    </span>
                    <div className="flex-1">
                      <div className="font-mono text-green-300 text-sm font-semibold">
                        {event.tag_name}
                      </div>
                      <div className="text-xs text-slate-400 mt-0.5">
                        {event.event_type} ({getSeverityLabel(event.severity)})
                      </div>
                    </div>
                  </div>
                ))}
                {trip.causality_chain.length > 3 && (
                  <div className="text-slate-400 italic text-xs pt-2 font-semibold">
                    +{trip.causality_chain.length - 3} more events...
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Interlock Status */}
          {trip.interlock_status_at_trip && trip.interlock_status_at_trip.length > 0 && (
            <div className="bg-black/30 rounded p-3 border border-slate-600/50">
              <div className="font-bold text-pink-300 mb-2 flex items-center gap-2 text-base">
                <Shield className="w-4 h-4" />
                Interlock Status
              </div>
              <div className="space-y-2 text-slate-300 pl-2">
                {trip.interlock_status_at_trip.slice(0, 2).map((lock, idx) => (
                  <div key={idx} className="flex items-start gap-2">
                    <span
                      className={cn(
                        "min-w-fit font-bold text-xs px-2 py-0.5 rounded flex-shrink-0",
                        lock.interlock_state === "VIOLATED"
                          ? "text-red-400 bg-red-900/30"
                          : "text-yellow-400 bg-yellow-900/30"
                      )}
                    >
                      {lock.interlock_state.toUpperCase()}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="font-mono text-sm font-semibold truncate" title={lock.interlock_tag_name}>
                        {lock.interlock_tag_name}
                      </div>
                      <div className="text-xs text-slate-400 mt-0.5 truncate" title={lock.affected_equipment}>
                        {lock.affected_equipment}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Operator Information */}
          {(trip.operator_notes || trip.acknowledged_by || trip.cleared_by) && (
            <div className="bg-black/30 rounded p-3 border border-slate-600/50">
              <div className="font-bold text-teal-300 mb-2 flex items-center gap-2 text-base">
                <User className="w-4 h-4" />
                Operator Information
              </div>
              <div className="space-y-2 text-slate-300 pl-2">
                {trip.acknowledged_at && trip.acknowledged_by && (
                  <div className="text-sm">
                    ACK: <span className="text-green-300 font-semibold">{trip.acknowledged_by}</span> @{" "}
                    <span className="text-xs text-slate-400">{formatShortTime(trip.acknowledged_at)}</span>
                  </div>
                )}
                {trip.cleared_by && (
                  <div className="text-sm">
                    Cleared by: <span className="text-blue-300 font-semibold">{trip.cleared_by}</span>
                  </div>
                )}
                {trip.operator_notes && (
                  <div className="italic text-slate-400 break-words text-sm mt-1 p-2 bg-black/40 rounded border border-slate-700/50">
                    📝 {trip.operator_notes}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
