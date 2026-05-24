import { useState, useEffect, useRef } from "react";
import { Activity, AlertCircle } from "lucide-react";
import { GaugeCard } from "./GaugeCard";
import { DigitalReadout } from "./DigitalReadout";
import { TrendChart, LiveTrendData } from "./TrendChart";
import { TagTrendModal } from "./TagTrendModal";
import mqttWebSocketService from "@/services/mqtt-websocket";

const LIVE_BUFFER_SIZE = 600; // 10 minutes at 1s rate

interface LiveDataPanelProps {
  equipmentId: string;
  equipmentName: string;
  selectedTags?: string[]; // Tags selected in the Asset Browser sidebar
}

interface SelectedTag {
  tagId: string;
  label: string;
  value: number;
  unit: string;
}

interface LiveDataValues {
  temperature: number | null;
  speed: number | null;
  vibration: number | null;
  pressure: number | null;
  flow: number | null;
}

export const LiveDataPanel = ({ equipmentId, equipmentName, selectedTags = [] }: LiveDataPanelProps) => {
  const [selectedTag, setSelectedTag] = useState<SelectedTag | null>(null);
  const [liveData, setLiveData] = useState<LiveDataValues>({
    temperature: null,
    speed: null,
    vibration: null,
    pressure: null,
    flow: null,
  });
  const [wsConnected, setWsConnected] = useState(false);

  // Live MQTT buffer: tagId → circular array of {time, value}
  const liveBufferRef = useRef<Record<string, { time: string; value: number }[]>>({});
  const [liveTrendData, setLiveTrendData] = useState<LiveTrendData>({ points: {}, tagLabels: {} });

  // Connect to MQTT WebSocket
  useEffect(() => {
    console.log('[LiveDataPanel] Connecting to MQTT WebSocket...');
    mqttWebSocketService.connect();
    setWsConnected(mqttWebSocketService.isConnected());

    // Subscribe to ALL tags (empty array = subscribe to everything)
    const unsubscribe = mqttWebSocketService.subscribe([], (updates) => {
      console.log('[LiveDataPanel] Received MQTT updates:', Object.keys(updates));
      setWsConnected(true);

      // Update hardcoded gauge display (legacy — maps old tag IDs if present)
      setLiveData((prev) => {
        const newData = { ...prev };
        if (updates["TT-101"]) newData.temperature = updates["TT-101"].value ?? updates["TT-101"].value_num;
        if (updates["ST-102"]) newData.speed = updates["ST-102"].value ?? updates["ST-102"].value_num;
        if (updates["VT-105"]) newData.vibration = updates["VT-105"].value ?? updates["VT-105"].value_num;
        if (updates["PT-201"]) newData.pressure = updates["PT-201"].value ?? updates["PT-201"].value_num;
        if (updates["FT-202"]) newData.flow = updates["FT-202"].value ?? updates["FT-202"].value_num;
        return newData;
      });

      // Update live buffer for trend chart
      const now = new Date().toLocaleTimeString("en-US", {
        hour: "2-digit", minute: "2-digit", second: "2-digit"
      });
      const buffer = liveBufferRef.current;
      Object.entries(updates).forEach(([tagId, tag]: [string, any]) => {
        const v = tag.value_num ?? tag.value;
        if (v === null || v === undefined || isNaN(Number(v))) return;
        if (!buffer[tagId]) buffer[tagId] = [];
        buffer[tagId].push({ time: now, value: Number(v) });
        // Keep circular buffer size
        if (buffer[tagId].length > LIVE_BUFFER_SIZE) {
          buffer[tagId] = buffer[tagId].slice(-LIVE_BUFFER_SIZE);
        }
      });

      // Build LiveTrendData for selected tags only
      if (selectedTags.length > 0) {
        const points: Record<string, { time: string; value: number }[]> = {};
        selectedTags.forEach((tagId) => {
          if (buffer[tagId] && buffer[tagId].length > 0) {
            points[tagId] = [...buffer[tagId]];
          }
        });
        setLiveTrendData({ points });
      }
    });

    return () => {
      console.log('[LiveDataPanel] Cleaning up MQTT subscription...');
      unsubscribe();
    };
  }, [equipmentId]);

  // Re-derive liveTrendData whenever selectedTags changes
  useEffect(() => {
    if (selectedTags.length === 0) {
      setLiveTrendData({ points: {} });
      return;
    }
    const buffer = liveBufferRef.current;
    const points: Record<string, { time: string; value: number }[]> = {};
    selectedTags.forEach((tagId) => {
      if (buffer[tagId] && buffer[tagId].length > 0) {
        points[tagId] = [...buffer[tagId]];
      }
    });
    setLiveTrendData({ points });
  }, [selectedTags]);

  const handleTagClick = (tagId: string, label: string, value: number | null, unit: string) => {
    if (value === null) return;
    setSelectedTag({ tagId, label, value, unit });
  };

  return (
    <div className="space-y-6">
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

      {/* Real-time Measurements */}
      <div className="bg-gradient-to-br from-slate-900/90 via-slate-800/90 to-slate-900/90 border border-primary/30 rounded-lg p-6 shadow-2xl">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <Activity className="h-5 w-5 text-primary animate-pulse" />
            <h2 className="text-base font-bold text-white uppercase tracking-wider">
              Real-Time Measurements
            </h2>
          </div>
          <div className="flex items-center gap-2 text-xs">
            {wsConnected ? (
              <>
                <div className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
                <span className="font-mono text-green-400">Live</span>
              </>
            ) : (
              <>
                <AlertCircle className="w-3 h-3 text-yellow-400" />
                <span className="font-mono text-yellow-400">Connecting...</span>
              </>
            )}
          </div>
        </div>
        
        {/* Show warning if no data available */}
        {!wsConnected && Object.values(liveData).every(v => v === null) && (
          <div className="mb-4 p-3 bg-yellow-900/20 border border-yellow-500/30 rounded-lg flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-yellow-400" />
            <span className="text-sm text-yellow-400">
              Waiting for live data from MQTT broker...
            </span>
          </div>
        )}
        
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <GaugeCard
            label="Temperature"
            tagId="TT-101"
            value={liveData.temperature ?? 0}
            unit="°C"
            min={0}
            max={120}
            warningThreshold={90}
            alarmThreshold={100}
            onTrendClick={() => liveData.temperature !== null && handleTagClick("TT-101", "Temperature", liveData.temperature, "°C")}
          />
          <GaugeCard
            label="Speed"
            tagId="ST-102"
            value={liveData.speed ?? 0}
            unit="RPM"
            min={0}
            max={1800}
            warningThreshold={1500}
            alarmThreshold={1650}
            onTrendClick={() => liveData.speed !== null && handleTagClick("ST-102", "Speed", liveData.speed, "RPM")}
          />
          <DigitalReadout
            label="Vibration"
            tagId="VT-105"
            value={liveData.vibration ?? 0}
            unit="mm/s"
            isAlarm={liveData.vibration !== null && liveData.vibration > 5.0}
            alarmMessage="High Limit Exceeded (>5.0 mm/s)"
            onTrendClick={() => liveData.vibration !== null && handleTagClick("VT-105", "Vibration", liveData.vibration, "mm/s")}
          />
          
          {/* Additional tags for eq-p201 */}
          {equipmentId === "eq-p201" && (
            <>
              <GaugeCard
                label="Pressure"
                tagId="PT-201"
                value={liveData.pressure ?? 0}
                unit="bar"
                min={0}
                max={10}
                warningThreshold={8}
                alarmThreshold={9}
                onTrendClick={() => liveData.pressure !== null && handleTagClick("PT-201", "Pressure", liveData.pressure, "bar")}
              />
              <GaugeCard
                label="Flow Rate"
                tagId="FT-202"
                value={liveData.flow ?? 0}
                unit="L/min"
                min={0}
                max={200}
                warningThreshold={180}
                alarmThreshold={190}
                onTrendClick={() => liveData.flow !== null && handleTagClick("FT-202", "Flow Rate", liveData.flow, "L/min")}
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
              Live Trends — Last 10 Minutes
            </h2>
          </div>
          {selectedTags.length === 0 && (
            <span className="text-xs text-yellow-400 font-mono px-3 py-1 bg-yellow-400/10 rounded-full border border-yellow-400/30">
              ⬅ Select tags from the Asset Browser
            </span>
          )}
        </div>
        <TrendChart
          title={`${equipmentName} — Real-time MQTT`}
          liveData={liveTrendData}
          mode="live"
        />
      </div>
    </div>
  );
};
