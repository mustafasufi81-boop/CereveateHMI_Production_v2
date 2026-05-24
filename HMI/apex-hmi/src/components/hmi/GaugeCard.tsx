import { cn } from "@/lib/utils";
import { TrendingUp } from "lucide-react";

interface GaugeCardProps {
  label: string;
  tagId: string;
  value: number;
  unit: string;
  min: number;
  max: number;
  warningThreshold?: number;
  alarmThreshold?: number;
  isAlarm?: boolean;
  onTrendClick?: () => void;
}

export const GaugeCard = ({
  label,
  tagId,
  value,
  unit,
  min,
  max,
  warningThreshold,
  alarmThreshold,
  isAlarm = false,
  onTrendClick
}: GaugeCardProps) => {
  const percentage = ((value - min) / (max - min)) * 100;
  const clampedPercentage = Math.min(Math.max(percentage, 0), 100);
  
  // Calculate the arc path
  const radius = 60;
  const strokeWidth = 12;
  const centerX = 70;
  const centerY = 70;
  const startAngle = 135;
  const endAngle = 405;
  const angleRange = endAngle - startAngle;
  
  const polarToCartesian = (angle: number) => {
    const radian = (angle - 90) * Math.PI / 180;
    return {
      x: centerX + radius * Math.cos(radian),
      y: centerY + radius * Math.sin(radian)
    };
  };
  
  const createArc = (startDeg: number, endDeg: number) => {
    const start = polarToCartesian(startDeg);
    const end = polarToCartesian(endDeg);
    const largeArcFlag = endDeg - startDeg <= 180 ? 0 : 1;
    return `M ${start.x} ${start.y} A ${radius} ${radius} 0 ${largeArcFlag} 1 ${end.x} ${end.y}`;
  };

  const valueAngle = startAngle + (angleRange * clampedPercentage) / 100;
  
  // Calculate needle endpoint
  const needleLength = radius - 5;
  const needleAngle = valueAngle;
  const needleEndX = centerX + needleLength * Math.cos((needleAngle - 90) * Math.PI / 180);
  const needleEndY = centerY + needleLength * Math.sin((needleAngle - 90) * Math.PI / 180);
  
  // Define color segments for the gradient arc
  const getColorSegments = () => {
    const normalZone = 70; // 70% is normal operating range (green)
    const warningZone = warningThreshold ? ((warningThreshold - min) / (max - min)) * 100 : 80;
    const alarmZone = alarmThreshold ? ((alarmThreshold - min) / (max - min)) * 100 : 90;
    
    return [
      { start: 0, end: 20, color: '#ef4444' }, // Red (low)
      { start: 20, end: 30, color: '#f97316' }, // Orange
      { start: 30, end: warningZone, color: '#10b981' }, // Green (optimal)
      { start: warningZone, end: alarmZone, color: '#eab308' }, // Yellow (warning)
      { start: alarmZone, end: 100, color: '#ef4444' }, // Red (alarm)
    ];
  };
  
  const getValueColor = () => {
    if (isAlarm || (alarmThreshold && value >= alarmThreshold)) return "text-red-500";
    if (warningThreshold && value >= warningThreshold) return "text-yellow-500";
    return "text-green-500";
  };

  const getNeedleColor = () => {
    if (isAlarm || (alarmThreshold && value >= alarmThreshold)) return "#ef4444";
    if (warningThreshold && value >= warningThreshold) return "#eab308";
    return "#10b981";
  };

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
          className="absolute top-3 right-3 p-2 bg-primary/20 hover:bg-primary/30 rounded-lg border border-primary/40 transition-all opacity-0 group-hover:opacity-100"
          onClick={(e) => {
            e.stopPropagation();
            onTrendClick();
          }}
        >
          <TrendingUp className="w-4 h-4 text-primary" />
        </button>
      )}

      {/* Header Section */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex-1">
          <h3 className="text-sm font-bold text-white uppercase tracking-wider">{label}</h3>
          <p className="text-xs text-primary font-mono mt-0.5 bg-primary/10 inline-block px-2 py-0.5 rounded">{tagId}</p>
        </div>
        <div className={cn(
          "w-3 h-3 rounded-full",
          isAlarm ? "bg-red-500 animate-pulse" : "bg-green-500"
        )} />
      </div>

      {/* Gauge SVG */}
      <div className="flex justify-center">
        <svg width="140" height="100" viewBox="0 0 140 100">
          {/* Color segments for the gauge */}
          {getColorSegments().map((segment, index) => {
            const segmentStartAngle = startAngle + (angleRange * segment.start) / 100;
            const segmentEndAngle = startAngle + (angleRange * segment.end) / 100;
            return (
              <path
                key={index}
                d={createArc(segmentStartAngle, segmentEndAngle)}
                fill="none"
                stroke={segment.color}
                strokeWidth={strokeWidth}
                strokeLinecap="round"
                opacity={0.9}
              />
            );
          })}

          {/* Tick marks */}
          {[0, 25, 50, 75, 100].map((tick) => {
            const tickAngle = startAngle + (angleRange * tick) / 100;
            const tickStart = polarToCartesian(tickAngle);
            const tickRadius = radius - strokeWidth / 2 - 3;
            const tickEnd = {
              x: centerX + tickRadius * Math.cos((tickAngle - 90) * Math.PI / 180),
              y: centerY + tickRadius * Math.sin((tickAngle - 90) * Math.PI / 180),
            };
            return (
              <line
                key={tick}
                x1={tickStart.x}
                y1={tickStart.y}
                x2={tickEnd.x}
                y2={tickEnd.y}
                stroke="rgba(148, 163, 184, 0.6)"
                strokeWidth="2"
                opacity={0.5}
              />
            );
          })}

          {/* Center pivot point */}
          <circle
            cx={centerX}
            cy={centerY}
            r="5"
            fill="rgb(30, 41, 59)"
            stroke={getNeedleColor()}
            strokeWidth="2"
          />

          {/* Needle/Pointer - wider base */}
          <line
            x1={centerX}
            y1={centerY}
            x2={needleEndX}
            y2={needleEndY}
            stroke={getNeedleColor()}
            strokeWidth="3"
            strokeLinecap="round"
            style={{ 
              filter: `drop-shadow(0 2px 4px rgba(0,0,0,0.3))`,
            }}
          />

          {/* Needle tip circle */}
          <circle
            cx={needleEndX}
            cy={needleEndY}
            r="4"
            fill={getNeedleColor()}
            stroke="white"
            strokeWidth="1"
          />

          {/* Min/Max labels */}
          <text x="15" y="95" className="fill-slate-400 text-[10px] font-mono font-bold">
            {min}
          </text>
          <text x="110" y="95" className="fill-slate-400 text-[10px] font-mono font-bold">
            {max}
          </text>
        </svg>
      </div>

      {/* Value Display */}
      <div className="text-center -mt-3 bg-slate-900/60 rounded-lg py-2.5 px-4 border border-primary/20">
        <div className={cn("text-3xl font-bold font-mono tabular-nums", getValueColor())}>
          {value.toFixed(1)}
          <span className="text-base ml-1.5 text-slate-400">{unit}</span>
        </div>
      </div>
    </div>
  );
};
