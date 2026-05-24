import { useState } from "react";
import { Download, ZoomIn, TrendingUp, Activity } from "lucide-react";
import { Button } from "@/components/ui/button";
import { TimeFilterBar, TimeFilter } from "./TimeFilterBar";
import { TagTrendModal } from "./TagTrendModal";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import { cn } from "@/lib/utils";

interface HistoricalDataPanelProps {
  equipmentId: string;
  equipmentName: string;
}

interface SelectedTag {
  tagId: string;
  label: string;
  value: number;
  unit: string;
}

interface TagInfo {
  id: string;
  label: string;
  dataKey: string;
  unit: string;
  color: string;
  yAxisId: string;
  currentValue: number;
}

// Generate sample historical data based on time range
const generateHistoricalData = (minutes: number) => {
  const data = [];
  const now = new Date();
  const interval = Math.max(1, Math.floor(minutes / 50)); // Max 50 data points

  for (let i = minutes; i >= 0; i -= interval) {
    const timestamp = new Date(now.getTime() - i * 60 * 1000);
    data.push({
      time: timestamp.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" }),
      temperature: 80 + Math.sin(i / 10) * 8 + Math.random() * 3,
      speed: 1150 + Math.sin(i / 8) * 40 + Math.random() * 20,
      vibration: 4 + Math.abs(Math.sin(i / 5)) * 3 + Math.random() * 1,
    });
  }

  return data;
};

export const HistoricalDataPanel = ({ equipmentId, equipmentName }: HistoricalDataPanelProps) => {
  const [timeFilter, setTimeFilter] = useState<TimeFilter>({ type: "quick", value: 60 });
  const [historicalData, setHistoricalData] = useState(() => generateHistoricalData(60));
  const [selectedTag, setSelectedTag] = useState<SelectedTag | null>(null);
  const [selectedTags, setSelectedTags] = useState<string[]>([]); // Track multiple selected tags (max 5)

  // Define available tags for this equipment
  const availableTags: TagInfo[] = [
    {
      id: "TT-101",
      label: "TEMPERATURE",
      dataKey: "temperature",
      unit: "°C",
      color: "#ef4444",
      yAxisId: "left",
      currentValue: historicalData[historicalData.length - 1]?.temperature || 0,
    },
    {
      id: "ST-102",
      label: "SPEED",
      dataKey: "speed",
      unit: "RPM",
      color: "#3b82f6",
      yAxisId: "left",
      currentValue: historicalData[historicalData.length - 1]?.speed || 0,
    },
    {
      id: "VT-105",
      label: "VIBRATION",
      dataKey: "vibration",
      unit: "mm/s",
      color: "#f59e0b",
      yAxisId: "right",
      currentValue: historicalData[historicalData.length - 1]?.vibration || 0,
    },
  ];

  // Toggle tag selection (max 5 tags)
  const handleTagToggle = (tagId: string) => {
    if (selectedTags.includes(tagId)) {
      // Deselect
      setSelectedTags(prev => prev.filter(id => id !== tagId));
    } else {
      // Select (max 5)
      if (selectedTags.length >= 5) {
        alert('Maximum 5 tags allowed. Please deselect a tag first.');
        return;
      }
      setSelectedTags(prev => [...prev, tagId]);
    }
  };

  const handleTagClick = (tag: TagInfo) => {
    setSelectedTag({
      tagId: tag.id,
      label: tag.label,
      value: tag.currentValue,
      unit: tag.unit,
    });
  };

  const handleFilterChange = (filter: TimeFilter) => {
    setTimeFilter(filter);
    
    // Generate data based on filter
    if (filter.type === "quick" && filter.value) {
      setHistoricalData(generateHistoricalData(filter.value));
    } else if (filter.type === "custom" && filter.startDate && filter.endDate) {
      const minutes = Math.floor((filter.endDate.getTime() - filter.startDate.getTime()) / 60000);
      setHistoricalData(generateHistoricalData(Math.min(minutes, 1440))); // Max 24 hours
    }
  };

  const handleExportData = () => {
    const csv = [
      ["Time", "Temperature (°C)", "Speed (RPM)", "Vibration (mm/s)"],
      ...historicalData.map((row) => [
        row.time,
        row.temperature.toFixed(2),
        row.speed.toFixed(0),
        row.vibration.toFixed(2),
      ]),
    ]
      .map((row) => row.join(","))
      .join("\n");

    const blob = new Blob([csv], { type: "text/csv" });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${equipmentId}_historical_data.csv`;
    a.click();
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

      {/* Time Filter */}
      <div className="bg-gradient-to-br from-slate-900/90 via-slate-800/90 to-slate-900/90 border border-primary/30 rounded-lg p-4 shadow-2xl">
        <TimeFilterBar onFilterChange={handleFilterChange} selectedFilter={timeFilter} />
      </div>

      {/* Tag Selection Cards - UPDATED with single-click selection */}
      <div className="bg-gradient-to-br from-slate-900/90 via-slate-800/90 to-slate-900/90 border border-primary/30 rounded-lg p-6 shadow-2xl">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <Activity className="h-5 w-5 text-primary" />
            <h2 className="text-base font-bold text-white uppercase tracking-wider">
              Individual Tag Analysis
            </h2>
          </div>
          <span className="text-xs text-slate-400 font-mono">
            Click to select (max 5) • Selected: {selectedTags.length}/5
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {availableTags.map((tag) => {
            const isSelected = selectedTags.includes(tag.id);
            return (
              <button
                key={tag.id}
                onClick={() => handleTagToggle(tag.id)}
                onDoubleClick={() => handleTagClick(tag)}
                className={cn(
                  "relative rounded-lg border-2 p-5 shadow-xl transition-all duration-300 cursor-pointer group",
                  isSelected 
                    ? "bg-gradient-to-br from-primary/30 via-primary/20 to-primary/30 border-primary scale-105 shadow-2xl shadow-primary/30" 
                    : "bg-gradient-to-br from-slate-800/50 via-slate-700/50 to-slate-800/50 border-primary/30 hover:border-primary/50 hover:scale-105"
                )}
              >
                {/* Selection Indicator */}
                {isSelected && (
                  <div className="absolute top-3 left-3 p-1.5 bg-primary rounded-full border-2 border-white">
                    <svg className="w-3 h-3 text-white" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                    </svg>
                  </div>
                )}

                {/* Trend Icon */}
                <div className="absolute top-3 right-3 p-2 bg-primary/20 rounded-lg border border-primary/40 transition-all opacity-0 group-hover:opacity-100">
                  <TrendingUp className="w-4 h-4 text-primary" />
                </div>

                <div className="flex flex-col items-center gap-3">
                  <div className="text-center">
                    <h3 className="text-sm font-bold text-white uppercase tracking-wider">{tag.label}</h3>
                    <p className="text-xs text-primary font-mono mt-0.5 bg-primary/10 inline-block px-2 py-0.5 rounded">{tag.id}</p>
                  </div>

                  <div className="w-full bg-slate-900/60 rounded-lg py-4 px-3 border border-primary/20">
                    <div className="text-4xl font-bold font-mono tabular-nums" style={{ color: tag.color }}>
                      {tag.currentValue.toFixed(1)}
                      <span className="text-lg ml-2 text-slate-400">{tag.unit}</span>
                    </div>
                  </div>

                  <div className="text-xs text-slate-400 font-semibold">
                    {isSelected ? "✓ Selected" : "Click to select"} • Double-click for details
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Data Summary */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-gradient-to-br from-slate-800/60 via-slate-700/60 to-slate-800/60 border border-primary/30 rounded-lg p-4 shadow-lg">
          <div className="text-xs text-slate-400 uppercase font-semibold mb-1">Data Points</div>
          <div className="text-2xl font-bold text-white">{historicalData.length}</div>
        </div>
        <div className="bg-gradient-to-br from-slate-800/60 via-slate-700/60 to-slate-800/60 border border-primary/30 rounded-lg p-4 shadow-lg">
          <div className="text-xs text-slate-400 uppercase font-semibold mb-1">Time Range</div>
          <div className="text-lg font-semibold text-white">
            {timeFilter.type === "quick" ? `${timeFilter.value} min` : "Custom"}
          </div>
        </div>
        <div className="bg-gradient-to-br from-slate-800/60 via-slate-700/60 to-slate-800/60 border border-red-500/30 rounded-lg p-4 shadow-lg">
          <div className="text-xs text-slate-400 uppercase font-semibold mb-1">Avg Temperature</div>
          <div className="text-2xl font-bold text-red-400">
            {(historicalData.reduce((sum, d) => sum + d.temperature, 0) / historicalData.length).toFixed(1)}°C
          </div>
        </div>
        <div className="bg-gradient-to-br from-slate-800/60 via-slate-700/60 to-slate-800/60 border border-orange-500/30 rounded-lg p-4 shadow-lg">
          <div className="text-xs text-slate-400 uppercase font-semibold mb-1">Max Vibration</div>
          <div className="text-2xl font-bold text-orange-400">
            {Math.max(...historicalData.map((d) => d.vibration)).toFixed(2)} mm/s
          </div>
        </div>
      </div>

      {/* Historical Trend Chart */}
      <div className="bg-gradient-to-br from-slate-900/90 via-slate-800/90 to-slate-900/90 border border-primary/30 rounded-lg p-6 shadow-2xl">
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-base font-bold text-white uppercase tracking-wider">{equipmentName} - Historical Trends</h3>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" className="gap-2 border-primary/50 text-primary hover:bg-primary/20">
              <ZoomIn className="h-4 w-4" />
              Zoom
            </Button>
            <Button variant="outline" size="sm" className="gap-2 border-green-500/50 text-green-400 hover:bg-green-500/20" onClick={handleExportData}>
              <Download className="h-4 w-4" />
              Export CSV
            </Button>
          </div>
        </div>

        <div className="bg-slate-950/60 rounded-lg p-4 border border-primary/20">
          <ResponsiveContainer width="100%" height={400}>
            <LineChart data={historicalData}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(100, 116, 139, 0.3)" vertical={false} />
              <XAxis
                dataKey="time"
                fontSize={11}
                tick={{ fill: "rgba(148, 163, 184, 0.9)" }}
                tickLine={false}
                axisLine={{ stroke: "rgba(100, 116, 139, 0.5)" }}
              />
              <YAxis
                yAxisId="left"
                fontSize={11}
                tick={{ fill: "rgba(239, 68, 68, 0.9)" }}
                tickLine={false}
                axisLine={{ stroke: "rgba(239, 68, 68, 0.5)" }}
                label={{ value: "Temperature (°C) / Speed (RPM / 10)", angle: -90, position: "insideLeft", style: { fill: "rgba(148, 163, 184, 0.9)" } }}
              />
              <YAxis
                yAxisId="right"
                orientation="right"
                fontSize={11}
                tick={{ fill: "rgba(245, 158, 11, 0.9)" }}
                tickLine={false}
                axisLine={{ stroke: "rgba(245, 158, 11, 0.5)" }}
                label={{ value: "Vibration (mm/s)", angle: 90, position: "insideRight", style: { fill: "rgba(148, 163, 184, 0.9)" } }}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "rgb(15, 23, 42)",
                  border: "1px solid rgba(59, 130, 246, 0.5)",
                  borderRadius: "8px",
                  fontSize: "12px",
                  padding: "10px",
                  boxShadow: "0 4px 6px rgba(0, 0, 0, 0.3)"
                }}
                labelStyle={{ color: "rgb(226, 232, 240)", fontWeight: "bold" }}
                itemStyle={{ color: "rgb(203, 213, 225)" }}
              />
              <Legend 
                wrapperStyle={{ fontSize: "13px", paddingTop: "15px" }}
                formatter={(value) => <span className="text-slate-300 font-semibold">{value}</span>}
              />
              <Line
                yAxisId="left"
                type="monotone"
                dataKey="temperature"
                stroke="#ef4444"
                name="Temperature (°C)"
                strokeWidth={3}
                dot={false}
                activeDot={{ r: 5, fill: "#ef4444", strokeWidth: 2, stroke: "white" }}
              />
              <Line
                yAxisId="left"
                type="monotone"
                dataKey="speed"
                stroke="#3b82f6"
                name="Speed (RPM / 10)"
                strokeWidth={3}
                dot={false}
                activeDot={{ r: 5, fill: "#3b82f6", strokeWidth: 2, stroke: "white" }}
              />
              <Line
                yAxisId="right"
                type="monotone"
                dataKey="vibration"
                stroke="#f59e0b"
                name="Vibration (mm/s)"
                strokeWidth={3}
                dot={false}
                activeDot={{ r: 5, fill: "#f59e0b", strokeWidth: 2, stroke: "white" }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
};
