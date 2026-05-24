import { Cog, AlertTriangle, CheckCircle2, Clock } from "lucide-react";
import { cn } from "@/lib/utils";

interface EquipmentHeaderProps {
  name: string;
  tagId: string;
  status: "running" | "stopped" | "alarm" | "maintenance";
  hasAlarm?: boolean;
  lastUpdate?: string;
}

const statusConfig = {
  running: {
    label: "RUNNING",
    color: "text-status-running",
    bgColor: "bg-status-running/10",
    icon: CheckCircle2
  },
  stopped: {
    label: "STOPPED",
    color: "text-muted-foreground",
    bgColor: "bg-muted",
    icon: Cog
  },
  alarm: {
    label: "ALARM",
    color: "text-status-alarm",
    bgColor: "bg-status-alarm/10",
    icon: AlertTriangle
  },
  maintenance: {
    label: "MAINTENANCE",
    color: "text-status-warning",
    bgColor: "bg-status-warning/10",
    icon: Cog
  }
};

export const EquipmentHeader = ({
  name,
  tagId,
  status,
  hasAlarm = false,
  lastUpdate = "Just now"
}: EquipmentHeaderProps) => {
  const config = statusConfig[status];
  const StatusIcon = config.icon;

  return (
    <div className="hmi-panel">
      <div className="hmi-panel-header">
        <div className="flex items-center gap-4">
          <div className={cn(
            "w-12 h-12 rounded-lg flex items-center justify-center",
            hasAlarm ? "bg-status-alarm/20" : "bg-primary/20"
          )}>
            <Cog className={cn(
              "w-6 h-6",
              hasAlarm ? "text-status-alarm" : "text-primary"
            )} />
          </div>
          
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-xl font-semibold text-foreground">{name}</h1>
              {hasAlarm && (
                <AlertTriangle className="w-5 h-5 text-status-alarm animate-pulse" />
              )}
            </div>
            <p className="text-sm text-muted-foreground font-mono">{tagId}</p>
          </div>
        </div>

        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Clock className="w-4 h-4" />
            <span>Updated: {lastUpdate}</span>
          </div>
          
          <div className={cn(
            "flex items-center gap-2 px-4 py-2 rounded-md font-medium text-sm",
            config.bgColor,
            config.color
          )}>
            <StatusIcon className="w-4 h-4" />
            <span>{config.label}</span>
          </div>
        </div>
      </div>
    </div>
  );
};
