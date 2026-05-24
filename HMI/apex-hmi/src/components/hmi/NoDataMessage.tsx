import { Database, TrendingUp, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";

interface NoDataMessageProps {
  /**
   * Type of message to display
   * - 'no-data': No data available for selected criteria
   * - 'loading': Data is being fetched
   * - 'error': Error occurred while fetching data
   */
  type?: 'no-data' | 'loading' | 'error';
  
  /**
   * Custom title message
   */
  title?: string;
  
  /**
   * Custom subtitle/hint message
   */
  subtitle?: string;
  
  /**
   * Height of the container (e.g., "h-80", "h-64")
   */
  height?: string;
  
  /**
   * Custom icon component
   */
  icon?: React.ReactNode;
  
  /**
   * Additional CSS classes
   */
  className?: string;
}

/**
 * Standardized "No Data" message component for trends and charts
 * ISA-101 Compliant styling
 */
export const NoDataMessage = ({ 
  type = 'no-data',
  title,
  subtitle,
  height = "h-80",
  icon,
  className
}: NoDataMessageProps) => {
  
  // Default messages based on type
  const defaultMessages = {
    'no-data': {
      title: 'NO DATA AVAILABLE',
      subtitle: 'No data found for the selected time range or tag',
      icon: <Database className="h-12 w-12 text-slate-600 mx-auto mb-3" />
    },
    'loading': {
      title: 'LOADING DATA...',
      subtitle: 'Please wait while we fetch the data',
      icon: <TrendingUp className="h-12 w-12 text-blue-500 animate-pulse mx-auto mb-3" />
    },
    'error': {
      title: 'ERROR LOADING DATA',
      subtitle: 'Failed to load data. Please try again',
      icon: <AlertCircle className="h-12 w-12 text-red-500 mx-auto mb-3" />
    }
  };

  const message = defaultMessages[type];
  const displayTitle = title || message.title;
  const displaySubtitle = subtitle || message.subtitle;
  const displayIcon = icon || message.icon;

  return (
    <div 
      className={cn(
        height,
        "flex items-center justify-center rounded-lg border-2 border-slate-700",
        "bg-slate-900/40",
        className
      )}
    >
      <div className="text-center">
        {displayIcon}
        <p className="text-sm text-slate-400 mb-1 font-mono font-bold tracking-wider">
          {displayTitle}
        </p>
        <p className="text-xs text-slate-500 font-mono">
          {displaySubtitle}
        </p>
      </div>
    </div>
  );
};
