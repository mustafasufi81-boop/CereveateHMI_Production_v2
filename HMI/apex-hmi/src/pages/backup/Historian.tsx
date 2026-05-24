/**
 * Industrial Historian - ISA-101 Compliant Trend Visualization
 * 
 * ISA-101 Standards Applied:
 * ✅ Dark Background (#1a1a1a) - Reduces eye strain for 24/7 operations
 * ✅ Bright Green Trend Line (#00FF00) - High contrast, industry standard (PEN 1)
 * ✅ Line Thickness 2.5px - ISA-101 recommended 2-3px for clarity
 * ✅ Time Format HH:mm:ss - Standard for live/historical trending
 * ✅ Y-Axis Units Display [unit] - Critical for engineering clarity
 * ✅ Grid Lines - Major (35% opacity), Minor disabled for clean view
 * ✅ Arial Font - Industry standard, high readability
 * ✅ Blue Axis Labels (#60a5fa) - Distinct from data, easy to read
 * 
 * Compatible with: Ignition, WinCC, Wonderware, FactoryTalk
 */

import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, Calendar, Download, Search, Filter, Database, Clock, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
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
import { UserHeader } from "@/components/hmi/UserHeader";

const API_BASE_URL = "";

const presetRanges = [
  { label: "1 Hr", hours: 1 },
  { label: "8 Hr", hours: 8 },
  { label: "24 Hr", hours: 24 },
  { label: "7 Days", hours: 168 },
  { label: "30 Days", hours: 720 },
];

interface Tag {
  id: string;
  name: string;
  unit: string;
  equipment: string;
}

interface HistoricalDataPoint {
  timestamp: Date;
  value: number;
}

const Historian = () => {
  const [tags, setTags] = useState<Tag[]>([]);
  const [selectedTag, setSelectedTag] = useState<string>("");
  const [selectedRange, setSelectedRange] = useState(24);
  const [customStart, setCustomStart] = useState("");
  const [customEnd, setCustomEnd] = useState("");
  const [historicalData, setHistoricalData] = useState<HistoricalDataPoint[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingTags, setLoadingTags] = useState(true);
  const [error, setError] = useState<string>("");
  const [showMilliseconds, setShowMilliseconds] = useState(false);

  const endDate = customEnd ? new Date(customEnd) : new Date();
  const startDate = customStart 
    ? new Date(customStart)
    : new Date(endDate.getTime() - selectedRange * 60 * 60 * 1000);

  const selectedTagInfo = tags.find((t) => t.id === selectedTag);

  // Fetch available tags from database
  useEffect(() => {
    const fetchTags = async () => {
      try {
        setLoadingTags(true);
        // Try new endpoint first
        let response = await fetch(`${API_BASE_URL}/api/historian/tags`);
        
        // Fallback to old endpoint if new one doesn't exist
        if (!response.ok) {
          console.log("New endpoint not found, trying /api/tags");
          response = await fetch(`${API_BASE_URL}/api/tags`);
        }
        
        const result = await response.json();
        
        if (result.success && result.tags && result.tags.length > 0) {
          // Map the tags to ensure consistent format
          const mappedTags = result.tags.map((tag: any) => ({
            id: tag.id || tag,
            name: tag.name || tag.id || tag,
            unit: tag.unit || '',
            equipment: tag.equipment || tag.description || 'Process Variable'
          }));
          setTags(mappedTags);
          setSelectedTag(mappedTags[0].id);
        } else {
          setError("No tags found in database");
        }
      } catch (err) {
        console.error("Error fetching tags:", err);
        setError("Failed to load tags from database");
      } finally {
        setLoadingTags(false);
      }
    };

    fetchTags();
  }, []);

  // Fetch data from database
  const fetchHistorianData = async () => {
    if (!selectedTag) return;
    
    setLoading(true);
    setError("");
    
    try {
      const url = `${API_BASE_URL}/api/historian/historical?` +
        `start_date=${startDate.toISOString()}&` +
        `end_date=${endDate.toISOString()}&` +
        `tags=["${selectedTag}"]&` +
        `max_points=5000`;
      
      console.log("Fetching data from:", url);
      const response = await fetch(url);
      const result = await response.json();
      
      console.log("API Response:", result);
      
      if (result.success && result.data && result.data.length > 0) {
        // Convert data format
        const formattedData = result.data
          .map((row: any) => ({
            timestamp: new Date(row.Timestamp),
            value: parseFloat(row[selectedTag])
          }))
          .filter((row: any) => !isNaN(row.value) && row.value !== null);
        
        console.log(`Formatted ${formattedData.length} data points`);
        setHistoricalData(formattedData);
        
        if (formattedData.length === 0) {
          setError("No data found for selected time range");
        }
      } else {
        setError(result.error || "No data available for selected time range");
        setHistoricalData([]);
      }
    } catch (err) {
      console.error("Error fetching historian data:", err);
      setError("Failed to fetch data from server");
      setHistoricalData([]);
    } finally {
      setLoading(false);
    }
  };

  // Auto-load data when tag or range changes
  useEffect(() => {
    if (selectedTag && !loadingTags) {
      fetchHistorianData();
    }
  }, [selectedTag, selectedRange]);

  const handleExport = () => {
    const csvContent = [
      ["Timestamp", "Value", "Unit"],
      ...historicalData.map((d) => [
        d.timestamp.toISOString(),
        d.value,
        selectedTagInfo?.unit || "",
      ]),
    ]
      .map((row) => row.join(","))
      .join("\n");

    const blob = new Blob([csvContent], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${selectedTag}_${startDate.toISOString()}_${endDate.toISOString()}.csv`;
    a.click();
  };

  return (
    <div className="min-h-screen bg-slate-950 text-foreground">
      {/* Header - Industrial Design */}
      <header className="sticky top-0 z-10 bg-gradient-to-r from-slate-950 via-slate-900 to-slate-950 border-b-2 border-amber-500/30 shadow-2xl">
        <div className="px-6 py-2.5 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link to="/">
              <Button 
                variant="outline" 
                size="sm" 
                className="gap-2 border-slate-700/50 bg-slate-800/50 hover:bg-slate-700/70 hover:border-slate-600 font-bold"
              >
                <ArrowLeft className="h-4 w-4" />
                BACK
              </Button>
            </Link>
            <div className="h-8 w-px bg-amber-500/40" />
            <div className="flex items-center gap-3">
              <div className="relative">
                <div className="w-2.5 h-2.5 rounded-full bg-blue-500 animate-pulse shadow-lg shadow-blue-500/50" />
                <div className="absolute inset-0 w-2.5 h-2.5 rounded-full bg-blue-500/30 animate-ping" />
              </div>
              <h1 className="text-lg font-black text-white uppercase tracking-widest">
                <span className="text-blue-400">PROCESS</span> HISTORIAN
              </h1>
            </div>
            <div className="h-8 w-px bg-amber-500/40" />
            <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-800/50 border border-slate-700/50 rounded-md">
              <Clock className="h-3.5 w-3.5 text-amber-400" />
              <span className="text-xs font-mono text-slate-300">
                {new Date().toLocaleString('en-US', { 
                  hour12: false,
                  month: 'short',
                  day: '2-digit',
                  hour: '2-digit',
                  minute: '2-digit',
                  second: '2-digit'
                })}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button 
              onClick={handleExport} 
              variant="outline" 
              size="sm" 
              className="gap-2 border-emerald-500/40 bg-emerald-950/30 text-emerald-300 hover:bg-emerald-500/20 hover:border-emerald-400 font-bold"
            >
              <Download className="h-4 w-4" />
              EXPORT CSV
            </Button>
            <div className="h-8 w-px bg-slate-700/50 mx-1" />
            <UserHeader />
          </div>
        </div>
      </header>

      <div className="p-6 space-y-6">
        {/* Filters - Vertical Layout */}
        <div className="bg-gradient-to-br from-slate-900 via-slate-900 to-slate-800 border-2 border-amber-600/30 rounded-lg shadow-2xl p-6">
          <div className="space-y-4">
            {/* Tag Selection */}
            <div className="space-y-2">
              <label className="text-xs text-amber-400 uppercase tracking-wider font-bold flex items-center gap-2">
                <Database className="h-3.5 w-3.5" />
                Process Tag
              </label>
              <Select value={selectedTag} onValueChange={setSelectedTag} disabled={loadingTags}>
                <SelectTrigger className="w-full bg-slate-800 border-slate-700 h-10">
                  <SelectValue placeholder={loadingTags ? "Loading tags..." : "Select a tag"} />
                </SelectTrigger>
                <SelectContent className="bg-slate-900 border-slate-700 max-h-80">
                  {tags.map((tag) => (
                    <SelectItem key={tag.id} value={tag.id}>
                      <div className="flex items-center gap-3">
                        <span className="font-mono text-white font-bold">{tag.id}</span>
                        <span className="text-slate-400 text-xs">
                          {tag.name} • {tag.unit}
                        </span>
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Quick Range Buttons */}
            <div className="space-y-2">
              <label className="text-xs text-amber-400 uppercase tracking-wider font-bold flex items-center gap-2">
                <Clock className="h-3.5 w-3.5" />
                Time Range
              </label>
              <div className="flex gap-2 flex-wrap">
                {presetRanges.map((range) => (
                  <Button
                    key={range.hours}
                    variant={selectedRange === range.hours ? "default" : "outline"}
                    size="sm"
                    onClick={() => {
                      setSelectedRange(range.hours);
                      setCustomStart("");
                      setCustomEnd("");
                    }}
                    className={cn(
                      "text-xs font-bold h-10",
                      selectedRange === range.hours
                        ? "bg-blue-600 border-blue-500 text-white shadow-lg"
                        : "border-slate-700/50 bg-slate-800/50 text-slate-300 hover:bg-slate-700"
                    )}
                  >
                    {range.label}
                  </Button>
                ))}
              </div>
            </div>

            {/* Custom Date Range */}
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <label className="text-xs text-slate-400 uppercase tracking-wider font-bold">
                  Custom Start
                </label>
                <Input
                  type="datetime-local"
                  value={customStart}
                  onChange={(e) => setCustomStart(e.target.value)}
                  className="w-full bg-slate-800 border-slate-700 h-10 text-sm"
                />
              </div>
              <div className="space-y-2">
                <label className="text-xs text-slate-400 uppercase tracking-wider font-bold">
                  Custom End
                </label>
                <Input
                  type="datetime-local"
                  value={customEnd}
                  onChange={(e) => setCustomEnd(e.target.value)}
                  className="w-full bg-slate-800 border-slate-700 h-10 text-sm"
                />
              </div>
            </div>

            {/* Query Button & Milliseconds Toggle */}
            <div className="flex items-center gap-4">
              <Button 
                variant="default" 
                size="default"
                className="flex-1 gap-2 bg-emerald-600 hover:bg-emerald-700 text-white font-bold h-10 shadow-lg"
                onClick={fetchHistorianData}
                disabled={loading || !selectedTag}
              >
                {loading ? (
                  <>
                    <RefreshCw className="h-4 w-4 animate-spin" />
                    Loading...
                  </>
                ) : (
                  <>
                    <Search className="h-4 w-4" />
                    Query Data
                  </>
                )}
              </Button>
              
              {/* Milliseconds Toggle - ISA-101 Option */}
              <div className="flex items-center gap-2 px-3 bg-slate-800/50 border border-slate-700 rounded-md h-10">
                <input
                  type="checkbox"
                  id="showMs"
                  checked={showMilliseconds}
                  onChange={(e) => setShowMilliseconds(e.target.checked)}
                  className="w-4 h-4 rounded border-slate-600 bg-slate-700 text-blue-600 focus:ring-2 focus:ring-blue-500"
                />
                <label htmlFor="showMs" className="text-xs text-slate-300 font-mono whitespace-nowrap cursor-pointer">
                  Show .ms
                </label>
              </div>
            </div>
          </div>

          {/* Error Message */}
          {error && (
            <div className="mt-4 p-3 bg-red-950/50 border border-red-500/50 rounded-md">
              <p className="text-sm text-red-300">⚠️ {error}</p>
            </div>
          )}

          {/* Info Bar */}
          <div className="mt-4 flex items-center justify-between text-xs text-slate-400">
            <div className="flex items-center gap-4">
              <span>
                <strong className="text-amber-400">From:</strong> {startDate.toLocaleString()}
              </span>
              <span>
                <strong className="text-amber-400">To:</strong> {endDate.toLocaleString()}
              </span>
            </div>
            <span>
              <strong className="text-amber-400">Data Points:</strong> {historicalData.length.toLocaleString()}
            </span>
          </div>
        </div>

        {/* Chart - ISA-101 Compliant */}
        <div className="border-2 border-blue-500/30 rounded-lg shadow-2xl overflow-hidden" style={{ backgroundColor: '#1a1a1a' }}>
          <div className="flex items-center justify-between px-4 py-3 border-b border-blue-500/30" style={{ backgroundColor: '#0f1419' }}>
            <div>
              <h2 className="text-sm font-bold text-blue-400 font-mono">
                {selectedTagInfo?.name || "Process Variable"} TREND
              </h2>
              <p className="text-xs text-slate-400 font-mono">
                {selectedTagInfo?.id} • {selectedTagInfo?.equipment}
              </p>
            </div>
            <div className="text-right">
              <p className="text-xs text-slate-400 font-mono">
                {startDate.toLocaleString("en-US", { hour12: false })} — {endDate.toLocaleString("en-US", { hour12: false })}
              </p>
              <p className="text-xs text-green-400 font-mono font-bold">
                {historicalData.length.toLocaleString()} DATA POINTS
              </p>
            </div>
          </div>

          <div className="p-4" style={{ backgroundColor: '#1a1a1a' }}>

          {loading ? (
            <div className="h-80 flex items-center justify-center rounded-lg border-2 border-slate-700" style={{ backgroundColor: '#121212' }}>
              <div className="text-center">
                <RefreshCw className="h-8 w-8 text-blue-500 animate-spin mx-auto mb-2" />
                <p className="text-sm text-slate-400 font-mono">LOADING HISTORIAN DATA...</p>
              </div>
            </div>
          ) : historicalData.length === 0 ? (
            <div className="h-80 flex items-center justify-center rounded-lg border-2 border-slate-700" style={{ backgroundColor: '#121212' }}>
              <div className="text-center">
                <Database className="h-12 w-12 text-slate-600 mx-auto mb-3" />
                <p className="text-sm text-slate-400 mb-1 font-mono">NO DATA AVAILABLE FOR SELECTED TIME RANGE</p>
                <p className="text-xs text-slate-500 font-mono">Try selecting a different time range or tag</p>
              </div>
            </div>
          ) : (
            <div className="h-80" style={{ backgroundColor: '#1a1a1a' }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart
                  data={historicalData}
                  margin={{ top: 10, right: 30, left: 20, bottom: 30 }}
                >
                  <CartesianGrid
                    strokeDasharray="3 3"
                    stroke="rgba(100, 116, 139, 0.35)"
                    strokeWidth={1.5}
                    vertical={false}
                  />
                  <XAxis
                    dataKey="timestamp"
                    stroke="#60a5fa"
                    fontSize={11}
                    fontFamily="Arial, sans-serif"
                    fontWeight="bold"
                    tickLine={true}
                    axisLine={{ stroke: "rgba(59, 130, 246, 0.6)", strokeWidth: 2 }}
                    height={60}
                    tickFormatter={(value) => {
                      const date = new Date(value);
                      if (selectedRange <= 24) {
                        // ISA-101: HH:mm:ss or HH:mm:ss.SSS format for short ranges
                        const timeStr = date.toLocaleTimeString("en-US", {
                          hour12: false,
                          hour: "2-digit",
                          minute: "2-digit",
                          second: "2-digit",
                        });
                        if (showMilliseconds) {
                          const ms = date.getMilliseconds().toString().padStart(3, '0');
                          return `${timeStr}.${ms}`;
                        }
                        return timeStr;
                      } else {
                        // ISA-101: MMM DD, HH:mm for longer ranges
                        return date.toLocaleDateString("en-US", {
                          month: "short",
                          day: "numeric",
                        }) + ", " + date.toLocaleTimeString("en-US", {
                          hour12: false,
                          hour: "2-digit",
                          minute: "2-digit",
                        });
                      }
                    }}
                    interval="preserveStartEnd"
                    minTickGap={60}
                    tick={{ fill: "#60a5fa", fontSize: 11 }}
                    angle={0}
                    dy={10}
                  />
                  <YAxis
                    stroke="#60a5fa"
                    fontSize={11}
                    fontFamily="Arial, sans-serif"
                    fontWeight="bold"
                    tickLine={false}
                    axisLine={{ stroke: "rgba(59, 130, 246, 0.6)", strokeWidth: 2 }}
                    tickFormatter={(value) => {
                      // Format numbers properly
                      if (value >= 1000) {
                        return `${(value / 1000).toFixed(1)}k`;
                      }
                      return value.toFixed(1);
                    }}
                    width={70}
                    domain={['auto', 'auto']}
                    tick={{ fill: "#60a5fa" }}
                    label={{ 
                      value: `[${selectedTagInfo?.unit || ''}]`, 
                      angle: -90, 
                      position: 'insideLeft',
                      style: { 
                        fill: '#00FF00', 
                        fontWeight: 'bold', 
                        fontSize: 13,
                        fontFamily: 'Arial, sans-serif'
                      } 
                    }}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#1a1a1a",
                      border: "2px solid rgba(59, 130, 246, 0.6)",
                      borderRadius: "4px",
                      fontSize: "12px",
                      fontFamily: "Arial, sans-serif",
                      padding: "8px 12px",
                    }}
                    labelStyle={{ color: "#60a5fa", fontWeight: "bold" }}
                    labelFormatter={(value) => {
                      const date = new Date(value);
                      const timeStr = date.toLocaleString("en-US", {
                        hour12: false,
                        month: "short",
                        day: "numeric",
                        hour: "2-digit",
                        minute: "2-digit",
                        second: "2-digit",
                      });
                      if (showMilliseconds) {
                        const ms = date.getMilliseconds().toString().padStart(3, '0');
                        return `${timeStr}.${ms}`;
                      }
                      return timeStr;
                    }}
                    formatter={(value: number) => [
                      `${value.toFixed(2)} ${selectedTagInfo?.unit || ''}`,
                      selectedTagInfo?.name || 'Value',
                    ]}
                  />
                  <Legend 
                    wrapperStyle={{ 
                      fontSize: "12px",
                      fontFamily: "Arial, sans-serif",
                      fontWeight: "bold"
                    }} 
                  />
                  <Line
                    type="monotone"
                    dataKey="value"
                    name={`${selectedTagInfo?.name || 'Value'} [${selectedTagInfo?.unit || ''}]`}
                    stroke="#00FF00"
                    strokeWidth={2.5}
                    dot={false}
                    activeDot={{ 
                      r: 5, 
                      fill: "#00FF00",
                      stroke: "#1a1a1a",
                      strokeWidth: 2
                    }}
                    connectNulls
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
          </div>
        </div>

        {/* Data Table */}
        <div className="hmi-panel p-4">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-medium">Raw Data</h2>
            <div className="flex items-center gap-2">
              <Filter className="h-4 w-4 text-muted-foreground" />
              <span className="text-xs text-muted-foreground">
                Showing {historicalData.length} records
              </span>
            </div>
          </div>

          <div className="max-h-80 overflow-auto rounded border border-border">
            <Table>
              <TableHeader className="sticky top-0 bg-card">
                <TableRow>
                  <TableHead className="font-mono text-xs">Timestamp</TableHead>
                  <TableHead className="font-mono text-xs">Value</TableHead>
                  <TableHead className="font-mono text-xs">Unit</TableHead>
                  <TableHead className="font-mono text-xs">Quality</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {historicalData.slice(0, 50).map((row, index) => (
                  <TableRow key={index}>
                    <TableCell className="font-mono text-xs">
                      {row.timestamp.toLocaleString()}
                    </TableCell>
                    <TableCell className="font-mono text-xs font-medium">
                      {row.value}
                    </TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      {selectedTagInfo?.unit}
                    </TableCell>
                    <TableCell>
                      <span className="inline-flex items-center gap-1 text-xs">
                        <span className="h-2 w-2 rounded-full bg-status-running" />
                        Good
                      </span>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          {historicalData.length > 50 && (
            <p className="text-xs text-muted-foreground mt-2 text-center">
              Showing first 50 of {historicalData.length} records. Export to see all data.
            </p>
          )}
        </div>
      </div>
    </div>
  );
};

export default Historian;
