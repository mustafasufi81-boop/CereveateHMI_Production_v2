import { cn } from "@/lib/utils";
import { AlertTriangle, Activity, TrendingUp } from "lucide-react";

interface DigitalReadoutProps {
  label: string;
  tagId: string;
  value: number;
  unit: string;
  isAlarm?: boolean;
  alarmMessage?: string;
  onTrendClick?: () => void;
}

export const DigitalReadout = ({
  label,
  tagId,
  value,
  unit,
  isAlarm = false,
  alarmMessage,
  onTrendClick
}: DigitalReadoutProps) => {
  return (
    <div className={cn(
      "relative bg-gradient-to-br from-slate-800/50 via-slate-700/50 to-slate-800/50 rounded-lg border-2 p-5 shadow-xl transition-all duration-300 hover:shadow-2xl hover:border-primary/50 cursor-pointer group",
      isAlarm ? "border-red-500 shadow-red-500/50 animate-pulse" : "border-primary/30"
    )}
    onClick={onTrendClick}
    >
      {/* Trend Button Overlay */}
      {onTrendClick && (
        <button 
          className="absolute top-3 right-12 p-2 bg-primary/20 hover:bg-primary/30 rounded-lg border border-primary/40 transition-all opacity-0 group-hover:opacity-100"
          onClick={(e) => {
            e.stopPropagation();
            onTrendClick();
          }}
        >
          <TrendingUp className="w-4 h-4 text-primary" />
        </button>
      )}

      {/* Header Section */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex-1">
          <h3 className="text-sm font-bold text-white uppercase tracking-wider">{label}</h3>
          <p className="text-xs text-primary font-mono mt-0.5 bg-primary/10 inline-block px-2 py-0.5 rounded">{tagId}</p>
        </div>
        {isAlarm ? (
          <AlertTriangle className="w-6 h-6 text-red-500 animate-pulse" />
        ) : (
          <Activity className="w-6 h-6 text-green-500 animate-pulse" />
        )}
      </div>

      {/* Digital Value Display */}
      <div className={cn(
        "flex flex-col items-center justify-center py-6 rounded-lg border-2",
        isAlarm 
          ? "bg-red-500/10 border-red-500/50" 
          : "bg-slate-900/60 border-primary/20"
      )}>
        <div className="flex items-baseline">
          <span className={cn(
            "font-mono text-4xl font-bold tracking-tight tabular-nums",
            isAlarm ? "text-red-500" : "text-green-500"
          )}>
            {value.toFixed(1)}
          </span>
          <span className="text-lg text-slate-400 ml-2 font-medium">{unit}</span>
        </div>
      </div>

      {/* Alarm Message */}
      {isAlarm && alarmMessage && (
        <div className="mt-4 flex items-center gap-2 text-xs font-semibold text-red-500 bg-red-500/10 border border-red-500/30 rounded-md p-3">
          <span className="relative flex h-3 w-3">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-500 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-3 w-3 bg-red-500"></span>
          </span>
          <span className="flex-1">{alarmMessage}</span>
        </div>
      )}
    </div>
  );
};
