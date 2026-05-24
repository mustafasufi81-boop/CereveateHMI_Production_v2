import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Calendar, Clock } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Calendar as CalendarComponent } from "@/components/ui/calendar";
import { format } from "date-fns";

export interface TimeFilter {
  type: "quick" | "custom";
  value?: number; // minutes for quick filters
  startDate?: Date;
  endDate?: Date;
}

interface TimeFilterBarProps {
  onFilterChange: (filter: TimeFilter) => void;
  selectedFilter?: TimeFilter;
}

const quickFilters = [
  { label: "5 min", value: 5 },
  { label: "10 min", value: 10 },
  { label: "30 min", value: 30 },
  { label: "1 hr", value: 60 },
  { label: "4 hr", value: 240 },
  { label: "8 hr", value: 480 },
  { label: "24 hr", value: 1440 },
];

export const TimeFilterBar = ({ onFilterChange, selectedFilter }: TimeFilterBarProps) => {
  const [dateRange, setDateRange] = useState<{ from?: Date; to?: Date }>({});
  const [showCalendar, setShowCalendar] = useState(false);

  const handleQuickFilter = (minutes: number) => {
    onFilterChange({ type: "quick", value: minutes });
  };

  const handleDateRangeApply = () => {
    if (dateRange.from && dateRange.to) {
      onFilterChange({
        type: "custom",
        startDate: dateRange.from,
        endDate: dateRange.to,
      });
      setShowCalendar(false);
    }
  };

  const isQuickFilterActive = (value: number) => {
    return selectedFilter?.type === "quick" && selectedFilter?.value === value;
  };

  return (
    <div className="flex items-center gap-2 p-3 bg-card border rounded-lg flex-wrap">
      <div className="flex items-center gap-1 mr-2">
        <Clock className="h-4 w-4 text-muted-foreground" />
        <span className="text-sm font-medium text-muted-foreground">Time Range:</span>
      </div>

      {/* Quick Filters */}
      {quickFilters.map((filter) => (
        <Button
          key={filter.value}
          variant={isQuickFilterActive(filter.value) ? "default" : "outline"}
          size="sm"
          onClick={() => handleQuickFilter(filter.value)}
          className="h-8"
        >
          {filter.label}
        </Button>
      ))}

      {/* Custom Date Range */}
      <Popover open={showCalendar} onOpenChange={setShowCalendar}>
        <PopoverTrigger asChild>
          <Button
            variant={selectedFilter?.type === "custom" ? "default" : "outline"}
            size="sm"
            className="h-8 gap-2"
          >
            <Calendar className="h-4 w-4" />
            {selectedFilter?.type === "custom" && selectedFilter.startDate && selectedFilter.endDate
              ? `${format(selectedFilter.startDate, "MMM d")} - ${format(selectedFilter.endDate, "MMM d")}`
              : "Custom Range"}
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-auto p-0" align="start">
          <div className="p-3 space-y-3">
            <div className="space-y-2">
              <label className="text-sm font-medium">From</label>
              <CalendarComponent
                mode="single"
                selected={dateRange.from}
                onSelect={(date) => setDateRange({ ...dateRange, from: date })}
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">To</label>
              <CalendarComponent
                mode="single"
                selected={dateRange.to}
                onSelect={(date) => setDateRange({ ...dateRange, to: date })}
              />
            </div>
            <div className="flex gap-2">
              <Button
                onClick={handleDateRangeApply}
                disabled={!dateRange.from || !dateRange.to}
                className="flex-1"
              >
                Apply
              </Button>
              <Button variant="outline" onClick={() => setShowCalendar(false)} className="flex-1">
                Cancel
              </Button>
            </div>
          </div>
        </PopoverContent>
      </Popover>

      {/* Reset Filter */}
      {selectedFilter && (
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onFilterChange({ type: "quick", value: 60 })}
          className="h-8 text-muted-foreground"
        >
          Reset
        </Button>
      )}
    </div>
  );
};
