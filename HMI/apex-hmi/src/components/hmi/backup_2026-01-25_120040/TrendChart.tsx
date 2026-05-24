import { useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend
} from "recharts";
import { cn } from "@/lib/utils";

interface TrendChartProps {
  title: string;
}

const timeRanges = [
  { label: "1h", hours: 1 },
  { label: "4h", hours: 4 },
  { label: "8h", hours: 8 },
  { label: "24h", hours: 24 }
];

// Generate mock historical data
const generateData = (hours: number) => {
  const data = [];
  const now = new Date();
  const pointsPerHour = hours <= 4 ? 12 : hours <= 8 ? 6 : 2;
  const totalPoints = hours * pointsPerHour;

  for (let i = totalPoints; i >= 0; i--) {
    const time = new Date(now.getTime() - (i * (60 / pointsPerHour) * 60 * 1000));
    const baseTemp = 82 + Math.sin(i / 10) * 5;
    const baseSpeed = 1180 + Math.cos(i / 8) * 40;
    
    data.push({
      time: time.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" }),
      temperature: Math.round((baseTemp + Math.random() * 4) * 10) / 10,
      speed: Math.round(baseSpeed + Math.random() * 30)
    });
  }
  return data;
};

export const TrendChart = ({ title }: TrendChartProps) => {
  const [selectedRange, setSelectedRange] = useState(8);
  const data = generateData(selectedRange);

  return (
    <div className="bg-slate-950/60 rounded-lg p-4 border border-primary/20">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-bold text-white uppercase tracking-wider">{title}</h3>
        <div className="flex gap-2">
          {timeRanges.map((range) => (
            <button
              key={range.hours}
              onClick={() => setSelectedRange(range.hours)}
              className={cn(
                "px-4 py-1.5 text-xs font-bold rounded-md transition-all duration-200 border",
                selectedRange === range.hours
                  ? "bg-primary text-white border-primary shadow-lg shadow-primary/50"
                  : "bg-slate-800 text-slate-400 border-slate-700 hover:bg-slate-700 hover:border-primary/50"
              )}
            >
              {range.label}
            </button>
          ))}
        </div>
      </div>

      <div className="h-72 bg-slate-900/40 rounded-lg p-3 border border-primary/10">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 5, right: 30, left: 0, bottom: 5 }}>
            <CartesianGrid 
              strokeDasharray="3 3" 
              stroke="rgba(100, 116, 139, 0.3)" 
              vertical={false}
            />
            <XAxis 
              dataKey="time" 
              stroke="rgba(148, 163, 184, 0.8)"
              fontSize={11}
              tickLine={false}
              axisLine={{ stroke: "rgba(100, 116, 139, 0.5)" }}
              interval="preserveStartEnd"
              tick={{ fill: "rgba(148, 163, 184, 0.9)" }}
            />
            <YAxis 
              yAxisId="temp"
              stroke="rgba(16, 185, 129, 0.8)"
              fontSize={11}
              tickLine={false}
              axisLine={{ stroke: "rgba(16, 185, 129, 0.5)" }}
              domain={[70, 100]}
              tickFormatter={(value) => `${value}°C`}
              tick={{ fill: "rgba(16, 185, 129, 0.9)" }}
            />
            <YAxis 
              yAxisId="speed"
              orientation="right"
              stroke="rgba(59, 130, 246, 0.8)"
              fontSize={11}
              tickLine={false}
              axisLine={{ stroke: "rgba(59, 130, 246, 0.5)" }}
              domain={[1000, 1400]}
              tickFormatter={(value) => `${value}`}
              tick={{ fill: "rgba(59, 130, 246, 0.9)" }}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "rgb(15, 23, 42)",
                border: "1px solid rgba(59, 130, 246, 0.5)",
                borderRadius: "8px",
                fontSize: "12px",
                padding: "8px 12px",
                boxShadow: "0 4px 6px rgba(0, 0, 0, 0.3)"
              }}
              labelStyle={{ color: "rgb(226, 232, 240)", fontWeight: "bold" }}
              itemStyle={{ color: "rgb(203, 213, 225)" }}
            />
            <Legend 
              wrapperStyle={{ fontSize: "13px", paddingTop: "10px" }}
              formatter={(value) => <span className="text-slate-300 font-semibold">{value}</span>}
            />
            <Line
              yAxisId="temp"
              type="monotone"
              dataKey="temperature"
              name="Temperature (°C)"
              stroke="rgb(16, 185, 129)"
              strokeWidth={3}
              dot={false}
              activeDot={{ r: 5, fill: "rgb(16, 185, 129)", strokeWidth: 2, stroke: "white" }}
            />
            <Line
              yAxisId="speed"
              type="monotone"
              dataKey="speed"
              name="Speed (RPM)"
              stroke="rgb(59, 130, 246)"
              strokeWidth={3}
              dot={false}
              activeDot={{ r: 5, fill: "rgb(59, 130, 246)", strokeWidth: 2, stroke: "white" }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};
