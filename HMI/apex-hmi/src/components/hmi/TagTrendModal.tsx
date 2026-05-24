import { useState, useEffect } from "react";
import { X, TrendingUp, Calendar, Download } from "lucide-react";
import { NoDataMessage } from "./NoDataMessage";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
  Area,
  AreaChart
} from "recharts";
import { cn } from "@/lib/utils";

interface TagTrendModalProps {
  isOpen: boolean;
  onClose: () => void;
  tagId: string;
  label: string;
  unit: string;
  currentValue: number;
}

const timeRanges = [
  { label: "1H", hours: 1 },
  { label: "4H", hours: 4 },
  { label: "8H", hours: 8 },
  { label: "12H", hours: 12 },
  { label: "24H", hours: 24 },
  { label: "7D", hours: 168 },
];

interface TrendDataPoint {
  time: string;
  value: number;
  min?: number;
  max?: number;
}

export const TagTrendModal = ({ 
  isOpen, 
  onClose, 
  tagId, 
  label, 
  unit,
  currentValue 
}: TagTrendModalProps) => {
  const [selectedRange, setSelectedRange] = useState(8);
  const [chartType, setChartType] = useState<"line" | "area">("line");
  const [data, setData] = useState<TrendDataPoint[]>([]);
  const [loading, setLoading] = useState(false);

  // Fetch real tag data from backend
  useEffect(() => {
    const fetchTagData = async () => {
      if (!isOpen) return;
      
      setLoading(true);
      try {
        // Calculate time range
        const endTime = new Date();
        const startTime = new Date(endTime.getTime() - selectedRange * 60 * 60 * 1000);

        // Fetch data from backend API
        const response = await fetch(`/api/historical/${tagId}`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${localStorage.getItem('token')}`
          },
          body: JSON.stringify({
            startTime: startTime.toISOString(),
            endTime: endTime.toISOString(),
            maxPoints: 1000
          })
        });

        if (!response.ok) {
          throw new Error('Failed to fetch tag data');
        }

        const result = await response.json();
        
        // Transform API response to chart format
        const transformedData: TrendDataPoint[] = (result.data || []).map((point: any) => ({
          time: new Date(point.timestamp).toLocaleString("en-US", { 
            month: "short",
            day: "numeric",
            hour: "2-digit", 
            minute: "2-digit" 
          }),
          value: point.value || 0,
          min: point.min,
          max: point.max,
        }));

        setData(transformedData);
      } catch (error) {
        console.error('Error fetching tag data:', error);
        setData([]);
      } finally {
        setLoading(false);
      }
    };

    fetchTagData();
  }, [selectedRange, tagId, isOpen]);

  if (!isOpen) return null;

  // Calculate statistics
  const values = data.map(d => d.value);
  const avgValue = values.length > 0 ? values.reduce((a, b) => a + b, 0) / values.length : 0;
  const minValue = values.length > 0 ? Math.min(...values) : 0;
  const maxValue = values.length > 0 ? Math.max(...values) : 0;
  const stdDev = values.length > 0 ? Math.sqrt(
    values.reduce((sq, n) => sq + Math.pow(n - avgValue, 2), 0) / values.length
  ) : 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm">
      <div className="relative w-[95vw] max-w-7xl h-[90vh] bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 rounded-xl border-2 border-primary/30 shadow-2xl flex flex-col">
        
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-primary/20">
          <div className="flex items-center gap-4">
            <TrendingUp className="w-8 h-8 text-primary" />
            <div>
              <h2 className="text-2xl font-bold text-white uppercase tracking-wider">
                {label} Trend Analysis
              </h2>
              <p className="text-sm text-primary font-mono mt-1">
                Tag: {tagId} | Current: {currentValue.toFixed(2)} {unit}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg bg-red-500/20 hover:bg-red-500/30 border border-red-500/50 transition-all"
          >
            <X className="w-6 h-6 text-red-400" />
          </button>
        </div>

        {/* Controls */}
        <div className="flex items-center justify-between gap-4 p-4 bg-slate-800/50 border-b border-primary/10">
          <div className="flex items-center gap-2">
            <Calendar className="w-5 h-5 text-primary" />
            <span className="text-sm font-semibold text-white">Time Range:</span>
            <div className="flex gap-2">
              {timeRanges.map((range) => (
                <button
                  key={range.hours}
                  onClick={() => setSelectedRange(range.hours)}
                  className={cn(
                    "px-4 py-2 text-sm font-bold rounded-md transition-all duration-200 border",
                    selectedRange === range.hours
                      ? "bg-primary text-white border-primary shadow-lg shadow-primary/50"
                      : "bg-slate-700 text-slate-300 border-slate-600 hover:bg-slate-600"
                  )}
                >
                  {range.label}
                </button>
              ))}
            </div>
          </div>

          <div className="flex items-center gap-3">
            <span className="text-sm font-semibold text-white">Chart Type:</span>
            <div className="flex gap-2">
              <button
                onClick={() => setChartType("line")}
                className={cn(
                  "px-4 py-2 text-sm font-bold rounded-md transition-all border",
                  chartType === "line"
                    ? "bg-primary text-white border-primary"
                    : "bg-slate-700 text-slate-300 border-slate-600 hover:bg-slate-600"
                )}
              >
                Line
              </button>
              <button
                onClick={() => setChartType("area")}
                className={cn(
                  "px-4 py-2 text-sm font-bold rounded-md transition-all border",
                  chartType === "area"
                    ? "bg-primary text-white border-primary"
                    : "bg-slate-700 text-slate-300 border-slate-600 hover:bg-slate-600"
                )}
              >
                Area
              </button>
            </div>
            <button className="px-4 py-2 text-sm font-bold rounded-md bg-green-600 hover:bg-green-700 text-white border border-green-500 flex items-center gap-2">
              <Download className="w-4 h-4" />
              Export
            </button>
          </div>
        </div>

        {/* Statistics Cards */}
        <div className="grid grid-cols-5 gap-4 p-4 bg-slate-950/40">
          <div className="bg-slate-800/60 rounded-lg p-3 border border-green-500/30">
            <div className="text-xs text-slate-400 uppercase font-semibold mb-1">Current</div>
            <div className="text-2xl font-bold text-green-400 font-mono">
              {currentValue.toFixed(2)} <span className="text-sm text-slate-400">{unit}</span>
            </div>
          </div>
          <div className="bg-slate-800/60 rounded-lg p-3 border border-blue-500/30">
            <div className="text-xs text-slate-400 uppercase font-semibold mb-1">Average</div>
            <div className="text-2xl font-bold text-blue-400 font-mono">
              {avgValue.toFixed(2)} <span className="text-sm text-slate-400">{unit}</span>
            </div>
          </div>
          <div className="bg-slate-800/60 rounded-lg p-3 border border-red-500/30">
            <div className="text-xs text-slate-400 uppercase font-semibold mb-1">Maximum</div>
            <div className="text-2xl font-bold text-red-400 font-mono">
              {maxValue.toFixed(2)} <span className="text-sm text-slate-400">{unit}</span>
            </div>
          </div>
          <div className="bg-slate-800/60 rounded-lg p-3 border border-cyan-500/30">
            <div className="text-xs text-slate-400 uppercase font-semibold mb-1">Minimum</div>
            <div className="text-2xl font-bold text-cyan-400 font-mono">
              {minValue.toFixed(2)} <span className="text-sm text-slate-400">{unit}</span>
            </div>
          </div>
          <div className="bg-slate-800/60 rounded-lg p-3 border border-purple-500/30">
            <div className="text-xs text-slate-400 uppercase font-semibold mb-1">Std Dev</div>
            <div className="text-2xl font-bold text-purple-400 font-mono">
              {stdDev.toFixed(2)} <span className="text-sm text-slate-400">{unit}</span>
            </div>
          </div>
        </div>

        {/* Chart */}
        <div className="flex-1 p-6 overflow-hidden">
          <div className="h-full bg-slate-950/60 rounded-lg p-4 border border-primary/20">
            {loading ? (
              <NoDataMessage type="loading" height="h-full" />
            ) : data.length === 0 ? (
              <NoDataMessage 
                type="no-data" 
                height="h-full"
                subtitle={`No data found for tag ${tagId}. Try a different time range or ensure the tag is configured.`}
              />
            ) : (
              <ResponsiveContainer width="100%" height="100%">
              {chartType === "line" ? (
                <LineChart data={data} margin={{ top: 10, right: 30, left: 10, bottom: 10 }}>
                  <CartesianGrid 
                    strokeDasharray="3 3" 
                    stroke="rgba(100, 116, 139, 0.3)" 
                    vertical={false}
                  />
                  <XAxis 
                    dataKey="time" 
                    stroke="rgba(148, 163, 184, 0.8)"
                    fontSize={12}
                    tickLine={false}
                    axisLine={{ stroke: "rgba(100, 116, 139, 0.5)" }}
                    tick={{ fill: "rgba(148, 163, 184, 0.9)" }}
                  />
                  <YAxis 
                    stroke="rgba(16, 185, 129, 0.8)"
                    fontSize={12}
                    tickLine={false}
                    axisLine={{ stroke: "rgba(16, 185, 129, 0.5)" }}
                    tickFormatter={(value) => `${value} ${unit}`}
                    tick={{ fill: "rgba(16, 185, 129, 0.9)" }}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "rgb(15, 23, 42)",
                      border: "1px solid rgba(16, 185, 129, 0.5)",
                      borderRadius: "8px",
                      fontSize: "13px",
                      padding: "12px",
                      boxShadow: "0 4px 6px rgba(0, 0, 0, 0.3)"
                    }}
                    labelStyle={{ color: "rgb(226, 232, 240)", fontWeight: "bold", marginBottom: "8px" }}
                    formatter={(value: any) => [`${value} ${unit}`, label]}
                  />
                  <Legend 
                    wrapperStyle={{ fontSize: "14px", paddingTop: "15px" }}
                    formatter={() => <span className="text-slate-300 font-semibold">{label}</span>}
                  />
                  <Line
                    type="monotone"
                    dataKey="value"
                    name={label}
                    stroke="rgb(16, 185, 129)"
                    strokeWidth={3}
                    dot={{ r: 3, fill: "rgb(16, 185, 129)" }}
                    activeDot={{ r: 6, fill: "rgb(16, 185, 129)", strokeWidth: 2, stroke: "white" }}
                  />
                  <Line
                    type="monotone"
                    dataKey="max"
                    name="Max"
                    stroke="rgba(239, 68, 68, 0.4)"
                    strokeWidth={1}
                    strokeDasharray="5 5"
                    dot={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="min"
                    name="Min"
                    stroke="rgba(59, 130, 246, 0.4)"
                    strokeWidth={1}
                    strokeDasharray="5 5"
                    dot={false}
                  />
                </LineChart>
              ) : (
                <AreaChart data={data} margin={{ top: 10, right: 30, left: 10, bottom: 10 }}>
                  <defs>
                    <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="rgb(16, 185, 129)" stopOpacity={0.8}/>
                      <stop offset="95%" stopColor="rgb(16, 185, 129)" stopOpacity={0.1}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid 
                    strokeDasharray="3 3" 
                    stroke="rgba(100, 116, 139, 0.3)" 
                    vertical={false}
                  />
                  <XAxis 
                    dataKey="time" 
                    stroke="rgba(148, 163, 184, 0.8)"
                    fontSize={12}
                    tickLine={false}
                    axisLine={{ stroke: "rgba(100, 116, 139, 0.5)" }}
                    tick={{ fill: "rgba(148, 163, 184, 0.9)" }}
                  />
                  <YAxis 
                    stroke="rgba(16, 185, 129, 0.8)"
                    fontSize={12}
                    tickLine={false}
                    axisLine={{ stroke: "rgba(16, 185, 129, 0.5)" }}
                    tickFormatter={(value) => `${value} ${unit}`}
                    tick={{ fill: "rgba(16, 185, 129, 0.9)" }}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "rgb(15, 23, 42)",
                      border: "1px solid rgba(16, 185, 129, 0.5)",
                      borderRadius: "8px",
                      fontSize: "13px",
                      padding: "12px",
                      boxShadow: "0 4px 6px rgba(0, 0, 0, 0.3)"
                    }}
                    labelStyle={{ color: "rgb(226, 232, 240)", fontWeight: "bold", marginBottom: "8px" }}
                    formatter={(value: any) => [`${value} ${unit}`, label]}
                  />
                  <Area
                    type="monotone"
                    dataKey="value"
                    stroke="rgb(16, 185, 129)"
                    strokeWidth={3}
                    fillOpacity={1}
                    fill="url(#colorValue)"
                  />
                </AreaChart>
              )}
            </ResponsiveContainer>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
