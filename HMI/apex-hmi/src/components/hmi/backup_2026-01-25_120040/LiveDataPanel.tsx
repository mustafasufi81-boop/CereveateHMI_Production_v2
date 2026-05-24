import { useState } from "react";
import { Activity } from "lucide-react";
import { GaugeCard } from "./GaugeCard";
import { DigitalReadout } from "./DigitalReadout";
import { TrendChart } from "./TrendChart";
import { TagTrendModal } from "./TagTrendModal";

interface LiveDataPanelProps {
  equipmentId: string;
  equipmentName: string;
}

interface SelectedTag {
  tagId: string;
  label: string;
  value: number;
  unit: string;
}

export const LiveDataPanel = ({ equipmentId, equipmentName }: LiveDataPanelProps) => {
  const [selectedTag, setSelectedTag] = useState<SelectedTag | null>(null);

  // This would normally come from WebSocket/real-time API
  const liveData = {
    temperature: 85.2,
    speed: 1200,
    vibration: 8.2,
    pressure: 4.5,
    flow: 165,
  };

  const handleTagClick = (tagId: string, label: string, value: number, unit: string) => {
    setSelectedTag({ tagId, label, value, unit });
  };

  return (
    <div className="space-y-4">
      {/* Tag Trend Modal */}
      {selectedTag && (
        <TagTrendModal
          isOpen={true}
          onClose={() => setSelectedTag(null)}
          tagId={selectedTag.tagId}
          label={selectedTag.label}
          unit={selectedTag.unit}
          currentValue={selectedTag.value}
        />
      )}

      {/* Real-Time Measurements Section */}
      <div className="bg-gradient-to-br from-slate-900/90 via-slate-800/90 to-slate-900/90 border border-primary/30 rounded-lg p-6 shadow-2xl">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <Activity className="h-5 w-5 text-primary animate-pulse" />
            <h2 className="text-base font-bold text-white uppercase tracking-wider">
              Real-Time Measurements
            </h2>
          </div>
          <div className="flex items-center gap-2 text-xs text-green-400">
            <div className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
            <span className="font-mono">Live</span>
          </div>
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <GaugeCard
            label="Temperature"
            tagId="TT-101"
            value={liveData.temperature}
            unit="°C"
            min={0}
            max={120}
            warningThreshold={90}
            alarmThreshold={100}
            onTrendClick={() => handleTagClick("TT-101", "Temperature", liveData.temperature, "°C")}
          />
          <GaugeCard
            label="Speed"
            tagId="ST-102"
            value={liveData.speed}
            unit="RPM"
            min={0}
            max={1800}
            warningThreshold={1500}
            alarmThreshold={1650}
            onTrendClick={() => handleTagClick("ST-102", "Speed", liveData.speed, "RPM")}
          />
          <DigitalReadout
            label="Vibration"
            tagId="VT-105"
            value={liveData.vibration}
            unit="mm/s"
            isAlarm={true}
            alarmMessage="High Limit Exceeded (>5.0 mm/s)"
            onTrendClick={() => handleTagClick("VT-105", "Vibration", liveData.vibration, "mm/s")}
          />
          {equipmentId === "eq-p201" && (
            <>
              <GaugeCard
                label="Pressure"
                tagId="PT-201"
                value={liveData.pressure}
                unit="bar"
                min={0}
                max={10}
                warningThreshold={8}
                alarmThreshold={9}
                onTrendClick={() => handleTagClick("PT-201", "Pressure", liveData.pressure, "bar")}
              />
              <GaugeCard
                label="Flow Rate"
                tagId="FT-202"
                value={liveData.flow}
                unit="L/min"
                min={0}
                max={200}
                warningThreshold={180}
                alarmThreshold={190}
                onTrendClick={() => handleTagClick("FT-202", "Flow Rate", liveData.flow, "L/min")}
              />
            </>
          )}
        </div>
      </div>

      {/* Live Trends Section */}
      <div className="bg-gradient-to-br from-slate-900/90 via-slate-800/90 to-slate-900/90 border border-primary/30 rounded-lg p-6 shadow-2xl">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <Activity className="h-5 w-5 text-primary" />
            <h2 className="text-base font-bold text-white uppercase tracking-wider">
              Live Trends - Last 10 Minutes
            </h2>
          </div>
          <div className="flex items-center gap-4">
            <span className="text-xs text-muted-foreground font-mono px-3 py-1 bg-slate-700/50 rounded-full border border-primary/20">
              Auto-refresh: 5s
            </span>
          </div>
        </div>
        <TrendChart title={`${equipmentName} - Real-time Performance`} />
      </div>
    </div>
  );
};
