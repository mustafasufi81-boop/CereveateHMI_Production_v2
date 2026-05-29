import { useState, useEffect, useCallback, useRef } from "react";
import { Activity, AlertTriangle, Wifi, Database, Settings, User, LogOut, Shield, TrendingUp } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";
import { useAuth } from "@/context/auth-context";
import { useTagSelection } from "@/context/tag-selection-context";
import { auditService } from "@/services/audit-service";
import { ShiftWarningNotification } from "@/components/rbac/ShiftWarningNotification";
import { CriticalOperationModal } from "@/components/rbac/CriticalOperationModal";
import { useCriticalOperation } from "@/hooks/useApprovalWorkflow";
import { AssetSidebar } from "./AssetSidebar";
import { UserHeader } from "./UserHeader";
import { AlarmPanel } from "./AlarmPanel";
import { TripTimeline } from "./TripTimeline";
import { InterlockStatusBoard } from "./InterlockStatusBoard";
import { PredictiveTrendModal } from "./PredictiveTrendModal";
import { HmiAnalyticsTab } from "./HmiAnalyticsTab";
import PredictiveAlarmPanel from "./PredictiveAlarmPanel";

import { usePermission } from "@/hooks/usePermission";
import mqttWebSocketService from "@/services/mqtt-websocket";
import { ConnectionHealthBanner } from "./ConnectionHealthBanner";
import { useConnectionHealth } from "@/hooks/useConnectionHealth";
import { useOpcPlcStatus } from "@/hooks/useOpcPlcStatus";
import { ISA_101_TREND_CONFIG, MAX_SELECTED_TAGS } from "@/config/isa101-trend-config";

// API Configuration
const API_BASE_URL = (import.meta.env.VITE_API_URL || '/api').replace(/\/api\/?$/, '');
const API_ROOT = `${API_BASE_URL}/api`;

// Standardized logging helpers for consistent, filterable logs
const LOG_PREFIX = {
  info: '[HMI-OPS]',
  warn: '[HMI-WARN]',
  error: '[HMI-ERR]',
  debug: '[HMI-DEBUG]'
};

const logInfo = (message?: any, ...optionalParams: any[]) => {
  console.info(`${LOG_PREFIX.info} ${String(message ?? '')}`, ...optionalParams);
};

const logWarn = (message?: any, ...optionalParams: any[]) => {
  console.warn(`${LOG_PREFIX.warn} ${String(message ?? '')}`, ...optionalParams);
};

const logError = (message?: any, ...optionalParams: any[]) => {
  console.error(`${LOG_PREFIX.error} ${String(message ?? '')}`, ...optionalParams);
};

const logDebug = (message?: any, ...optionalParams: any[]) => {
  if (import.meta.env.DEV) {
    console.debug(`${LOG_PREFIX.debug} ${String(message ?? '')}`, ...optionalParams);
  }
};

// ISA-101 Compliant Color System
const ISA_COLORS = {
  background: '#1C1C1E',
  foreground: '#E5E5E5',
  panel: '#2A2A2C',
  border: '#404040',
  
  // Equipment States
  equipmentNormal: '#808080',
  equipmentRunning: '#00C851',
  equipmentStopped: '#808080',
  equipmentAlarm: '#FF4444',
  equipmentWarning: '#FFB300',
  
  // Data Values
  valueNormal: '#00FF00',
  valueWarning: '#FFFF00',
  valueAlarm: '#FF0000',
  valueDisabled: '#666666',
  
  // Alarms
  alarmP1: '#FF0000',
  alarmP2: '#FFB300',
  alarmP3: '#FFFF00',
  
  // System Status
  statusOnline: '#00C851',
  statusOffline: '#FF4444',
  alarmCritical: '#FF4444',  // alias — same red as equipmentAlarm
};

interface Asset {
  id: string;
  name: string;
  type: 'plant' | 'area' | 'equipment' | 'component';
  children?: Asset[];
  tags?: Tag[];
}

interface Tag {
  id: string;
  name: string;
  description: string;
  value: number;
  unit: string;
  sp?: number;
  hiLimit?: number;
  loLimit?: number;
  status: 'normal' | 'warning' | 'alarm';
  mode: 'auto' | 'manual' | 'hand';
  plant?: string;      // ISA-101: Contextual information for situation awareness
  area?: string;       // ISA-101: Equipment location context
  equipment?: string;  // ISA-101: Parent equipment identification
  windowId?: string;   // Which trend window this tag belongs to (overrides unit grouping)
}

interface Alarm {
  id: string;
  timestamp: string;
  priority: 1 | 2 | 3;
  tagId: string;
  message: string;
  acknowledged: boolean;
  value?: number;
}

// Static Asset Taxonomy
const ASSET_TREE: Asset[] = [
  {
    id: 'plant-001',
    name: 'MAIN PLANT',
    type: 'plant',
    children: [
      {
        id: 'area-100',
        name: 'PRODUCTION AREA A',
        type: 'area',
        children: [
          {
            id: 'eq-comp-101',
            name: 'COMPRESSOR C-101',
            type: 'equipment',
            children: [
              {
                id: 'comp-motor-101',
                name: 'MOTOR',
                type: 'component',
                tags: [
                  { id: 'TT-101', name: 'TT-101', description: 'MOTOR TEMPERATURE', value: 85.2, unit: '°C', sp: 80, hiLimit: 100, loLimit: 60, status: 'warning', mode: 'auto' },
                  { id: 'ST-101', name: 'ST-101', description: 'MOTOR SPEED', value: 1485, unit: 'RPM', sp: 1500, hiLimit: 1600, loLimit: 1400, status: 'normal', mode: 'auto' },
                  { id: 'VT-101', name: 'VT-101', description: 'VIBRATION', value: 8.5, unit: 'mm/s', sp: 5, hiLimit: 7, loLimit: 0, status: 'alarm', mode: 'auto' },
                  { id: 'CT-101', name: 'CT-101', description: 'CURRENT', value: 145, unit: 'A', sp: 150, hiLimit: 180, loLimit: 100, status: 'normal', mode: 'auto' },
                ]
              },
              {
                id: 'comp-bearing-101',
                name: 'BEARING',
                type: 'component',
                tags: [
                  { id: 'TT-102', name: 'TT-102', description: 'BEARING TEMP', value: 72.5, unit: '°C', sp: 70, hiLimit: 85, loLimit: 40, status: 'normal', mode: 'auto' },
                  { id: 'VT-102', name: 'VT-102', description: 'BEARING VIB', value: 3.2, unit: 'mm/s', sp: 3, hiLimit: 5, loLimit: 0, status: 'normal', mode: 'auto' },
                ]
              },
              {
                id: 'comp-cooling-101',
                name: 'COOLING SYSTEM',
                type: 'component',
                tags: [
                  { id: 'Cooling_FAN_SPEED', name: 'Cooling_FAN_SPEED', description: 'COOLING FAN SPEED', value: 0, unit: 'rpm', sp: 1500, hiLimit: 1800, loLimit: 1000, status: 'normal', mode: 'auto' },
                ]
              }
            ]
          },
          {
            id: 'eq-pump-201',
            name: 'PUMP P-201',
            type: 'equipment',
            children: [
              {
                id: 'pump-motor-201',
                name: 'MOTOR',
                type: 'component',
                tags: [
                  { id: 'PT-201', name: 'PT-201', description: 'DISCHARGE PRESSURE', value: 4.5, unit: 'bar', sp: 4.2, hiLimit: 5.5, loLimit: 3, status: 'normal', mode: 'auto' },
                  { id: 'FT-201', name: 'FT-201', description: 'FLOW RATE', value: 165, unit: 'L/min', sp: 160, hiLimit: 200, loLimit: 100, status: 'normal', mode: 'auto' },
                  { id: 'TT-201', name: 'TT-201', description: 'MOTOR TEMP', value: 68.3, unit: '°C', sp: 65, hiLimit: 90, loLimit: 50, status: 'normal', mode: 'auto' },
                ]
              }
            ]
          }
        ]
      },
      {
        id: 'area-200',
        name: 'PRODUCTION AREA B',
        type: 'area',
        children: [
          {
            id: 'eq-tank-301',
            name: 'TANK T-301',
            type: 'equipment',
            children: [
              {
                id: 'tank-level-301',
                name: 'LEVEL CONTROL',
                type: 'component',
                tags: [
                  { id: 'LT-301', name: 'LT-301', description: 'LEVEL', value: 67.5, unit: '%', sp: 70, hiLimit: 90, loLimit: 20, status: 'normal', mode: 'auto' },
                  { id: 'TT-301', name: 'TT-301', description: 'TEMPERATURE', value: 45.2, unit: '°C', sp: 45, hiLimit: 60, loLimit: 30, status: 'normal', mode: 'auto' },
                ]
              }
            ]
          }
        ]
      }
    ]
  }
];

// Static Alarm Data
const INITIAL_ALARMS: Alarm[] = [
  { id: 'alm-001', timestamp: '2026-01-24 14:25:32', priority: 1, tagId: 'VT-101', message: 'COMPRESSOR C-101: HIGH VIBRATION ALARM - CRITICAL', acknowledged: false, value: 8.5 },
  { id: 'alm-002', timestamp: '2026-01-24 14:23:15', priority: 2, tagId: 'TT-101', message: 'COMPRESSOR C-101: MOTOR TEMPERATURE WARNING', acknowledged: false, value: 85.2 },
  { id: 'alm-003', timestamp: '2026-01-24 14:20:45', priority: 3, tagId: 'PT-201', message: 'PUMP P-201: PRESSURE DEVIATION', acknowledged: true, value: 4.5 },
  { id: 'alm-004', timestamp: '2026-01-24 14:18:22', priority: 2, tagId: 'LT-301', message: 'TANK T-301: LEVEL LOW WARNING', acknowledged: true, value: 67.5 },
];

// Helper function to format MQTT timestamp (ISO format) to display format
const formatMQTTTimestamp = (isoTimestamp: string, includeMilliseconds: boolean = false): string => {
  try {
    const date = new Date(isoTimestamp);
    const timeString = date.toLocaleTimeString('en-US', { 
      hour: '2-digit', 
      minute: '2-digit', 
      second: '2-digit',
      hour12: true
    });
    
    if (includeMilliseconds) {
      // Extract milliseconds from ISO timestamp or Date object
      const ms = date.getMilliseconds().toString().padStart(3, '0');
      
      // Insert milliseconds before AM/PM (handle with or without space)
      let result;
      if (timeString.match(/\s[AP]M$/i)) {
        // Format: "02:22:16 PM"
        result = timeString.replace(/(\s[AP]M)$/i, `.${ms}$1`);
      } else if (timeString.match(/[AP]M$/i)) {
        // Format: "02:22:16PM" (no space)
        result = timeString.replace(/([AP]M)$/i, `.${ms} $1`);
      } else {
        // Fallback: just append milliseconds
        result = timeString + `.${ms}`;
      }
      return result;
    }
    
    return timeString;
  } catch (error) {
    logError('[formatMQTTTimestamp] Error parsing timestamp:', error);
    // Fallback to current time if parsing fails
    const now = new Date();
    const timeString = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    return includeMilliseconds 
      ? timeString.replace(/( [AP]M)$/i, `.${now.getMilliseconds().toString().padStart(3, '0')}$1`)
      : timeString;
  }
};

// Generate trend data (last 30 points)
const generateTrendData = (baseValue: number, variance: number, minutes: number = 30, includeMilliseconds: boolean = false) => {
  const dataPoints = 30; // Always generate 30 points for smooth curves
  return Array.from({ length: dataPoints }, (_, i) => {
    const timestamp = new Date(Date.now() - (minutes - (i * minutes / (dataPoints - 1))) * 60000);
    const timeString = includeMilliseconds
      ? timestamp.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) + '.' + timestamp.getMilliseconds().toString().padStart(3, '0')
      : timestamp.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
    return {
      time: timeString,
      value: baseValue + (Math.sin(i / 3) * variance) + (Math.random() * variance * 0.3)
    };
  });
};

// Tag colors for multi-selection - ISA-101 Compliant
const TAG_TREND_COLORS = ISA_101_TREND_CONFIG.colors.trendLines;

// Format timestamp with date for historian mode (DD/MM/YYYY HH:mm:ss)
const formatHistorianTimestamp = (timestamp: string | Date, includeMilliseconds: boolean = false): string => {
  const date = typeof timestamp === 'string' ? new Date(timestamp) : timestamp;
  
  // DD/MM/YYYY format
  const day = date.getDate().toString().padStart(2, '0');
  const month = (date.getMonth() + 1).toString().padStart(2, '0');
  const year = date.getFullYear();
  const dateStr = `${day}/${month}/${year}`;
  
  const hours = date.getHours().toString().padStart(2, '0');
  const minutes = date.getMinutes().toString().padStart(2, '0');
  const seconds = date.getSeconds().toString().padStart(2, '0');
  const timeStr = `${hours}:${minutes}:${seconds}`;
  
  if (includeMilliseconds) {
    return `${dateStr} ${timeStr}.${date.getMilliseconds().toString().padStart(3, '0')}`;
  }
  return `${dateStr} ${timeStr}`;
};

export const IndustrialHMIPrototype = () => {
  logInfo('🚀 [HMI-INIT] IndustrialHMIPrototype component mounted');
  
  const navigate = useNavigate();
  const { user, sessionId } = useAuth(); // Add authentication and session tracking
  const { selection, updateSelection } = useTagSelection(); // Access tag selection context
  
  // RBAC: Approval workflow for critical operations
  const {
    isModalOpen: isApprovalModalOpen,
    pendingOperation,
    executeWithApprovalCheck,
    onApprovalGranted,
    onApprovalFailed,
    cancelOperation
  } = useCriticalOperation();
  
  // Connection health (MQTT + Flask)
  const connHealth = useConnectionHealth();
  // OPC server + PLC gateway status (polled from C# backend every 10s)
  const opcPlcStatus = useOpcPlcStatus();

  // WebSocket state
  const [wsConnected, setWsConnected] = useState(false);
  const [liveTagValues, setLiveTagValues] = useState<Record<string, any>>({});
  const trendDataRef = useRef<Record<string, Array<{time: string, value: number}>>>({});
  const [historianTrendData, setHistorianTrendData] = useState<Record<string, Array<{time: string, value: number, min?: number, max?: number, count?: number, rawTimestamp?: string}>>>({});
  const [historianRenderKey, setHistorianRenderKey] = useState(0); // incremented to force re-render after historian fetch
  const trendsPausedRef = useRef<Record<string, boolean>>({}); // Per-unit pause tracking
  const [trendsPausedState, setTrendsPausedState] = useState<Record<string, boolean>>({}); // Per-unit UI state
  const [selectedTags, setSelectedTags] = useState<Tag[]>([]); // Changed to array for multi-selection
  const selectedTagsRef = useRef<Tag[]>([]); // Ref to avoid closure issues
  
  // Advanced trending features state
  const [cursorPosition, setCursorPosition] = useState<{x: number, y: number, unit: string} | null>(null);
  const [showStatistics, setShowStatistics] = useState<Record<string, boolean>>({}); // Per-tag statistics display
  const [showReferencLines, setShowReferenceLines] = useState(false);
  const [annotations, setAnnotations] = useState<Record<string, Array<{x: number, y: number, text: string}>>>({});
  const [showAnnotations, setShowAnnotations] = useState(true);
  const svgRefs = useRef<Record<string, SVGSVGElement | null>>({});
  
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set(['plant-001', 'area-100', 'eq-comp-101']));
  const [selectedAsset, setSelectedAsset] = useState<Asset | null>(null);
  const [selectedEquipment, setSelectedEquipment] = useState("eq-m101"); // For AssetSidebar
  const [selectedNode, setSelectedNode] = useState<any | null>(null); // For AssetSidebar
  const [predictiveTrendTag, setPredictiveTrendTag] = useState<{ id: string; name: string } | null>(null);
  const openPredictiveTrend = useCallback((id: string, name: string) => {
    setPredictiveTrendTag({ id, name });
  }, []);
  // Trend window targeting: which window is "active" for receiving tags
  const [activeTrendWindowId, setActiveTrendWindowId] = useState<string | null>(null);
  const [isDraggingTag, setIsDraggingTag] = useState(false);
  const [centerTab, setCenterTab] = useState<'trends' | 'analytics' | 'predictive'>('trends');

  // ── Analytics visibility guard ────────────────────────────────────────────
  // Reads analytics.canView from DB via usePermission.
  // Backend sets this correctly per role:
  //   Admin     → true  (isAdmin shortcut in usePermission)
  //   Operator  → true  (role_module_permissions row or fallback)
  //   Engineer  → true  (role_module_permissions row or fallback)
  //   Viewer    → false (fallback explicitly sets analytics: none_p)
  const canViewAnalytics = usePermission('analytics', 'canView');
  const canViewReports   = usePermission('reports', 'canView');
  const canViewAlarms    = usePermission('alarms',    'canView');
  const canViewHmi       = usePermission('hmi',       'canView');

  // Per-service failure tracking for the header status bar
  // Use consecutive-failure counters (ref, not state) to avoid re-render on every poll.
  // Badge only shows after 3+ consecutive failures — prevents transient blips.
  const opcFailCountRef = useRef(0);
  const plcFailCountRef = useRef(0);
  const [opcFailed,  setOpcFailed]  = useState(false);
  const [plcFailed,  setPlcFailed]  = useState(false);
  const [usingRestFallback, setUsingRestFallback] = useState(false);

  // OPC/PLC connection state from backend health endpoint
  // Possible values: 'Connected' | 'Disconnected' | 'Reconnecting' | 'Degraded' | 'Faulted' | 'Unknown'
  const [opcConnectionState, setOpcConnectionState] = useState<string>('Unknown');
  // Per-source status: array of { server_progid, tag_count, live_tag_count, status }
  type SourceStatus = { server_progid: string; tag_count: number; live_tag_count: number; status: 'live' | 'disconnected' };
  const [sourceStatuses, setSourceStatuses] = useState<SourceStatus[]>([]);

  // Auto-snap back to TRENDS if user loses analytics access while on a restricted tab
  useEffect(() => {
    if (!canViewAnalytics && (centerTab === 'analytics' || centerTab === 'predictive')) {
      setCenterTab('trends');
    }
  }, [canViewAnalytics, centerTab]);

  const [alarms, setAlarms]= useState<Alarm[]>(INITIAL_ALARMS);
  const [currentTime, setCurrentTime] = useState(new Date());
  const [zoomLevel, setZoomLevel] = useState(1); // Zoom level: 1 = normal, 2 = 2x, 0.5 = 50%
  
  // Per-unit chart states: each unit has independent mode, time range, and date picker
  const [chartStates, setChartStates] = useState<Record<string, {
    dataMode: 'live' | 'historian';
    timeRange: number; // Default: 5 minutes for historian mode
    showCustomDatePicker: boolean;
    customStartDate: string;
    customEndDate: string;
    showMinMaxBand: boolean; // Toggle for min/max shaded area
    scrollOffset: number; // Scroll position for pan navigation (0 = latest data)
  }>>({});
  const chartStatesRef = useRef(chartStates);
  chartStatesRef.current = chartStates;
  
  // Tooltip state for showing avg/min/max on hover
  const [tooltip, setTooltip] = useState<{
    visible: boolean;
    x: number;
    y: number;
    data: {
      time: string;
      value: number;
      min?: number;
      max?: number;
      count?: number;
    };
    tagName: string;
    isAggregated: boolean; // Track if data is aggregated (historian) or actual (live)
  } | null>(null);
  
  const [systemStatus] = useState({
    plc: true,
    opc: true,
    historian: true,
    alarmCount: { p1: 1, p2: 1, p3: 0 }
  });
  
  // Millisecond display toggle for trends
  const [showMilliseconds, setShowMilliseconds] = useState(false);
  const showMillisecondsRef = useRef(false); // Ref to track current state without re-creating MQTT handlers
  
  // DEBUG PANEL - ISA-101 Compliance Check
  const [showDebugPanel, setShowDebugPanel] = useState(false);
  
  // Handler to toggle milliseconds and clear trend data for consistent formatting
  const handleMillisecondsToggle = (enabled: boolean) => {
    setShowMilliseconds(enabled);
    showMillisecondsRef.current = enabled; // Update ref for MQTT handler
    // Clear all trend data to ensure consistent time format
    Object.keys(trendDataRef.current).forEach(key => {
      trendDataRef.current[key] = [];
    });
    setHistorianTrendData({});
  };

  const getRenderedTrendData = (tagId: string, dataMode: 'live' | 'historian') => {
    return dataMode === 'historian'
      ? (historianTrendData[tagId] || [])
      : (trendDataRef.current[tagId] || []);
  };

  // Statistical calculations utility
  const calculateStatistics = (data: Array<{time: string, value: number}>) => {
    if (!data || data.length === 0) return null;
    
    const values = data.map(d => d.value);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const avg = values.reduce((a, b) => a + b, 0) / values.length;
    const variance = values.reduce((sum, val) => sum + Math.pow(val - avg, 2), 0) / values.length;
    const stdDev = Math.sqrt(variance);
    
    // Rate of change (last point - first point) / time
    const rateOfChange = data.length > 1 ? (data[data.length - 1].value - data[0].value) / data.length : 0;
    
    return { min, max, avg, stdDev, rateOfChange };
  };

  // Export chart as PNG
  const exportChartAsPNG = (unit: string) => {
    const svg = svgRefs.current[unit];
    if (!svg) return;
    
    const svgData = new XMLSerializer().serializeToString(svg);
    const canvas = document.createElement('canvas');
    canvas.width = 1200;
    canvas.height = 400;
    const ctx = canvas.getContext('2d');
    
    const img = new Image();
    const svgBlob = new Blob([svgData], { type: 'image/svg+xml;charset=utf-8' });
    const url = URL.createObjectURL(svgBlob);
    
    img.onload = () => {
      ctx?.drawImage(img, 0, 0);
      URL.revokeObjectURL(url);
      
      canvas.toBlob((blob) => {
        if (blob) {
          const a = document.createElement('a');
          a.href = URL.createObjectURL(blob);
          a.download = `trend_${unit}_${new Date().toISOString().slice(0,19).replace(/:/g,'-')}.png`;
          a.click();
        }
      });
    };
    
    img.src = url;
  };

  // Export data as CSV
  const exportDataAsCSV = (tags: Tag[], unit: string) => {
    let csv = 'Time,' + tags.map(t => `${t.name} (${t.unit})`).join(',') + '\n';
    
    // Get max length of trend data
    const maxLength = Math.max(...tags.map(t => trendDataRef.current[t.id]?.length || 0));
    
    for (let i = 0; i < maxLength; i++) {
      const row: string[] = [];
      let time = '';
      
      tags.forEach((tag, idx) => {
        const data = trendDataRef.current[tag.id];
        if (data && data[i]) {
          if (idx === 0) time = data[i].time;
          row.push(data[i].value.toFixed(2));
        } else {
          row.push('');
        }
      });
      
      csv += `${time},${row.join(',')}\n`;
    }
    
    const blob = new Blob([csv], { type: 'text/csv' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `trend_data_${unit}_${new Date().toISOString().slice(0,19).replace(/:/g,'-')}.csv`;
    a.click();
  };

  // Load previously selected tags on mount (from localStorage directly - full tag objects)
  useEffect(() => {
    // First, try to restore FULL TAG OBJECTS from localStorage (this includes database tags)
    try {
      const storedTags = localStorage.getItem('hmi_selected_tags_full');
      if (storedTags) {
        const parsed = JSON.parse(storedTags);
        if (Array.isArray(parsed) && parsed.length > 0) {
          setSelectedTags(parsed);
          selectedTagsRef.current = parsed;
          return; // Successfully restored, exit early
        }
      }
    } catch (e) {
      logError('Failed to restore selected tags:', e);
    }

    // Fallback: Try context (for compatibility)
    let tagIdsToRestore: string[] = (selection.selectedTags || []).map(id => String(id).trim()).filter(id => id.length > 0);

    if (!tagIdsToRestore || tagIdsToRestore.length === 0) {
      try {
        const storedIds = localStorage.getItem('hmi_selected_tag_ids');
        if (storedIds) {
          const parsed = JSON.parse(storedIds);
          tagIdsToRestore = (Array.isArray(parsed) ? parsed : []).map(id => String(id).trim());
        }
      } catch (e) {
        logError('Failed to parse selected tag IDs:', e);
      }
    }

    if (tagIdsToRestore && tagIdsToRestore.length > 0) {
      // Find matching tags in ASSET_TREE (fallback for static tags only)
      const findTagsFromAssetTree = (assets: Asset[]): Tag[] => {
        const foundTags: Tag[] = [];
        const visitNode = (node: Asset) => {
          if (node.tags) {
            const matching = node.tags.filter(tag => {
              const normalizedTagId = String(tag.id).trim();
              return tagIdsToRestore.includes(normalizedTagId);
            });
            foundTags.push(...matching);
          }
          if (node.children) {
            node.children.forEach(child => visitNode(child));
          }
        };
        assets.forEach(asset => visitNode(asset));
        return foundTags;
      };

      const tagsToRestore = findTagsFromAssetTree(ASSET_TREE);
      
      if (tagsToRestore.length > 0) {
        setSelectedTags(tagsToRestore);
        selectedTagsRef.current = tagsToRestore;
      }
    }
  }, []); // Run only on mount

  const persistTagIdsToStorage = (tags: Tag[]) => {
    // Store FULL tag objects for complete restoration (includes database tags)
    const tagData = tags.map(t => ({
      id: String(t.id).trim(),
      name: t.name,
      description: t.description,
      value: t.value,
      unit: t.unit,
      sp: t.sp,
      hiLimit: t.hiLimit,
      loLimit: t.loLimit,
      status: t.status,
      mode: t.mode,
      plant: t.plant,      // ISA-101: Persist contextual information
      area: t.area,
      equipment: t.equipment
    }));
    localStorage.setItem('hmi_selected_tags_full', JSON.stringify(tagData));
    
    // Also keep IDs for compatibility
    const tagIds = tags.map(t => String(t.id).trim());
    localStorage.setItem('hmi_selected_tag_ids', JSON.stringify(tagIds));

    updateSelection({ selectedTags: tagIds });
  };

  // Persist selected tags to both context AND localStorage
  useEffect(() => {
    const tagIds = selectedTags.map(tag => String(tag.id).trim()).filter(id => id.length > 0);
    
    // Store FULL tag objects for complete restoration
    const tagData = selectedTags.map(t => ({
      id: String(t.id).trim(),
      name: t.name,
      description: t.description,
      value: t.value,
      unit: t.unit,
      sp: t.sp,
      hiLimit: t.hiLimit,
      loLimit: t.loLimit,
      status: t.status,
      mode: t.mode
    }));
    localStorage.setItem('hmi_selected_tags_full', JSON.stringify(tagData));
    
    // Also keep IDs for compatibility
    localStorage.setItem('hmi_selected_tag_ids', JSON.stringify(tagIds));
    
    // Save to context
    if (tagIds.length > 0) {
      updateSelection({ selectedTags: tagIds });
    }
  }, [selectedTags, updateSelection]);

  // Save tags to localStorage before component unmounts
  useEffect(() => {
    return () => {
      // Cleanup: Save current tags to localStorage when leaving the page
      if (selectedTagsRef.current.length > 0) {
        const tagIds = selectedTagsRef.current.map(tag => String(tag.id).trim()).filter(id => id.length > 0);
        localStorage.setItem('hmi_selected_tag_ids', JSON.stringify(tagIds));
      }
    };
  }, []);

  // Save tags when page visibility changes
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.hidden) {
        // Page is hidden, save tags
        if (selectedTagsRef.current.length > 0) {
          const tagIds = selectedTagsRef.current.map(tag => String(tag.id).trim()).filter(id => id.length > 0);
          localStorage.setItem('hmi_selected_tag_ids', JSON.stringify(tagIds));
        }
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
  }, []);

  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  // WebSocket connection for live MQTT data
  useEffect(() => {
    logInfo('🔌 Connecting to WebSocket for MQTT live data...');

    // Subscribe to real-time connection state changes (instant UI update)
    const unsubConn = mqttWebSocketService.onConnectionChange((connected) => {
      setWsConnected(connected);
      if (connected) {
        setUsingRestFallback(false);
      }
      logInfo(connected ? '✅ Socket.IO connected' : 'âš ï¸ Socket.IO disconnected');
    });

    mqttWebSocketService.connect();
    setWsConnected(mqttWebSocketService.isConnected());

    const handleMQTTUpdate = (data: any) => {
      if (data.tags && Array.isArray(data.tags)) {
        const updates: Record<string, any> = {};
        
        data.tags.forEach((tag: any) => {
          const tagId = tag.tag_id;
          // C# publishes plain `value`; DB-sourced payloads may use value_num/value_text/value_bool
          const value = tag.value_num ?? tag.value_text ?? tag.value_bool ?? tag.value;
          
          if (tagId && value !== undefined) {
            updates[tagId] = {
              value: value,
              quality: tag.quality,
              timestamp: tag.time || new Date().toISOString(),
              unit: tag.eng_unit || '',
              topic: data.topic
            };

            // Update trend data (check if this tag's unit is paused)
            // Find the tag in selectedTags to get its unit
            const currentSelectedTags = selectedTagsRef.current;
            const selectedTag = currentSelectedTags.find(t => String(t.id) === String(tagId));
            
            if (selectedTag) {
              const tagUnit = selectedTag.unit || tag.eng_unit || ''; // empty string for unit-less tags
              const isUnitPaused = trendsPausedRef.current[tagUnit] || false;
              // Determine the chart key (windowId or cleaned unit)
              const chartKey = selectedTag.windowId || tagUnit.replace(/^\d+\s*/, '').trim();
              const isHistorianMode = chartStatesRef.current[chartKey]?.dataMode === 'historian';
              
              if (!isUnitPaused && !isHistorianMode) {
                if (!trendDataRef.current[tagId]) {
                  trendDataRef.current[tagId] = [];
                }
                
                const trendData = trendDataRef.current[tagId];
                // Use actual timestamp from MQTT message
                const mqttTimestamp = tag.time || new Date().toISOString();
                const timeString = formatMQTTTimestamp(mqttTimestamp, showMillisecondsRef.current);
                const numericValue = typeof value === 'number' ? value : parseFloat(String(value));
                if (isNaN(numericValue)) {
                  return;
                }
                trendData.push({
                  time: timeString,
                  value: numericValue
                });
              
                // Keep last 100 points
                if (trendData.length > 100) {
                  trendData.shift();
                }
              }
            }
          }
        });
        
        if (Object.keys(updates).length > 0) {
          setLiveTagValues(prev => ({ ...prev, ...updates }));
          
          // Update tag units from MQTT data if not already set
          setSelectedTags(prevTags => {
            const updatedTags = prevTags.map(tag => {
              const mqttData = updates[tag.id];
              if (mqttData && mqttData.unit && !tag.unit) {
                logInfo(`[IndustrialHMI] 🔧 Updating unit for tag ${tag.id}: "${mqttData.unit}"`);
                return { ...tag, unit: mqttData.unit };
              }
              return tag;
            });
            // Sync ref
            selectedTagsRef.current = updatedTags;
            return updatedTags;
          });
        }
      }
    };

    const handleMQTTAlarm = (alarmData: any) => {
      logInfo('🚨 MQTT Alarm received:', alarmData);
      
      // Add or update alarm in the alarms array
      setAlarms(prevAlarms => {
        const existingIndex = prevAlarms.findIndex(a => a.id === alarmData.id);
        
        const newAlarm: Alarm = {
          id: alarmData.id,
          timestamp: alarmData.timestamp,
          priority: alarmData.priority,
          tagId: alarmData.tagId,
          message: alarmData.message,
          acknowledged: alarmData.acknowledged,
          value: alarmData.value
        };
        
        if (existingIndex >= 0) {
          // Update existing alarm
          const updated = [...prevAlarms];
          updated[existingIndex] = newAlarm;
          return updated;
        } else {
          // Add new alarm at the beginning (most recent first)
          return [newAlarm, ...prevAlarms];
        }
      });
    };

    mqttWebSocketService.on('mqtt_tag_update', handleMQTTUpdate);
    mqttWebSocketService.on('mqtt_alarm', handleMQTTAlarm);

    return () => {
      mqttWebSocketService.off('mqtt_tag_update', handleMQTTUpdate);
      mqttWebSocketService.off('mqtt_alarm', handleMQTTAlarm);
      unsubConn();
    };
  }, []);

  // REST fallback: poll /api/opc/values + /api/plc/values every 1s
  // Restarts automatically when canViewHmi changes (permission restored -> data resumes)

  // Poll /api/source-status every 10s — shows per-server_progid live/disconnected state
  // Only marks a source DISCONNECTED if it has enabled tags configured in DB but no fresh data.
  // If no sources are configured in DB at all, nothing is shown (not a false alarm).
  useEffect(() => {
    const pollSourceStatus = async () => {
      try {
        const token = localStorage.getItem('auth_token') || '';
        const res = await fetch('/api/source-status', { headers: { Authorization: `Bearer ${token}` } });
        if (!res.ok) return;
        const data = await res.json();
        const sources: SourceStatus[] = data?.sources || [];
        setSourceStatuses(sources);
        // Derive overall OPC state for the existing badge
        if (sources.length === 0) {
          setOpcConnectionState('Unknown');
        } else if (sources.every(s => s.status === 'live')) {
          setOpcConnectionState('Connected');
        } else if (sources.some(s => s.status === 'live')) {
          setOpcConnectionState('Degraded');
        } else {
          setOpcConnectionState('Disconnected');
        }
      } catch {
        // network error — don't update state, keep last known
      }
    };
    pollSourceStatus();
    const t = setInterval(pollSourceStatus, 10_000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    if (!canViewHmi) {
      setUsingRestFallback(false);
      setOpcFailed(false);
      setPlcFailed(false);
      opcFailCountRef.current = 0;
      plcFailCountRef.current = 0;
      return;
    }

    // Shared helper: normalise any tag array/dict and push into liveTagValues + trend
    const applyTagUpdates = (raw: any, source: string) => {
      if (!raw) return;
      const entries: any[] = Array.isArray(raw)
        ? raw
        : Object.entries(raw).map(([id, v]: any) => ({ tagId: id, ...v }));
      const updates: Record<string, any> = {};
      entries.forEach((tag: any) => {
        const tagId: string | undefined = tag.tagId || tag.tag_id || tag.tagName || tag.id;
        const value = tag.value_num ?? tag.value_text ?? tag.value_bool ?? tag.value;
        if (tagId && value !== undefined && value !== null) {
          updates[tagId] = {
            value,
            quality:   tag.quality   || 'Good',
            timestamp: tag.timestamp || tag.time || tag.cachedAt || new Date().toISOString(),
            unit:      tag.eng_unit  || tag.unit || '',
            source,
          };
        }
      });
      if (Object.keys(updates).length === 0) return;
      setLiveTagValues(prev => ({ ...prev, ...updates }));
      const currentSelected = selectedTagsRef.current;
      Object.entries(updates).forEach(([tagId, tagData]) => {
        const selTag = currentSelected.find(t => String(t.id) === String(tagId));
        if (!selTag) return;
        const tagUnit = selTag.unit || tagData.unit || '';
        const isPaused = trendsPausedRef.current[tagUnit] || false;
        const chartKey = selTag.windowId || tagUnit.replace(/^\d+\s*/, '').trim();
        const isHistorianMode = chartStatesRef.current[chartKey]?.dataMode === 'historian';
        if (isPaused || isHistorianMode) return;
        if (!trendDataRef.current[tagId]) trendDataRef.current[tagId] = [];
        const trendArr = trendDataRef.current[tagId];
        const ts = tagData.timestamp || new Date().toISOString();
        const timeString = formatMQTTTimestamp(ts, showMillisecondsRef.current);
        const numVal = typeof tagData.value === 'number' ? tagData.value : parseFloat(String(tagData.value));
        if (!isNaN(numVal)) {
          trendArr.push({ time: timeString, value: numVal });
          if (trendArr.length > 300) trendArr.shift();
        }
      });
    };

    const pollRestValues = async () => {
      const token = localStorage.getItem('auth_token') || '';
      const headers = { Authorization: `Bearer ${token}` };

      // -- OPC REST poll --
      try {
        const res = await fetch('/api/opc/values', { headers, signal: AbortSignal.timeout(4500) });
        if (!res.ok) throw new Error(`OPC HTTP ${res.status}`);
        const data = await res.json();
        opcFailCountRef.current = 0;
        setOpcFailed(false);
        applyTagUpdates(data?.tags ?? data, 'rest-opc');
        setUsingRestFallback(!mqttWebSocketService.isConnected());
      } catch (e) {
        opcFailCountRef.current += 1;
        if (opcFailCountRef.current >= 3) setOpcFailed(true);
        console.warn('[REST] OPC poll failed:', e);
      }

      // -- PLC REST poll --
      try {
        const res = await fetch('/api/plc/values', { headers, signal: AbortSignal.timeout(4500) });
        if (!res.ok) throw new Error(`PLC HTTP ${res.status}`);
        const data = await res.json();
        plcFailCountRef.current = 0;
        setPlcFailed(false);
        applyTagUpdates(data?.tags ?? data?.values ?? data, 'rest-plc');
        // Notify MQTT health service that fresh data arrived (resets stale-data watchdog)
        mqttWebSocketService.notifyRestDataFresh('plc-rest');
      } catch (e) {
        plcFailCountRef.current += 1;
        if (plcFailCountRef.current >= 3) setPlcFailed(true);
        console.warn('[REST] PLC poll failed:', e);
      }
    };

    const interval = setInterval(pollRestValues, 5000); // 5s — prevents stacking when C# is slow
    pollRestValues(); // run immediately on mount / permission restore
    return () => clearInterval(interval);
  }, [canViewHmi]); // restart when HMI access is granted/revoked

  // Historian Data Fetching - When mode switches to 'historian'
  useEffect(() => {
    const fetchHistorianData = async () => {
      const historianUpdates: Record<string, Array<{time: string, value: number, min?: number, max?: number, count?: number, rawTimestamp?: string}>> = {};
      // Find all units that are in historian mode
      const historianUnits = Object.entries(chartStates).filter(([_, state]) => state.dataMode === 'historian');
      
      if (historianUnits.length === 0) {
        return;
      }

      // For each unit in historian mode, fetch data for its tags
      for (const [unit, state] of historianUnits) {
        // Check if this unit is paused
        const isPaused = trendsPausedRef.current[unit] || false;
        if (isPaused) {
          continue;
        }
        logDebug(`[Historian] 🔍 State object:`, JSON.stringify({
          timeRange: state.timeRange,
          customStartDate: state.customStartDate,
          customEndDate: state.customEndDate,
          dataMode: state.dataMode
        }, null, 2));
        
        // Get tags for this window correctly (win_ = windowId match, else unit match)
        const tagsForUnit = unit.startsWith('win_')
          ? selectedTags.filter(t => t.windowId === unit)
          : selectedTags.filter(t => t.unit === unit || (t.unit || '').replace(/^\d+\s*/, '').trim() === unit);
        
        if (tagsForUnit.length === 0) {
          continue;
        }

        for (const tag of tagsForUnit) {
          try {
            let startParam: string;
            let endParam: string;
            
            // CRITICAL: Check for custom dates FIRST
            if (state.customStartDate && state.customEndDate) {
              // Use custom date range (DATE ONLY format: YYYY-MM-DD)
              startParam = state.customStartDate; // e.g., "2026-04-18"
              endParam = state.customEndDate;     // e.g., "2026-04-19"
              logDebug(`[Historian] 📅 Using CUSTOM range for ${tag.id}: ${startParam} to ${endParam}`);
            } else {
              // Calculate relative time range (for live/recent data)
              const endTime = new Date();
              const startTime = new Date(endTime.getTime() - state.timeRange * 60 * 1000);
              startParam = startTime.toISOString();
              endParam = endTime.toISOString();
              logDebug(`[Historian] ⏰ Using RELATIVE range for ${tag.id}: ${state.timeRange} minutes`);
            }

            // INDUSTRY STANDARD: Use 'auto' aggregation mode
            // Backend will intelligently aggregate based on time span:
            // <= 1 hour: raw data
            // <= 8 hours: 1-minute buckets
            // <= 1 day: 5-minute buckets
            // <= 1 week: 30-minute buckets
            // > 1 week: 1-hour buckets
            const params = new URLSearchParams({
              tag: tag.id,
              start_time: startParam,
              end_time: endParam,
              limit: '50000',  // Max cache limit (industry standard)
              aggregation: 'auto'  // Let backend choose optimal aggregation
            });

            const response = await fetch(`${API_ROOT}/historian/historical?${params}`);
            
            if (!response.ok) {
              logError(`[Historian] Failed to fetch data for ${tag.id}: ${response.status} ${response.statusText}`);
              continue;
            }

            const result = await response.json();
            const data = result.data || []; // Extract data array from response
            
            // DIAGNOSTIC: Log received data details
            if (data.length > 0) {
            }

            // Warn if no data returned
            if (data.length === 0) {
              logWarn(`[Historian] ⚠️ No data found for ${tag.id} in range ${startParam} to ${endParam}`);
              logWarn(`[Historian] 💡 Tip: Check if data exists in this date range or try a larger time window`);
            }

            if (data && data.length > 0) {
              // INDUSTRY STANDARD: Cache limit check (50K points max per tag)
              if (data.length > 50000) {
                logWarn(`[Historian] ⚠️ Data exceeds cache limit. Received ${data.length} points, keeping 50000`);
                data.length = 50000; // Truncate to cache limit
              }
              
              // Transform historian data to trend format WITH DATE for historian mode
              // IMPORTANT: Include min/max/count for aggregated data (used in tooltips and bands)
              // Filter out null-value points (can occur if data stored as value_text before fix)
              const trendData = data
                .filter((point: any) => point.value !== null && point.value !== undefined && !isNaN(parseFloat(point.value)))
                .map((point: any) => ({
                time: formatHistorianTimestamp(point.timestamp || point.time, showMilliseconds),
                value: typeof point.value === 'number' ? point.value : parseFloat(point.value),
                min: point.min !== undefined && point.min !== null ? (typeof point.min === 'number' ? point.min : parseFloat(point.min)) : undefined,
                max: point.max !== undefined && point.max !== null ? (typeof point.max === 'number' ? point.max : parseFloat(point.max)) : undefined,
                count: point.count !== undefined ? point.count : undefined,
                rawTimestamp: point.timestamp || point.time // Keep raw timestamp for sorting
              }));

              // Update trend data
              trendDataRef.current[tag.id] = trendData;
              historianUpdates[tag.id] = trendData;
            } else {
              logWarn(`[Historian] ⚠️ No data returned for ${tag.id} - empty chart will be shown`);
              historianUpdates[tag.id] = [];
            }

          } catch (error) {
            logError(`[Historian] Error fetching data for ${tag.id}:`, error);
          }
        }
      }
      setHistorianTrendData(prev => ({ ...prev, ...historianUpdates }));
      // Force React to re-render so charts read the updated trendDataRef
      setHistorianRenderKey(k => k + 1);
    };

    // Debounce: Wait 500ms after chartStates changes before fetching
    const timer = setTimeout(fetchHistorianData, 500);
    return () => clearTimeout(timer);
  }, [chartStates, selectedTags, showMilliseconds]);

  // Handler for AssetSidebar selection
  const handleAssetSelect = (id: string, node?: any) => {
    logInfo('[IndustrialHMI] Asset selected:', id, node);
    setSelectedEquipment(id);
    setSelectedNode(node || null);
    if (node && node.type === 'component') {
      setSelectedAsset(node);
    }
  };

  // Handler for tag toggle (configurable max tags) - Works across ALL plants
  const handleTagToggle = (tagId: string, tagData?: any) => {
    const tagIdStr = String(tagId);
    const tagIds = selectedTags.map(t => String(t.id));
    
    logInfo('[IndustrialHMI] 🏷️ Tag toggle:', tagId);
    logInfo('[IndustrialHMI] 📋 Tag data received:', tagData);
    
    if (tagIds.includes(tagIdStr)) {
      // Deselect
      logInfo('[IndustrialHMI] ❌ Deselecting tag:', tagIdStr);
      setSelectedTags(prev => {
        const updated = prev.filter(t => String(t.id) !== tagIdStr);
        selectedTagsRef.current = updated;
        persistTagIdsToStorage(updated);
        return updated;
      });
    } else {
      // Select (max limit)
      if (selectedTags.length >= MAX_SELECTED_TAGS) {
        alert(`Maximum ${MAX_SELECTED_TAGS} tags allowed for trend display`);
        return;
      }
      
      // Extract unit from tag data - check all possible field names
      const unit = tagData?.eng_unit || tagData?.unit || tagData?.engUnit || '';
      logInfo('[IndustrialHMI] 🔧 Extracted unit:', unit);
      
      // ISA-101: Extract contextual information for situation awareness
      const plant = tagData?.plant || '';
      const area = tagData?.area || '';
      const equipment = tagData?.equipment || '';
      logInfo('[IndustrialHMI] 📍 Context:', { plant, area, equipment });
      
      // Create tag object with data from AssetSidebar
      const newTag: Tag = {
        id: tagIdStr,
        name: tagData?.tag_name || tagData?.tagName || tagData?.description || tagIdStr,
        description: tagData?.description || '',
        value: tagData?.value || 0,
        unit: unit,
        hiLimit: tagData?.hi_limit || tagData?.hiLimit || 100,
        loLimit: tagData?.lo_limit || tagData?.loLimit || 0,
        status: 'normal',
        mode: 'auto',
        plant: plant,
        area: area,
        equipment: equipment,
        // If a trend window is active/targeted, assign tag to it (allows cross-unit mixing)
        windowId: tagData?._forceWindowId ?? activeTrendWindowId ?? undefined
      };
      logInfo('[IndustrialHMI] ✅ Created tag:', newTag);
      setSelectedTags(prev => {
        const updated = [...prev, newTag];
        selectedTagsRef.current = updated;
        persistTagIdsToStorage(updated);
        return updated;
      });
    }
  };

  const toggleNode = (id: string) => {
    setExpandedNodes(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleTagSelection = (tag: Tag) => {
    setSelectedTags(prev => {
      const exists = prev.find(t => t.id === tag.id);
      if (exists) {
        // Deselect
        const updated = prev.filter(t => t.id !== tag.id);
        selectedTagsRef.current = updated;
        persistTagIdsToStorage(updated);
        return updated;
      } else {
        // Select (max tags)
        if (prev.length >= MAX_SELECTED_TAGS) {
          alert(`Maximum ${MAX_SELECTED_TAGS} tags allowed for trend display`);
          return prev;
        }
        const updated = [...prev, tag];
        selectedTagsRef.current = updated;
        persistTagIdsToStorage(updated);
        return updated;
      }
    });
  };

  const acknowledgeAlarm = async (id: string) => {
    // Optimistically update UI
    setAlarms(prev => prev.map(alm => alm.id === id ? { ...alm, acknowledged: true } : alm));
    
    try {
      // Find the alarm to get full details
      const alarm = alarms.find(a => a.id === id);
      if (!alarm) {
        logError('Alarm not found:', id);
        return;
      }
      
      // Log to audit trail
      if (user?.id && user?.username) {
        const numericUserId = Number(user.id);
        if (Number.isNaN(numericUserId)) {
          logError('Invalid user id for audit logging:', user.id);
        } else {
        await auditService.logAlarmAcknowledgment(
          numericUserId,
          user.username,
          alarm.id,
          alarm.tagId,
          alarm.message,
          alarm.priority,
          sessionId || undefined
        );
        }
      }
      
      // Call API to persist acknowledgment
      // Flask endpoint: POST /api/alarm/acknowledge/<alarm_id>
      const authToken = localStorage.getItem('auth_token') || '';
      const response = await fetch(`${API_ROOT}/alarm/acknowledge/${alarm.id}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${authToken}`
        },
        body: JSON.stringify({
          notes: `Acknowledged by ${user?.username || 'operator'} via HMI`
        })
      });
      
      const result = await response.json();
      
      if (result.success) {
        logInfo(`✅ Alarm ${id} acknowledged successfully in database`);
      } else {
        logError(`❌ Failed to acknowledge alarm ${id}:`, result.error);
        // Revert optimistic update on failure
        setAlarms(prev => prev.map(alm => alm.id === id ? { ...alm, acknowledged: false } : alm));
      }
    } catch (error) {
      logError('Error acknowledging alarm:', error);
      // Revert optimistic update on error
      setAlarms(prev => prev.map(alm => alm.id === id ? { ...alm, acknowledged: false } : alm));
    }
  };

  // Helper function to get or initialize chart state for a unit
  const getChartState = (unit: string) => {
    if (!chartStates[unit]) {
      return {
        dataMode: 'live' as const,
        timeRange: 5, // Default: 5 minutes for historian mode
        showCustomDatePicker: false,
        customStartDate: '',
        customEndDate: '',
        showMinMaxBand: false,
        scrollOffset: 0
      };
    }
    return chartStates[unit];
  };

  // Helper function to update chart state for a specific unit
  const updateChartState = (unit: string, updates: Partial<typeof chartStates[string]>) => {
    setChartStates(prev => ({
      ...prev,
      [unit]: {
        ...getChartState(unit),
        ...updates
      }
    }));
  };

  /**
   * Get all selected tags that belong to a chart window.
   * For win_ windows: match by tag.windowId
   * For unit-based windows: match by cleaned tag.unit
   */
  const getTagsForWindow = (unit: string): Tag[] => {
    if (unit.startsWith('win_')) {
      return selectedTags.filter(t => t.windowId === unit);
    }
    return selectedTags.filter(t => {
      const cleaned = (t.unit || '').replace(/^\d+\s*/, '').trim();
      return cleaned === unit || t.unit === unit;
    });
  };

  const handleTimeRangeChange = (unit: string, minutes: number) => {
    updateChartState(unit, {
      timeRange: minutes,
      showCustomDatePicker: false,
      customStartDate: '',
      customEndDate: ''
    });
  };

  const handleCustomDateApply = (unit: string) => {
    const state = getChartState(unit);
    
    if (state.customStartDate && state.customEndDate) {
      // Date input gives us "2026-02-01" format - pass as-is
      const startDate = state.customStartDate; // e.g., "2026-02-01"
      const endDate = state.customEndDate;     // e.g., "2026-02-03"
      
      // Validate date range
      if (startDate >= endDate) {
        alert('Start date must be before end date');
        return;
      }
      
      // Calculate days for validation
      const start = new Date(startDate);
      const end = new Date(endDate);
      const diffDays = Math.ceil((end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24));
      
      // Validate max range (1 year)
      if (diffDays > 365) {
        alert('Maximum date range is 1 year (365 days)');
        return;
      }
      
      // CRITICAL: Clear existing trend data for this unit to force fresh fetch
      const tagsForUnit = getTagsForWindow(unit);
      tagsForUnit.forEach(tag => {
        if (trendDataRef.current[tag.id]) {
          logDebug(`[Custom Range] 🗑️ Clearing cached data for ${tag.id} before applying custom range`);
          delete trendDataRef.current[tag.id];
        }
      });
      
      logDebug(`[Custom Range] ✅ Applying custom range: ${startDate} to ${endDate} for unit ${unit}`);
      
      updateChartState(unit, {
        showCustomDatePicker: false,
        customStartDate: startDate,
        customEndDate: endDate
      });
    } else {
      logError(`[Custom Range] ❌ ERROR: customStartDate or customEndDate is empty!`);
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'normal': return ISA_COLORS.valueNormal;
      case 'warning': return ISA_COLORS.valueWarning;
      case 'alarm': return ISA_COLORS.valueAlarm;
      default: return ISA_COLORS.valueDisabled;
    }
  };

  const renderAssetTree = (assets: Asset[], level = 0) => {
    return assets.map(asset => {
      const isExpanded = expandedNodes.has(asset.id);
      const hasChildren = (asset.children && asset.children.length > 0) || (asset.tags && asset.tags.length > 0);
      
      return (
        <div key={asset.id}>
          <div
            className="flex items-center hover:bg-white/5 cursor-pointer"
            style={{
              paddingLeft: `${level * 16 + 8}px`,
              height: '32px',
              borderBottom: `1px solid ${ISA_COLORS.border}`,
              backgroundColor: selectedAsset?.id === asset.id ? 'rgba(255,255,255,0.1)' : 'transparent'
            }}
            onClick={() => {
              if (hasChildren) toggleNode(asset.id);
              if (asset.type === 'component') setSelectedAsset(asset);
            }}
          >
            <span style={{ width: '16px', fontSize: '10px', color: ISA_COLORS.foreground }}>
              {hasChildren && (isExpanded ? '▼' : '▶')}
            </span>
            <span style={{ 
              fontSize: '11px', 
              fontFamily: 'Consolas, monospace',
              color: ISA_COLORS.foreground,
              fontWeight: asset.type === 'equipment' ? 700 : 400,
              textTransform: 'uppercase'
            }}>
              {asset.name}
            </span>
          </div>
          
          {isExpanded && asset.children && renderAssetTree(asset.children, level + 1)}
          
          {isExpanded && asset.tags && asset.tags.map(tag => (
            <div
              key={tag.id}
              className="flex items-center hover:bg-white/5 cursor-pointer"
              style={{
                paddingLeft: `${(level + 1) * 16 + 24}px`,
                height: '28px',
                borderBottom: `1px solid ${ISA_COLORS.border}`,
                backgroundColor: selectedTags.find(t => t.id === tag.id) ? 'rgba(255,255,255,0.1)' : 'transparent',
                borderLeft: `3px solid ${getStatusColor(tag.status)}`
              }}
              onClick={() => toggleTagSelection(tag)}
            >
              <Activity style={{ width: '12px', height: '12px', marginRight: '6px', color: getStatusColor(tag.status) }} />
              <span style={{ 
                fontSize: '10px', 
                fontFamily: 'Consolas, monospace',
                color: ISA_COLORS.foreground
              }}>
                {tag.name}
              </span>
              {selectedTags.find(t => t.id === tag.id) && (
                <span style={{ 
                  marginLeft: 'auto',
                  marginRight: '8px',
                  width: '12px',
                  height: '12px',
                  borderRadius: '50%',
                  backgroundColor: TAG_TREND_COLORS[selectedTags.findIndex(t => t.id === tag.id) % TAG_TREND_COLORS.length]
                }} />
              )}
            </div>
          ))}
        </div>
      );
    });
  };

  const unacknowledgedAlarms = alarms.filter(a => !a.acknowledged);
  const activeP1Alarm = unacknowledgedAlarms.find(a => a.priority === 1);

  return (
    <div style={{ 
      width: '100vw', 
      height: '100vh', 
      backgroundColor: ISA_COLORS.background,
      color: ISA_COLORS.foreground,
      fontFamily: 'Arial, sans-serif',
      display: 'flex',
      flexDirection: 'column',
      overflow: 'hidden'
    }}>
      {/* Global connection health banner — shows when MQTT/Flask is down or data is stale */}
      <ConnectionHealthBanner />

      {/* Shift Warning Notification */}
      <ShiftWarningNotification />
      
      {/* SYSTEM STATUS BAR */}
      <div style={{
        height: '40px',
        backgroundColor: ISA_COLORS.panel,
        borderBottom: `2px solid ${ISA_COLORS.border}`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 16px',
        fontSize: '12px',
        fontFamily: 'Consolas, monospace'
      }}>
        <div style={{ display: 'flex', gap: '24px', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <div style={{
              width: '12px', height: '12px', borderRadius: '50%',
              backgroundColor: !connHealth.socketConnected
                ? ISA_COLORS.statusOffline
                : connHealth.dataIsStale
                  ? '#ffaa00'
                  : ISA_COLORS.statusOnline,
              boxShadow: connHealth.socketConnected && !connHealth.dataIsStale
                ? `0 0 5px ${ISA_COLORS.statusOnline}` : 'none',
            }} />
            <span style={{ color: !connHealth.socketConnected ? ISA_COLORS.statusOffline : connHealth.dataIsStale ? '#ffaa00' : ISA_COLORS.statusOnline }}>
              MQTT: {!connHealth.socketConnected
                ? (connHealth.reconnectAttempts > 0 ? `RECONNECTING #${connHealth.reconnectAttempts}` : 'OFFLINE')
                : connHealth.dataIsStale ? 'DATA STALE' : 'LIVE'}
            </span>
            {connHealth.flaskReachable === false && (
              <span style={{ color: ISA_COLORS.statusOffline, marginLeft: 4 }}>| FLASK API DOWN</span>
            )}
            {opcFailed && connHealth.flaskReachable !== false && (
              <span style={{ color: '#ff4444', marginLeft: 4, fontWeight: 700 }}>| OPC REST FAIL</span>
            )}
            {plcFailed && (
              <span style={{ color: '#ff8800', marginLeft: 4, fontWeight: 700 }}>| PLC REST FAIL</span>
            )}
            {usingRestFallback && !opcFailed && (
              <span style={{ color: '#ffaa00', marginLeft: 4, fontSize: '10px' }}>| REST FALLBACK ACTIVE</span>
            )}
            {/* OPC Server disconnected */}
            {!opcPlcStatus.loading && opcPlcStatus.opc && !opcPlcStatus.opc.connected && (
              <span style={{
                color: '#ff2222',
                marginLeft: 8,
                fontWeight: 700,
                fontSize: '11px',
                padding: '2px 7px',
                border: '1px solid #ff2222',
                borderRadius: '3px',
                backgroundColor: 'rgba(255,34,34,0.12)',
                animation: 'pulse 1.5s infinite',
              }}>
                ⚠ OPC {opcPlcStatus.opc.status?.toUpperCase() || 'DISCONNECTED'}
              </span>
            )}
            {/* PLC(s) disconnected */}
            {!opcPlcStatus.loading && opcPlcStatus.anyPlcDisconnected && opcPlcStatus.plcs
              .filter(p => !p.connected && !p.isNoPlcSentinel)
              .map(p => (
                <span key={p.id} style={{
                  color: '#ff7700',
                  marginLeft: 8,
                  fontWeight: 700,
                  fontSize: '11px',
                  padding: '2px 7px',
                  border: '1px solid #ff7700',
                  borderRadius: '3px',
                  backgroundColor: 'rgba(255,119,0,0.12)',
                  animation: 'pulse 1.5s infinite',
                }}>
                  ⚠ PLC {p.name || p.id}: NOT CONNECTED
                </span>
              ))
            }
            {/* Gap 8: PLC(s) connected but in PROGRAM mode / frozen (no value changes >30s) */}
            {!opcPlcStatus.loading && opcPlcStatus.plcs
              .filter(p => p.connected && p.mode === 'FROZEN')
              .map(p => (
                <span key={`frozen-${p.id}`} style={{
                  color: '#ffaa00',
                  marginLeft: 8,
                  fontWeight: 700,
                  fontSize: '11px',
                  padding: '2px 7px',
                  border: '1px solid #ffaa00',
                  borderRadius: '3px',
                  backgroundColor: 'rgba(255,170,0,0.15)',
                  animation: 'pulse 1.5s infinite',
                }} title={`No tag value has changed for ${Math.round(p.frozenForMs/1000)}s — controller likely in PROGRAM mode or scan halted`}>
                  ⚠ PLC {p.name || p.id}: PROGRAM/FROZEN ({Math.round(p.frozenForMs/1000)}s)
                </span>
              ))
            }
            {/* Gap 7: No PLC configured at all */}
            {!opcPlcStatus.loading && opcPlcStatus.noPlcConfigured && (
              <span style={{
                color: '#ff2222',
                marginLeft: 8,
                fontWeight: 700,
                fontSize: '11px',
                padding: '2px 7px',
                border: '1px solid #ff2222',
                borderRadius: '3px',
                backgroundColor: 'rgba(255,34,34,0.18)',
                animation: 'pulse 1.5s infinite',
              }}>
                ⛔ NO PLC CONFIGURED — contact engineering
              </span>
            )}
          </div>
          {/* Per-source OPC/PLC badges — only shown for sources that have enabled tags in DB.
              DISCONNECTED = tags are configured for this source but no fresh data is arriving.
              If source has no configured tags in DB, it is never shown here. */}
          {sourceStatuses.map(src => (
            <div key={src.server_progid} style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
              <div style={{
                width: '10px', height: '10px', borderRadius: '50%',
                backgroundColor: src.status === 'live' ? '#00c851' : '#ff4444',
                boxShadow: src.status === 'live' ? '0 0 5px #00c851' : '0 0 5px #ff4444',
              }} />
              <span style={{
                fontSize: '11px', fontWeight: 700, letterSpacing: '0.5px',
                color: src.status === 'live' ? '#00c851' : '#ff4444',
              }}>
                {src.server_progid}: {src.status === 'live' ? 'LIVE' : 'DISCONNECTED'}
              </span>
            </div>
          ))}
          {sourceStatuses.length === 0 && opcConnectionState !== 'Unknown' && (
            <span style={{ fontSize: '10px', color: '#888' }}>NO SOURCES CONFIGURED</span>
          )}
          <div style={{ display: 'flex', gap: '16px', marginLeft: '24px' }}>
            <span style={{ color: ISA_COLORS.alarmP1, fontWeight: 700 }}>P1: {systemStatus.alarmCount.p1}</span>
            <span style={{ color: ISA_COLORS.alarmP2, fontWeight: 700 }}>P2: {systemStatus.alarmCount.p2}</span>
            <span style={{ color: ISA_COLORS.alarmP3, fontWeight: 700 }}>P3: {systemStatus.alarmCount.p3}</span>
          </div>
          
          {/* Selected Tags Counter */}
          {selectedTags.length > 0 && (
            <>
              <div style={{ width: '1px', height: '24px', backgroundColor: ISA_COLORS.border, marginLeft: '16px' }} />
              <div style={{
                padding: '6px 12px',
                backgroundColor: 'rgba(0, 200, 81, 0.2)',
                border: '1px solid ' + ISA_COLORS.statusOnline,
                color: ISA_COLORS.statusOnline,
                fontSize: '11px',
                fontWeight: 700,
                textTransform: 'uppercase',
                display: 'flex',
                alignItems: 'center',
                gap: '6px'
              }}>
                <Activity style={{ width: '14px', height: '14px' }} />
                SELECTED: {selectedTags.length}/{MAX_SELECTED_TAGS}
              </div>
            </>
          )}
          
          {/* DEBUG BUTTON - ISA-101 Compliance Check */}
          <div style={{ width: '1px', height: '24px', backgroundColor: ISA_COLORS.border, marginLeft: '16px', display: 'none' }} />
          <button
            onClick={() => setShowDebugPanel(!showDebugPanel)}
            style={{
              padding: '6px 12px',
              backgroundColor: showDebugPanel ? 'rgba(255, 170, 0, 0.3)' : 'rgba(96, 165, 250, 0.2)',
              border: '1px solid ' + (showDebugPanel ? '#ffaa00' : '#60a5fa'),
              color: showDebugPanel ? '#ffaa00' : '#60a5fa',
              fontSize: '11px',
              fontWeight: 700,
              textTransform: 'uppercase',
              cursor: 'pointer',
              borderRadius: '4px',
              display: 'none',
              alignItems: 'center',
              gap: '6px'
            }}
          >
            🐛 DEBUG {showDebugPanel ? 'ON' : 'OFF'}
          </button>

        </div>
        <div style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
          <span>{currentTime.toLocaleString('en-US', { hour12: false, month: '2-digit', day: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>
          {/* PLC MODE — real per-PLC mode from C# backend (Gap 8).
              RUN = green, FROZEN = orange (controller in PROGRAM mode / scan halted),
              DISCONNECTED = red, UNKNOWN = grey. */}
          {(() => {
            const plcs = opcPlcStatus.plcs.filter(p => !p.isNoPlcSentinel);
            if (opcPlcStatus.loading || plcs.length === 0) {
              return <span style={{ color: '#888' }}>MODE: —</span>;
            }
            return plcs.map(p => {
              let color = '#888';
              let label = 'UNKNOWN';
              let title = `${p.name || p.id}: mode unknown`;
              if (!p.connected) {
                color = '#ff2222'; label = 'DISCONNECTED';
                title = `${p.name || p.id}: ${p.lastError || 'disconnected'}`;
              } else if (p.mode === 'FROZEN') {
                color = '#ffaa00'; label = `FROZEN ${Math.round(p.frozenForMs/1000)}s`;
                title = `${p.name || p.id}: no tag value has changed for ${Math.round(p.frozenForMs/1000)}s — controller likely in PROGRAM mode or scan halted`;
              } else if (p.mode === 'RUN') {
                color = '#00c851'; label = 'RUN';
                title = `${p.name || p.id}: RUN (values changing)`;
              } else {
                label = p.mode || 'UNKNOWN';
              }
              return (
                <span key={`mode-${p.id}`} title={title} style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 6,
                  color,
                  fontWeight: 700,
                  fontSize: '11px',
                  padding: '2px 7px',
                  border: `1px solid ${color}`,
                  borderRadius: '3px',
                  backgroundColor: `${color}1f`,
                }}>
                  <span style={{
                    width: 8, height: 8, borderRadius: '50%',
                    backgroundColor: color, boxShadow: `0 0 5px ${color}`,
                  }} />
                  MODE: {label}
                </span>
              );
            });
          })()}

          {/* Admin Link */}
          {user?.isAdmin && (
            <>
              <div style={{ width: '1px', height: '24px', backgroundColor: ISA_COLORS.border }} />
              <Link to="/admin" style={{ textDecoration: 'none' }}>
                <button
                  style={{
                    padding: '6px 12px',
                    backgroundColor: 'rgba(139, 92, 246, 0.2)',
                    color: '#A78BFA',
                    border: '1px solid #A78BFA',
                    cursor: 'pointer',
                    fontWeight: 700,
                    fontSize: '11px',
                    textTransform: 'uppercase',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                    fontFamily: 'Consolas, monospace'
                  }}
                >
                  <Shield style={{ width: '14px', height: '14px' }} />
                  ADMIN
                </button>
              </Link>
            </>
          )}
          
          <div style={{ width: '1px', height: '24px', backgroundColor: ISA_COLORS.border }} />
          
          {/* User Header Component */}
          <div style={{ transform: 'scale(0.9)' }}>
            <UserHeader />
          </div>
        </div>
      </div>

      {/* MAIN CONTENT */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* LEFT - DB-CONNECTED ASSET SIDEBAR */}
        {
          <AssetSidebar
            selectedId={selectedEquipment}
            onSelect={handleAssetSelect}
            selectedTags={selectedTags.map(t => String(t.id))}
            onTagToggle={handleTagToggle}
            liveTagValues={liveTagValues}
            onTagOpenNewWindow={(tagId, tagData) => {
              // Create a brand-new unique window ID so this tag gets its own chart below existing ones
              const newWindowId = `win_${Date.now()}_${tagId}`;
              handleTagToggle(tagId, { ...tagData, _forceWindowId: newWindowId });
            }}
            onContextMenuRequest={(state) => {
              openPredictiveTrend(state.tagId, state.tagData?.name ?? state.tagId);
            }}
          />
        }

        {/* CENTER - TRENDS / ANALYTICS / PREDICTIVE TABS */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>

          {/* ── Professional Tab Bar ── */}
          <div style={{
            display: 'flex',
            alignItems: 'stretch',
            borderBottom: '1px solid #1F2937',
            backgroundColor: '#080D14',
            flexShrink: 0,
            height: '38px',
            paddingLeft: '4px',
          }}>
            {/* TRENDS — always visible */}
            <button
              onClick={() => setCenterTab('trends')}
              style={{
                display: 'flex', alignItems: 'center', gap: '6px',
                padding: '0 18px',
                fontSize: '10.5px', fontWeight: 700, letterSpacing: '0.9px',
                cursor: 'pointer', background: 'none', border: 'none',
                borderBottom: centerTab === 'trends' ? '2px solid #3B82F6' : '2px solid transparent',
                borderTop: '2px solid transparent',
                color: centerTab === 'trends' ? '#60A5FA' : '#4B5563',
                fontFamily: 'Consolas, monospace', textTransform: 'uppercase',
                transition: 'color 0.15s, border-color 0.15s',
                whiteSpace: 'nowrap',
              }}
            >
              TRENDS
            </button>

            {/* Divider */}
            <div style={{ width: '1px', backgroundColor: '#1F2937', margin: '8px 2px' }} />

            {/* ANALYTICS — hidden from Viewer */}
            {canViewAnalytics && (
              <button
                onClick={() => setCenterTab('analytics')}
                style={{
                  display: 'flex', alignItems: 'center', gap: '6px',
                  padding: '0 18px',
                  fontSize: '10.5px', fontWeight: 700, letterSpacing: '0.9px',
                  cursor: 'pointer', background: 'none', border: 'none',
                  borderBottom: centerTab === 'analytics' ? '2px solid #F59E0B' : '2px solid transparent',
                  borderTop: '2px solid transparent',
                  color: centerTab === 'analytics' ? '#FCD34D' : '#4B5563',
                  fontFamily: 'Consolas, monospace', textTransform: 'uppercase',
                  transition: 'color 0.15s, border-color 0.15s',
                  whiteSpace: 'nowrap',
                  position: 'relative',
                }}
              >
                ANALYTICS
                {centerTab === 'analytics' && (
                  <span style={{
                    marginLeft: '4px', fontSize: '8px', fontWeight: 700,
                    backgroundColor: '#78350F', color: '#FCD34D',
                    padding: '1px 5px', borderRadius: '3px', letterSpacing: '0.5px',
                  }}>LIVE</span>
                )}
              </button>
            )}

            {/* PREDICTIVE — hidden from Viewer */}
            {canViewAnalytics && (
              <>
                <div style={{ width: '1px', backgroundColor: '#1F2937', margin: '8px 2px' }} />
                <button
                  onClick={() => setCenterTab('predictive')}
                  style={{
                    display: 'flex', alignItems: 'center', gap: '6px',
                    padding: '0 18px',
                    fontSize: '10.5px', fontWeight: 700, letterSpacing: '0.9px',
                    cursor: 'pointer', background: 'none', border: 'none',
                    borderBottom: centerTab === 'predictive' ? '2px solid #8B5CF6' : '2px solid transparent',
                    borderTop: '2px solid transparent',
                    color: centerTab === 'predictive' ? '#C4B5FD' : '#4B5563',
                    fontFamily: 'Consolas, monospace', textTransform: 'uppercase',
                    transition: 'color 0.15s, border-color 0.15s',
                    whiteSpace: 'nowrap',
                  }}
                >
                  PREDICTIVE
                  {centerTab === 'predictive' && (
                    <span style={{
                      marginLeft: '4px', fontSize: '8px', fontWeight: 700,
                      backgroundColor: '#4C1D95', color: '#C4B5FD',
                      padding: '1px 5px', borderRadius: '3px', letterSpacing: '0.5px',
                    }}>EWM</span>
                  )}
                </button>
              </>
            )}

            {/* REPORTS — opens in new tab */}
            {canViewReports && (
              <>
                <div style={{ width: '1px', backgroundColor: '#1F2937', margin: '8px 2px' }} />
                <button
                  onClick={() => window.open('/reports/daily', '_blank')}
                  style={{
                    display: 'flex', alignItems: 'center', gap: '6px',
                    padding: '0 18px',
                    fontSize: '10.5px', fontWeight: 700, letterSpacing: '0.9px',
                    cursor: 'pointer', background: 'none', border: 'none',
                    borderBottom: '2px solid transparent',
                    borderTop: '2px solid transparent',
                    color: '#4B5563',
                    fontFamily: 'Consolas, monospace', textTransform: 'uppercase',
                    transition: 'color 0.15s',
                    whiteSpace: 'nowrap',
                  }}
                  onMouseEnter={e => (e.currentTarget.style.color = '#34D399')}
                  onMouseLeave={e => (e.currentTarget.style.color = '#4B5563')}
                >
                  REPORTS ↗
                </button>
              </>
            )}
          </div>

          {/* ANALYTICS tab content */}
          {centerTab === 'analytics' && canViewAnalytics && (
            <div style={{ flex: 1, overflow: 'hidden', backgroundColor: '#0d1117' }}>
              <HmiAnalyticsTab onTagClick={openPredictiveTrend} />
            </div>
          )}

          {/* PREDICTIVE tab content */}
          {centerTab === 'predictive' && canViewAnalytics && (
            <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column', backgroundColor: '#0d1117' }}>
              <PredictiveAlarmPanel />
            </div>
          )}

          {/* TRENDS tab */}
          <div style={{ flex: 1, overflow: 'auto', display: centerTab === 'trends' ? 'block' : 'none' }}>
          {selectedTags.length > 0 ? (
            <div style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {/* TAG FACEPLATES - Show first selected tag in detail */}
              {selectedTags.length === 1 && (
              <div style={{
                backgroundColor: ISA_COLORS.panel,
                border: `2px solid ${ISA_COLORS.border}`,
                boxShadow: 'inset 0 2px 4px rgba(0,0,0,0.5), inset 0 -2px 4px rgba(255,255,255,0.05)'
              }}>
                <div style={{
                  padding: '12px 16px',
                  borderBottom: `2px solid ${ISA_COLORS.border}`,
                  backgroundColor: 'rgba(0,0,0,0.3)',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center'
                }}>
                  <div>
                    <span style={{ fontWeight: 700, fontSize: '16px', fontFamily: 'Consolas, monospace' }}>{selectedTags[0].name}</span>
                    <span style={{ marginLeft: '16px', fontSize: '13px', color: ISA_COLORS.foreground }}>{selectedTags[0].description}</span>
                  </div>
                  <div style={{
                    padding: '4px 12px',
                    backgroundColor: getStatusColor(selectedTags[0].status),
                    color: '#000000',
                    fontWeight: 700,
                    fontSize: '12px'
                  }}>
                    {selectedTags[0].status.toUpperCase()}
                  </div>
                </div>
                
                <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  {/* DIGITAL VALUE DISPLAY */}
                  <div style={{ textAlign: 'center' }}>
                    <div style={{
                      fontSize: '56px',
                      fontFamily: 'Digital-7, Consolas, monospace',
                      color: getStatusColor(selectedTags[0].status),
                      textShadow: `0 0 10px ${getStatusColor(selectedTags[0].status)}`,
                      fontWeight: 700,
                      letterSpacing: '4px'
                    }}>
                      {(() => {
                        const liveValue = liveTagValues[selectedTags[0].id];
                        const displayValue = liveValue?.value ?? selectedTags[0].value ?? 0;
                        const _n = typeof displayValue === 'number' ? displayValue : parseFloat(displayValue);
                        const isStale = liveValue && (
                          liveValue.quality === 'Stale' || liveValue.quality === 'STALE' ||
                          liveValue.quality === 'Uncertain' || liveValue.quality === 'UNCERTAIN'
                        );
                        return (
                          <span style={{ color: isStale ? '#6b7280' : undefined, opacity: isStale ? 0.6 : 1 }}>
                            {!isNaN(_n) ? _n.toFixed(3) : displayValue}
                          </span>
                        );
                      })()}
                    </div>
                    {/* Gap 2: STALE badge for single-tag display */}
                    {(() => {
                      const liveValue = liveTagValues[selectedTags[0].id];
                      const isStale = liveValue && (
                        liveValue.quality === 'Stale' || liveValue.quality === 'STALE' ||
                        liveValue.quality === 'Uncertain' || liveValue.quality === 'UNCERTAIN'
                      );
                      return isStale ? (
                        <div style={{ fontSize: '11px', color: '#f59e0b', backgroundColor: '#78350f44', border: '1px solid #f59e0b', borderRadius: '4px', padding: '2px 6px', marginTop: '4px', letterSpacing: '1px', fontWeight: 600 }}>
                          ⚠ STALE
                        </div>
                      ) : null;
                    })()}
                    <div style={{ fontSize: '20px', color: ISA_COLORS.foreground, marginTop: '8px' }}>
                      {selectedTags[0].unit || liveTagValues[selectedTags[0].id]?.unit || ''}
                    </div>
                  </div>
                </div>
              </div>
              )}

              {/* MULTI-TAG SUMMARY - Show when multiple tags selected */}
              {selectedTags.length > 1 && (
                <div style={{
                  backgroundColor: ISA_COLORS.panel,
                  border: `2px solid ${ISA_COLORS.border}`,
                  boxShadow: 'inset 0 2px 4px rgba(0,0,0,0.5)'
                }}>
                  <div style={{
                    padding: '12px 16px',
                    borderBottom: `2px solid ${ISA_COLORS.border}`,
                    backgroundColor: 'rgba(0,0,0,0.3)',
                    fontWeight: 700,
                    fontSize: '13px',
                    textTransform: 'uppercase'
                  }}>
                    SELECTED TAGS ({selectedTags.length}/{MAX_SELECTED_TAGS})
                  </div>
                  <div style={{ 
                    padding: '16px', 
                    display: 'grid', 
                    gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', 
                    gap: '12px',
                    maxHeight: '400px',
                    overflowY: 'auto',
                    overflowX: 'hidden'
                  }}>
                    {selectedTags.map((tag, index) => (
                      <div key={tag.id} style={{
                        padding: '14px',
                        background: 'linear-gradient(135deg, rgba(15, 23, 42, 0.9) 0%, rgba(10, 15, 30, 0.9) 100%)',
                        border: `3px solid ${TAG_TREND_COLORS[index % TAG_TREND_COLORS.length]}`,
                        borderRadius: '6px',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '10px',
                        boxShadow: `0 0 10px ${TAG_TREND_COLORS[index % TAG_TREND_COLORS.length]}33`
                      }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                          <div style={{
                            width: '14px',
                            height: '14px',
                            borderRadius: '50%',
                            backgroundColor: TAG_TREND_COLORS[index % TAG_TREND_COLORS.length],
                            boxShadow: `0 0 8px ${TAG_TREND_COLORS[index % TAG_TREND_COLORS.length]}`,
                            border: '2px solid rgba(0,0,0,0.5)'
                          }} />
                          <span style={{ 
                            fontFamily: 'Consolas, monospace', 
                            fontSize: '13px', 
                            fontWeight: 700,
                            color: TAG_TREND_COLORS[index % TAG_TREND_COLORS.length],
                            letterSpacing: '0.3px'
                          }}>
                            {tag.name}
                          </span>
                        </div>
                        <div style={{ 
                          fontSize: '11px', 
                          color: ISA_COLORS.foreground,
                          opacity: 0.8,
                          fontFamily: 'Consolas, monospace'
                        }}>
                          {tag.description}
                        </div>
                        {/* ISA-101: Display contextual information for situation awareness */}
                        {(tag.plant || tag.area || tag.equipment) && (
                          <div style={{ 
                            fontSize: '10px', 
                            color: '#60a5fa',
                            opacity: 0.9,
                            fontFamily: 'Consolas, monospace',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '4px',
                            marginTop: '4px',
                            padding: '4px 6px',
                            backgroundColor: 'rgba(96, 165, 250, 0.1)',
                            borderRadius: '3px',
                            border: '1px solid rgba(96, 165, 250, 0.3)',
                            cursor: 'help'
                          }}
                          title={[tag.plant, tag.area, tag.equipment].filter(Boolean).join(' › ')}
                          >
                            <span style={{ fontSize: '9px' }}>📍</span>
                            <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                              {[tag.plant, tag.area, tag.equipment].filter(Boolean).join(' › ')}
                            </span>
                          </div>
                        )}
                        <div style={{
                          fontSize: '26px',
                          fontFamily: 'Consolas, monospace',
                          color: TAG_TREND_COLORS[index % TAG_TREND_COLORS.length],
                          fontWeight: 700,
                          textShadow: `0 0 10px ${TAG_TREND_COLORS[index % TAG_TREND_COLORS.length]}66`,
                          padding: '8px',
                          backgroundColor: 'rgba(0,0,0,0.4)',
                          borderRadius: '4px',
                          border: `1px solid ${TAG_TREND_COLORS[index % TAG_TREND_COLORS.length]}44`
                        }}>
                          {(() => {
                            // INDUSTRY STANDARD: Always show latest available value
                            // Priority: MQTT live data > Latest historian data > No data indicator
                            const chartState = getChartState(tag.unit);
                            let displayValue, displayUnit;
                            
                            const liveValue = liveTagValues[tag.id];
                            const historianData = trendDataRef.current[tag.id];
                            
                            if (chartState.dataMode === 'live') {
                              // Live mode: prefer MQTT, fallback to latest historian value
                              if (liveValue?.value !== undefined && liveValue.value !== null) {
                                displayValue = liveValue.value;
                                displayUnit = tag.unit || liveValue.unit || '';
                              } else if (historianData && historianData.length > 0) {
                                // No live data, show latest historian value
                                const latestPoint = historianData[historianData.length - 1];
                                displayValue = latestPoint.value;
                                displayUnit = tag.unit || '';
                              } else {
                                // No data available from any source - show placeholder
                                displayValue = '---';
                                displayUnit = tag.unit || '';
                              }
                            } else {
                              // Historian mode: show latest historian value
                              if (historianData && historianData.length > 0) {
                                const latestPoint = historianData[historianData.length - 1];
                                displayValue = latestPoint.value;
                                displayUnit = tag.unit || '';
                              } else {
                                // No historian data yet
                                displayValue = '---';
                                displayUnit = tag.unit || '';
                              }
                            }
                            
                            const _numVal = typeof displayValue === 'number' ? displayValue : parseFloat(displayValue);
                            const formattedValue = !isNaN(_numVal) ? _numVal.toFixed(3) : displayValue;
                            // Remove any leading numbers from unit display (e.g., "0 rpm" -> "rpm")
                            const cleanUnit = displayUnit.replace(/^\d+\s*/, '');
                            const ts = liveTagValues[tag.id]?.timestamp;
                            const tsLabel = ts ? new Date(ts).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : null;
                            // Gap 2: detect stale quality from the live value store
                            const liveQ = liveTagValues[tag.id]?.quality;
                            const isStale = liveQ === 'Stale' || liveQ === 'STALE' ||
                                            liveQ === 'Uncertain' || liveQ === 'UNCERTAIN';
                            return (
                              <>
                                <span style={{ color: isStale ? '#6b7280' : undefined, opacity: isStale ? 0.6 : 1 }}>
                                  {`${formattedValue} ${cleanUnit}`}
                                </span>
                                {isStale && (
                                  <div style={{ fontSize: '8px', color: '#f59e0b', marginTop: '1px', letterSpacing: '0.5px', fontWeight: 600 }}>
                                    ⚠ STALE
                                  </div>
                                )}
                                {tsLabel && (
                                  <div style={{ fontSize: '9px', color: '#6b7280', marginTop: '2px', letterSpacing: '0.5px' }}>
                                    {tsLabel}
                                  </div>
                                )}
                              </>
                            );
                          })()}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* TREND CHARTS - Grouped by Unit */}
              {(() => {
                // Safety check
                if (!selectedTags || selectedTags.length === 0) {
                  return null;
                }
                
                try {
                  // Group tags by windowId (if set) or unit — allows cross-unit mixing per window
                  const tagsByUnit = selectedTags.reduce((acc, tag) => {
                    if (!tag) return acc; // Skip null/undefined tags
                    // Use explicit windowId if tag was dragged/assigned to a window;
                    // otherwise fall back to cleaned unit for auto-grouping
                    let groupKey: string;
                    if (tag.windowId) {
                      groupKey = tag.windowId;
                    } else {
                      const rawUnit = tag.unit || '';
                      groupKey = rawUnit.replace(/^\d+\s*/, '').trim();
                    }
                    if (!acc[groupKey]) {
                      acc[groupKey] = [];
                    }
                    acc[groupKey].push(tag);
                    return acc;
                  }, {} as Record<string, Tag[]>);

                  // Filter out empty groups
                  const validEntries = Object.entries(tagsByUnit).filter(([_, tags]) => tags && tags.length > 0);
                  
                  if (validEntries.length === 0) {
                    return null;
                  }

                  return validEntries.map(([unit, tags]) => {
                    try {
                      const chartState = getChartState(unit);
                      const isActiveTarget = activeTrendWindowId === unit;

                      // Handle tag drop onto this trend window
                      const handleWindowDrop = (e: React.DragEvent) => {
                        e.preventDefault();
                        setIsDraggingTag(false);
                        try {
                          const payload = JSON.parse(e.dataTransfer.getData('application/hmi-tag'));
                          const { tagId, tagData } = payload;
                          // Assign this windowId then add tag
                          setActiveTrendWindowId(unit);
                          // Small defer so state is set before toggle fires
                          setTimeout(() => {
                            handleTagToggle(tagId, { ...tagData, _forceWindowId: unit });
                            setActiveTrendWindowId(null);
                          }, 0);
                        } catch (err) {
                          logError('[DnD] Failed to parse dropped tag', err);
                        }
                      };
                  
                  return (
                  <div
                    key={unit}
                    data-render-key={historianRenderKey}
                    onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; }}
                    onDrop={handleWindowDrop}
                    onDragEnter={() => setIsDraggingTag(true)}
                    onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setIsDraggingTag(false); }}
                    style={{
                      backgroundColor: ISA_COLORS.panel,
                      border: isActiveTarget
                        ? '2px solid #3b82f6'
                        : isDraggingTag ? '2px dashed rgba(59,130,246,0.5)' : `2px solid ${ISA_COLORS.border}`,
                      boxShadow: isActiveTarget ? '0 0 12px rgba(59,130,246,0.4), inset 0 2px 4px rgba(0,0,0,0.5)' : 'inset 0 2px 4px rgba(0,0,0,0.5)'
                    }}
                  >
                    <div style={{
                      padding: '12px 16px',
                      borderBottom: `3px solid ${ISA_COLORS.border}`,
                      background: 'linear-gradient(180deg, rgba(15, 23, 42, 0.95) 0%, rgba(10, 15, 30, 0.95) 100%)',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      boxShadow: '0 2px 4px rgba(0,0,0,0.5)'
                    }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                        <div style={{ 
                          display: 'flex', 
                          alignItems: 'center', 
                          gap: '10px',
                          padding: '6px 12px',
                          backgroundColor: 'rgba(59, 130, 246, 0.15)',
                          border: '2px solid rgba(59, 130, 246, 0.4)',
                          borderRadius: '4px'
                        }}>
                          <TrendingUp style={{ width: '18px', height: '18px', color: '#3b82f6' }} />
                          <span style={{ 
                            fontWeight: 700, 
                            fontSize: '14px', 
                            color: '#60a5fa',
                            letterSpacing: '0.5px',
                            fontFamily: 'Consolas, monospace'
                          }}>
                            TREND - {chartState.dataMode === 'live' ? 'LAST 1 MIN' : (() => {
                              // Check if custom date range is active
                              if (chartState.customStartDate && chartState.customEndDate) {
                                const diffMs = new Date(chartState.customEndDate).getTime() - new Date(chartState.customStartDate).getTime();
                                const diffHrs = Math.floor(diffMs / (1000 * 60 * 60));
                                const diffDays = Math.floor(diffHrs / 24);
                                if (diffDays >= 1) {
                                  return `CUSTOM (${diffDays} DAY${diffDays > 1 ? 'S' : ''}) ✓`;
                                } else {
                                  return `CUSTOM (${diffHrs} HR${diffHrs > 1 ? 'S' : ''}) ✓`;
                                }
                              }
                            })()}
                          </span>
                          
                          {/* INDUSTRIAL STANDARD: Show custom date range details for historian mode */}
                          {chartState.dataMode === 'historian' && chartState.customStartDate && chartState.customEndDate && (() => {
                            const start = new Date(chartState.customStartDate);
                            const end = new Date(chartState.customEndDate);
                            const startStr = start.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
                            const endStr = end.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
                            const tagsForUnit = getTagsForWindow(unit);
                            const totalPoints = tagsForUnit.reduce((sum, tag) => {
                              const data = trendDataRef.current[tag.id];
                              return sum + (data ? data.length : 0);
                            }, 0);
                            
                            return (
                              <span style={{
                                fontWeight: 600,
                                fontSize: '10px',
                                color: '#10b981',
                                backgroundColor: 'rgba(16, 185, 129, 0.15)',
                                padding: '3px 8px',
                                borderRadius: '3px',
                                border: '1px solid rgba(16, 185, 129, 0.4)',
                                fontFamily: 'Consolas, monospace',
                                marginLeft: '8px'
                              }}>
                                📅 {startStr} → {endStr} | {totalPoints.toLocaleString()} pts
                              </span>
                            );
                          })()}
                          
                          {chartState.scrollOffset > 0 && (
                            <span style={{
                              fontWeight: 700,
                              fontSize: '10px',
                              color: '#fbbf24',
                              backgroundColor: 'rgba(251, 191, 36, 0.2)',
                              padding: '2px 6px',
                              borderRadius: '3px',
                              border: '1px solid rgba(251, 191, 36, 0.5)',
                              fontFamily: 'Consolas, monospace'
                            }}>
                              -{chartState.scrollOffset} SCROLLED
                            </span>
                          )}
                          <span style={{ 
                            fontWeight: 700, 
                            fontSize: '13px', 
                            color: '#fbbf24',
                            backgroundColor: 'rgba(251, 191, 36, 0.15)',
                            padding: '2px 8px',
                            borderRadius: '3px',
                            border: '1px solid rgba(251, 191, 36, 0.3)'
                          }}>
                            {/* For windowId-based windows show tag name(s); for unit-based windows show the unit */}
                            {(() => {
                              if (unit.startsWith('win_')) {
                                const names = tags.map(t => t.name || t.id).join(', ');
                                return names || '—';
                              }
                              const cleanedUnit = unit.replace(/^\d+\s*/, '').trim();
                              return (cleanedUnit && cleanedUnit !== 'N/A') ? cleanedUnit : '—';
                            })()}
                          </span>
                        </div>

                        {/* Trend Window Target Button — click to make this the active drop target */}
                        <button
                          title={isActiveTarget ? 'This window is the active target — sidebar clicks/drops go here. Click to deactivate.' : 'Click to make this window the active target for sidebar tags & drag-drop'}
                          onClick={() => setActiveTrendWindowId(prev => prev === unit ? null : unit)}
                          style={{
                            padding: '3px 10px',
                            fontSize: '10px',
                            fontWeight: 700,
                            fontFamily: 'Consolas, monospace',
                            letterSpacing: '0.5px',
                            cursor: 'pointer',
                            borderRadius: '3px',
                            border: isActiveTarget ? '1px solid #3b82f6' : '1px solid rgba(255,255,255,0.2)',
                            backgroundColor: isActiveTarget ? 'rgba(59,130,246,0.3)' : 'rgba(255,255,255,0.07)',
                            color: isActiveTarget ? '#93c5fd' : '#9ca3af',
                            transition: 'all 0.15s'
                          }}
                        >
                          {isActiveTarget ? '⊛ SELECTED' : '⊙ TARGET'}
                        </button>
                        
                        {/* Live / Historian Switch */}
                        <div style={{ display: 'flex', gap: '4px', backgroundColor: 'rgba(0,0,0,0.3)', padding: '4px', border: `1px solid ${ISA_COLORS.border}` }}>
                          <button
                            onClick={() => {
                              // CRITICAL: Clear cached data and custom dates when switching to LIVE mode
                              const tagsForUnit = getTagsForWindow(unit);
                              tagsForUnit.forEach(tag => {
                                if (trendDataRef.current[tag.id]) {
                                  logDebug(`[Mode Switch] 🗑️ Clearing cached data for ${tag.id} when switching to LIVE`);
                                  delete trendDataRef.current[tag.id];
                                }
                              });
                              
                              updateChartState(unit, { 
                                dataMode: 'live',
                                customStartDate: '',
                                customEndDate: '',
                                showCustomDatePicker: false
                              });
                            }}
                            style={{
                              padding: '4px 12px',
                              backgroundColor: chartState.dataMode === 'live' ? ISA_COLORS.statusOnline : 'transparent',
                              color: chartState.dataMode === 'live' ? '#000000' : ISA_COLORS.foreground,
                              border: 'none',
                              cursor: 'pointer',
                              fontWeight: 700,
                              fontSize: '11px',
                              fontFamily: 'Consolas, monospace'
                            }}
                          >
                            LIVE
                          </button>
                          <button
                            onClick={() => {
                              // CRITICAL: Clear cached data when switching to HISTORIAN mode
                              const tagsForUnit = getTagsForWindow(unit);
                              tagsForUnit.forEach(tag => {
                                if (trendDataRef.current[tag.id]) {
                                  logDebug(`[Mode Switch] 🗑️ Clearing cached data for ${tag.id} when switching to HISTORIAN`);
                                  delete trendDataRef.current[tag.id];
                                }
                              });
                              
                              updateChartState(unit, { dataMode: 'historian', timeRange: 5 });
                            }}
                            style={{
                              padding: '4px 12px',
                              backgroundColor: chartState.dataMode === 'historian' ? '#3b82f6' : 'transparent',
                              color: chartState.dataMode === 'historian' ? '#FFFFFF' : ISA_COLORS.foreground,
                              border: 'none',
                              cursor: 'pointer',
                              fontWeight: 700,
                              fontSize: '11px',
                              fontFamily: 'Consolas, monospace'
                            }}
                          >
                            HISTORIAN
                          </button>
                        </div>
                        
                        {/* Millisecond Toggle */}
                        <label style={{ 
                          display: 'flex', 
                          alignItems: 'center', 
                          gap: '6px',
                          padding: '4px 8px',
                          backgroundColor: 'rgba(0,0,0,0.3)',
                          border: `1px solid ${ISA_COLORS.border}`,
                          cursor: 'pointer',
                          fontFamily: 'Consolas, monospace',
                          fontSize: '11px',
                          fontWeight: 700,
                          color: showMilliseconds ? '#10b981' : ISA_COLORS.foreground
                        }}>
                          <input
                            type="checkbox"
                            checked={showMilliseconds}
                            onChange={(e) => handleMillisecondsToggle(e.target.checked)}
                            style={{ cursor: 'pointer', accentColor: '#10b981' }}
                          />
                          MS
                        </label>
                        
                        {/* Time Range Filter - Horizontal in Historian mode */}
                        {chartState.dataMode === 'historian' && (
                          <div style={{ display: 'flex', gap: '4px', backgroundColor: 'rgba(0,0,0,0.3)', padding: '4px', border: `1px solid ${ISA_COLORS.border}` }}>
                            {[5, 30, 60, 120, 240, 480, 1440].map(minutes => (
                              <button
                                key={minutes}
                                onClick={() => handleTimeRangeChange(unit, minutes)}
                                style={{
                                  padding: '4px 8px',
                                  backgroundColor: chartState.timeRange === minutes && !chartState.showCustomDatePicker ? '#3b82f6' : 'transparent',
                                  color: chartState.timeRange === minutes && !chartState.showCustomDatePicker ? '#FFFFFF' : ISA_COLORS.foreground,
                                  border: 'none',
                                  cursor: 'pointer',
                                  fontWeight: 700,
                                  fontSize: '10px',
                                  fontFamily: 'Consolas, monospace',
                                  whiteSpace: 'nowrap'
                                }}
                              >
                                {minutes < 60 ? `${minutes}M` : minutes === 60 ? '1H' : minutes === 120 ? '2H' : minutes === 240 ? '4H' : minutes === 480 ? '8H' : '24H'}
                              </button>
                            ))}
                            <button
                              onClick={() => updateChartState(unit, { showCustomDatePicker: !chartState.showCustomDatePicker })}
                              style={{
                                padding: '4px 8px',
                                backgroundColor: (chartState.customStartDate && chartState.customEndDate) ? '#10b981' : (chartState.showCustomDatePicker ? '#3b82f6' : 'transparent'),
                                color: (chartState.customStartDate && chartState.customEndDate) || chartState.showCustomDatePicker ? '#FFFFFF' : ISA_COLORS.foreground,
                                border: (chartState.customStartDate && chartState.customEndDate) ? '2px solid #34d399' : 'none',
                                cursor: 'pointer',
                                fontWeight: 700,
                                fontSize: '10px',
                                fontFamily: 'Consolas, monospace',
                                boxShadow: (chartState.customStartDate && chartState.customEndDate) ? '0 0 8px rgba(16, 185, 129, 0.5)' : 'none'
                              }}
                              title={(chartState.customStartDate && chartState.customEndDate) ? 'Custom range active' : 'Set custom date range'}
                            >
                              {(chartState.customStartDate && chartState.customEndDate) ? '✓ CUSTOM' : 'CUSTOM'}
                            </button>
                          </div>
                        )}
                        
                        {/* Pan/Scroll Navigation Controls - ISA-101 Industrial Standard */}
                        {chartState.dataMode === 'historian' && (() => {
                          const firstTag = tags[0];
                          const totalDataPoints = firstTag ? getRenderedTrendData(firstTag.id, chartState.dataMode).length : 0;
                          const dataPoints = Math.min(Math.floor(chartState.timeRange / 2), 60);
                          const maxScroll = Math.max(0, totalDataPoints - dataPoints);
                          const scrollStep = Math.max(5, Math.floor(dataPoints / 6)); // Scroll by ~1/6 of window
                          
                          return (
                            <div style={{ display: 'flex', gap: '2px', backgroundColor: 'rgba(0,0,0,0.3)', padding: '4px', border: `2px solid rgba(251, 191, 36, 0.5)` }}>
                              <span style={{ 
                                fontSize: '9px', 
                                color: '#fbbf24', 
                                fontWeight: 700,
                                padding: '0 6px',
                                display: 'flex',
                                alignItems: 'center',
                                fontFamily: 'Consolas, monospace'
                              }}>NAV:</span>
                              <button
                                onClick={() => {
                                  const currentOffset = chartState.scrollOffset || 0;
                                  const newOffset = Math.min(maxScroll, currentOffset + scrollStep);
                                  updateChartState(unit, { scrollOffset: newOffset });
                                }}
                                disabled={maxScroll === 0 || (chartState.scrollOffset || 0) >= maxScroll}
                                style={{
                                  padding: '4px 12px',
                                  backgroundColor: 'rgba(59, 130, 246, 0.2)',
                                  color: (maxScroll === 0 || (chartState.scrollOffset || 0) >= maxScroll) ? '#4b5563' : '#60a5fa',
                                  border: '1px solid rgba(59, 130, 246, 0.5)',
                                  cursor: (maxScroll === 0 || (chartState.scrollOffset || 0) >= maxScroll) ? 'not-allowed' : 'pointer',
                                  fontWeight: 700,
                                  fontSize: '12px',
                                  fontFamily: 'monospace',
                                  opacity: (maxScroll === 0 || (chartState.scrollOffset || 0) >= maxScroll) ? 0.4 : 1
                                }}
                                title={`Scroll Left (Older Data) - Step: ${scrollStep} pts`}
                              >
                                ⏪
                              </button>
                              <button
                                onClick={() => {
                                  updateChartState(unit, { scrollOffset: 0 });
                                }}
                                style={{
                                  padding: '4px 10px',
                                  backgroundColor: (chartState.scrollOffset || 0) === 0 ? 'rgba(34, 197, 94, 0.3)' : 'rgba(0,0,0,0.3)',
                                  color: (chartState.scrollOffset || 0) === 0 ? '#22c55e' : '#9ca3af',
                                  border: `1px solid ${(chartState.scrollOffset || 0) === 0 ? 'rgba(34, 197, 94, 0.5)' : 'rgba(156, 163, 175, 0.3)'}`,
                                  cursor: 'pointer',
                                  fontWeight: 700,
                                  fontSize: '9px',
                                  fontFamily: 'Consolas, monospace'
                                }}
                                title="Reset to Latest Data"
                              >
                                NOW
                              </button>
                              <button
                                onClick={() => {
                                  const currentOffset = chartState.scrollOffset || 0;
                                  const newOffset = Math.max(0, currentOffset - scrollStep);
                                  updateChartState(unit, { scrollOffset: newOffset });
                                }}
                                disabled={(chartState.scrollOffset || 0) === 0}
                                style={{
                                  padding: '4px 12px',
                                  backgroundColor: 'rgba(59, 130, 246, 0.2)',
                                  color: (chartState.scrollOffset || 0) === 0 ? '#4b5563' : '#60a5fa',
                                  border: '1px solid rgba(59, 130, 246, 0.5)',
                                  cursor: (chartState.scrollOffset || 0) === 0 ? 'not-allowed' : 'pointer',
                                  fontWeight: 700,
                                  fontSize: '12px',
                                  fontFamily: 'monospace',
                                  opacity: (chartState.scrollOffset || 0) === 0 ? 0.4 : 1
                                }}
                                title={`Scroll Right (Newer Data) - Step: ${scrollStep} pts`}
                              >
                                ⏩
                              </button>
                            </div>
                          );
                        })()}
                        
                        {/* Tag Names for this unit with individual STAT buttons */}
                        <div style={{ display: 'flex', gap: '12px', alignItems: 'center', flexWrap: 'wrap' }}>
                          {tags.map((tag, idx) => {
                            const tagIndex = selectedTags.findIndex(t => t.id === tag.id);
                            const isStatsVisible = showStatistics[tag.id] || false;
                            return (
                              <div key={tag.id} style={{ display: 'flex', alignItems: 'center', gap: '6px', backgroundColor: 'rgba(0,0,0,0.2)', padding: '4px 8px', borderRadius: '3px' }}>
                                <div style={{
                                  width: '20px',
                                  height: '3px',
                                  backgroundColor: TAG_TREND_COLORS[tagIndex % TAG_TREND_COLORS.length]
                                }} />
                                <span style={{
                                  fontSize: '11px',
                                  fontFamily: 'Consolas, monospace',
                                  fontWeight: 700,
                                  color: TAG_TREND_COLORS[tagIndex % TAG_TREND_COLORS.length]
                                }}>
                                  {tag.name}{(() => {
                                    const u = tag.unit || '';
                                    // Don't show windowId as a unit in the legend
                                    if (!u || u.startsWith('win_')) return '';
                                    const cleaned = u.replace(/^\d+\s*/, '').trim();
                                    return cleaned ? ` (${cleaned})` : '';
                                  })()}
                                </span>
                                <button
                                  onClick={() => setShowStatistics(prev => ({ ...prev, [tag.id]: !isStatsVisible }))}
                                  style={{
                                    padding: '2px 6px',
                                    backgroundColor: isStatsVisible ? '#3b82f6' : 'rgba(0,0,0,0.3)',
                                    color: isStatsVisible ? '#FFFFFF' : ISA_COLORS.foreground,
                                    border: `1px solid ${isStatsVisible ? '#3b82f6' : ISA_COLORS.border}`,
                                    cursor: 'pointer',
                                    fontWeight: 700,
                                    fontSize: '8px',
                                    fontFamily: 'Consolas, monospace',
                                    borderRadius: '2px'
                                  }}
                                  title={`${isStatsVisible ? 'Hide' : 'Show'} statistics for ${tag.name}`}
                                >
                                  STAT
                                </button>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                      
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                        {/* View Controls */}
                        <div style={{ display: 'flex', gap: '2px', alignItems: 'center', backgroundColor: 'rgba(0,0,0,0.3)', padding: '2px', border: `1px solid ${ISA_COLORS.border}` }}>
                          <button
                            onClick={() => setShowReferenceLines(!showReferencLines)}
                            style={{
                              padding: '4px 10px',
                              backgroundColor: showReferencLines ? '#3b82f6' : 'transparent',
                              color: ISA_COLORS.foreground,
                              border: 'none',
                              cursor: 'pointer',
                              fontWeight: 700,
                              fontSize: '9px',
                              fontFamily: 'Consolas, monospace'
                            }}
                            title="Show Reference Lines"
                          >
                            REF
                          </button>
                        </div>
                        
                        {/* Zoom Controls */}
                        <div style={{ display: 'flex', gap: '2px', alignItems: 'center', backgroundColor: 'rgba(0,0,0,0.3)', padding: '2px', border: `1px solid ${ISA_COLORS.border}` }}>
                          <span style={{ fontSize: '9px', color: ISA_COLORS.foreground, marginLeft: '4px', marginRight: '4px' }}>ZOOM:</span>
                          <button
                            onClick={() => setZoomLevel(prev => Math.min(prev + 0.25, 3))}
                            style={{
                              padding: '4px 8px',
                              backgroundColor: 'transparent',
                              color: ISA_COLORS.foreground,
                              border: 'none',
                              cursor: 'pointer',
                              fontWeight: 700,
                              fontSize: '14px'
                            }}
                            title="Zoom In"
                          >
                            +
                          </button>
                          <span style={{ 
                            fontSize: '10px', 
                            fontFamily: 'Consolas, monospace',
                            minWidth: '35px',
                            textAlign: 'center',
                            color: ISA_COLORS.valueNormal
                          }}>
                            {(zoomLevel * 100).toFixed(0)}%
                          </span>
                          <button
                            onClick={() => setZoomLevel(prev => Math.max(prev - 0.25, 0.5))}
                            style={{
                              padding: '4px 8px',
                              backgroundColor: 'transparent',
                              color: ISA_COLORS.foreground,
                              border: 'none',
                              cursor: 'pointer',
                              fontWeight: 700,
                              fontSize: '14px'
                            }}
                            title="Zoom Out"
                          >
                            -
                          </button>
                          <button
                            onClick={() => setZoomLevel(1)}
                            style={{
                              padding: '4px 10px',
                              backgroundColor: 'transparent',
                              color: ISA_COLORS.foreground,
                              border: 'none',
                              cursor: 'pointer',
                              fontWeight: 700,
                              fontSize: '9px',
                              fontFamily: 'Consolas, monospace'
                            }}
                            title="Reset Zoom"
                          >
                            RESET
                          </button>
                        </div>
                        
                        {/* Pause Control - Per Unit */}
                        <button
                          onClick={() => {
                            const isPaused = trendsPausedState[unit] || false;
                            const newValue = !isPaused;
                            setTrendsPausedState(prev => ({ ...prev, [unit]: newValue }));
                            trendsPausedRef.current[unit] = newValue;
                            logInfo(`🎬 Trend [${unit}]`, newValue ? 'PAUSED' : 'RESUMED');
                          }}
                          style={{
                            padding: '4px 12px',
                            backgroundColor: (trendsPausedState[unit] || false) ? '#f59e0b' : 'rgba(0,0,0,0.3)',
                            color: ISA_COLORS.foreground,
                            border: `1px solid ${ISA_COLORS.border}`,
                            cursor: 'pointer',
                            fontWeight: 700,
                            fontSize: '10px',
                            fontFamily: 'Consolas, monospace',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '4px'
                          }}
                          title={(trendsPausedState[unit] || false) ? `Resume ${unit} Trend` : `Pause ${unit} Trend`}
                        >
                          {(trendsPausedState[unit] || false) ? '▶' : '⏸'} {(trendsPausedState[unit] || false) ? 'RESUME' : 'PAUSE'}
                        </button>
                        
                        <span style={{ fontSize: '10px', fontFamily: 'Consolas, monospace', color: ISA_COLORS.foreground, opacity: 0.7 }}>UPDATE: 1s</span>
                      </div>
                    </div>
                    
                    {/* Custom Date Range Picker */}
                    {chartState.dataMode === 'historian' && chartState.showCustomDatePicker && (
                      <div style={{
                        padding: '12px 16px',
                        borderBottom: `2px solid ${ISA_COLORS.border}`,
                        backgroundColor: 'rgba(59, 130, 246, 0.1)',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '16px'
                      }}>
                        <span style={{ fontSize: '11px', fontWeight: 700, color: ISA_COLORS.foreground }}>CUSTOM RANGE:</span>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <label style={{ fontSize: '10px', color: ISA_COLORS.foreground }}>FROM:</label>
                          <input
                            type="date"
                            value={chartState.customStartDate}
                            onChange={(e) => {
                              updateChartState(unit, { customStartDate: e.target.value });
                            }}
                            style={{
                              padding: '4px 8px',
                              backgroundColor: ISA_COLORS.panel,
                              color: ISA_COLORS.foreground,
                              border: `1px solid ${ISA_COLORS.border}`,
                              fontFamily: 'Consolas, monospace',
                              fontSize: '11px'
                            }}
                          />
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <label style={{ fontSize: '10px', color: ISA_COLORS.foreground }}>TO:</label>
                          <input
                            type="date"
                            value={chartState.customEndDate}
                            onChange={(e) => {
                              updateChartState(unit, { customEndDate: e.target.value });
                            }}
                            style={{
                              padding: '4px 8px',
                              backgroundColor: ISA_COLORS.panel,
                              color: ISA_COLORS.foreground,
                              border: `1px solid ${ISA_COLORS.border}`,
                              fontFamily: 'Consolas, monospace',
                              fontSize: '11px'
                            }}
                          />
                        </div>
                        <button
                          onClick={() => handleCustomDateApply(unit)}
                          disabled={!chartState.customStartDate || !chartState.customEndDate}
                          style={{
                            padding: '4px 16px',
                            backgroundColor: chartState.customStartDate && chartState.customEndDate ? '#3b82f6' : ISA_COLORS.panel,
                            color: chartState.customStartDate && chartState.customEndDate ? '#FFFFFF' : ISA_COLORS.valueDisabled,
                            border: `1px solid ${ISA_COLORS.border}`,
                            cursor: chartState.customStartDate && chartState.customEndDate ? 'pointer' : 'not-allowed',
                            fontWeight: 700,
                            fontSize: '11px',
                            fontFamily: 'Consolas, monospace'
                          }}
                        >
                          APPLY
                        </button>
                        <button
                          onClick={() => {
                            // CRITICAL: Clear cached trend data when canceling custom range
                            const tagsForUnit = getTagsForWindow(unit);
                            tagsForUnit.forEach(tag => {
                              if (trendDataRef.current[tag.id]) {
                                logDebug(`[Custom Range] 🗑️ Clearing cached data for ${tag.id} on CANCEL`);
                                delete trendDataRef.current[tag.id];
                              }
                            });
                            
                            updateChartState(unit, {
                              showCustomDatePicker: false,
                              customStartDate: '',
                              customEndDate: ''
                            });
                          }}
                          style={{
                            padding: '4px 16px',
                            backgroundColor: 'transparent',
                            color: ISA_COLORS.foreground,
                            border: `1px solid ${ISA_COLORS.border}`,
                            cursor: 'pointer',
                            fontWeight: 700,
                            fontSize: '11px',
                            fontFamily: 'Consolas, monospace'
                          }}
                        >
                          CANCEL
                        </button>
                      </div>
                    )}
                    
                    {/* Min/Max Band Toggle - Industry standard for process variability analysis */}
                    {chartState.dataMode === 'historian' && (
                      <button
                        onClick={() => {
                          updateChartState(unit, {
                            showMinMaxBand: !chartState.showMinMaxBand
                          });
                        }}
                        style={{
                          padding: '6px 12px',
                          backgroundColor: chartState.showMinMaxBand ? '#10b981' : 'transparent',
                          color: chartState.showMinMaxBand ? '#FFFFFF' : ISA_COLORS.foreground,
                          border: `1px solid ${chartState.showMinMaxBand ? '#10b981' : ISA_COLORS.border}`,
                          cursor: 'pointer',
                          fontWeight: 700,
                          fontSize: '10px',
                          fontFamily: 'Consolas, monospace',
                          marginLeft: '8px'
                        }}
                        title="Toggle Min/Max band display for process variability analysis"
                      >
                        📊 {chartState.showMinMaxBand ? 'HIDE BAND' : 'SHOW BAND'}
                      </button>
                    )}
                    
                    {/* Statistics Panel - Per-Tag Display */}
                    {(() => {
                      // Filter tags that have statistics enabled
                      const tagsWithStats = tags.filter(tag => showStatistics[tag.id]);
                      if (tagsWithStats.length === 0) return null;
                      
                      return (
                        <div style={{
                          padding: '8px 12px',
                          borderBottom: `2px solid ${ISA_COLORS.border}`,
                          backgroundColor: 'rgba(59, 130, 246, 0.1)',
                          display: 'grid',
                          gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
                          gap: '12px'
                        }}>
                          {tagsWithStats.map((tag, idx) => {
                            const data = getRenderedTrendData(tag.id, chartState.dataMode);
                            if (!data || data.length === 0) return null;
                            const stats = calculateStatistics(data);
                            if (!stats) return null;
                            
                            const tagIndex = selectedTags.findIndex(t => t.id === tag.id);
                            return (
                              <div key={tag.id} style={{ 
                                display: 'flex', 
                                flexDirection: 'column', 
                                gap: '2px',
                                borderLeft: `3px solid ${TAG_TREND_COLORS[tagIndex % TAG_TREND_COLORS.length]}`,
                                paddingLeft: '6px'
                              }}>
                                <div style={{ fontSize: '10px', fontWeight: 700, color: TAG_TREND_COLORS[tagIndex % TAG_TREND_COLORS.length], marginBottom: '2px' }}>
                                  {tag.name}
                                </div>
                                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', fontSize: '8px', fontFamily: 'Consolas', color: ISA_COLORS.foreground, opacity: 0.9 }}>
                                  <span>MIN: {stats.min.toFixed(2)}</span>
                                  <span>MAX: {stats.max.toFixed(2)}</span>
                                </div>
                                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', fontSize: '8px', fontFamily: 'Consolas', color: ISA_COLORS.foreground, opacity: 0.9 }}>
                                  <span>AVG: {stats.avg.toFixed(2)}</span>
                                  <span>STD: {stats.stdDev.toFixed(2)}</span>
                                </div>
                                <div style={{ fontSize: '8px', fontFamily: 'Consolas', color: ISA_COLORS.foreground, opacity: 0.9 }}>
                                  RATE: {stats.rateOfChange.toFixed(3)} {tag.unit?.replace(/^\d+\s*/, '') || tag.unit}/s
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      );
                    })()}
                    
                    {/* SVG LINE CHART - ISA-101 Compliant */}
                    <div 
                      style={{ padding: '16px', overflow: 'auto', backgroundColor: ISA_101_TREND_CONFIG.colors.background.xAxis, position: 'relative' }}
                      onMouseMove={(e) => {
                        const rect = e.currentTarget.getBoundingClientRect();
                        const x = e.clientX - rect.left - 16; // Adjust for padding
                        const y = e.clientY - rect.top - 16;
                        if (x >= 0 && x <= rect.width - 32 && y >= 0 && y <= 400) {
                          setCursorPosition({ x, y, unit });
                        }
                      }}
                      onMouseLeave={() => setCursorPosition(null)}
                    >
                      <div style={{ 
                        transform: `scale(${zoomLevel})`, 
                        transformOrigin: 'top left',
                        transition: 'transform 0.2s ease-out'
                      }}>
                        <svg 
                          ref={(el) => { if (el) svgRefs.current[unit] = el; }}
                          width="100%" 
                          height={450} 
                          viewBox="0 0 1200 450" 
                          preserveAspectRatio="none"
                        >
                        {/* Grid Lines - ISA-101 Industrial Standard */}
                        <defs>
                          {/* Major Grid Pattern */}
                          <pattern id={`majorGrid-${unit}`} width="120" height="80" patternUnits="userSpaceOnUse">
                            <path d="M 120 0 L 0 0 0 80" fill="none" stroke={ISA_101_TREND_CONFIG.colors.grid.major} strokeWidth={ISA_101_TREND_CONFIG.strokes.grid.major}/>
                          </pattern>
                          {/* Minor Grid Pattern */}
                          <pattern id={`minorGrid-${unit}`} width="40" height="40" patternUnits="userSpaceOnUse">
                            <path d="M 40 0 L 0 0 0 40" fill="none" stroke={ISA_101_TREND_CONFIG.colors.grid.minor} strokeWidth={ISA_101_TREND_CONFIG.strokes.grid.minor}/>
                          </pattern>
                        </defs>
                        {/* Dark industrial background - ISA-101 */}
                        <rect width="1200" height="400" fill={ISA_101_TREND_CONFIG.colors.background.main} />
                        {/* Minor grid overlay */}
                        <rect width="1200" height="400" fill={`url(#minorGrid-${unit})`} />
                        {/* Major grid overlay */}
                        <rect width="1200" height="400" fill={`url(#majorGrid-${unit})`} />
                        
                        {/* Calculate common min/max for tags with same unit */}
                        {(() => {
                          // GENERIC SCALE CALCULATION - Works for any value range
                          // Collect all data values from live trends
                          const allDataValues = tags.flatMap(tag => {
                            const liveTrendData = getRenderedTrendData(tag.id, chartState.dataMode);
                            if (liveTrendData && liveTrendData.length > 0) {
                              return liveTrendData.map(d => d.value);
                            }
                            return [tag.value || 0];
                          });
                          
                          // Include limits if they're meaningful (not default 0-100)
                          const limitsToInclude = tags.flatMap(t => {
                            const limits = [];
                            if (t.loLimit !== undefined && t.loLimit !== 0) limits.push(t.loLimit);
                            if (t.hiLimit !== undefined && t.hiLimit !== 100) limits.push(t.hiLimit);
                            return limits;
                          });
                          
                          const allValues = [...allDataValues, ...limitsToInclude];
                          
                          // Handle edge cases
                          if (allValues.length === 0) {
                            allValues.push(0, 100); // Fallback range
                          }
                          
                          let dataMin = Math.min(...allValues);
                          let dataMax = Math.max(...allValues);
                          
                          // If min equals max, add padding
                          if (dataMin === dataMax) {
                            dataMin = dataMin - Math.abs(dataMin * 0.1 || 10);
                            dataMax = dataMax + Math.abs(dataMax * 0.1 || 10);
                          }
                          
                          // Add 10% padding to prevent values at edges
                          const dataRange = dataMax - dataMin;
                          const padding = dataRange * 0.1;
                          const commonMin = dataMin - padding;
                          const commonMax = dataMax + padding;
                          const range = commonMax - commonMin;
                          
                          // Y-axis reference lines and labels - INDUSTRIAL STYLE
                          const steps = 5;
                          return (
                            <g>
                              {/* Y-Axis Background Panel - ISA-101 */}
                              <rect x="0" y="0" width="80" height="400" fill={ISA_101_TREND_CONFIG.colors.background.yAxis} />
                              
                              {/* Left Border (Y-Axis) - ISA-101 */}
                              <line x1="80" y1="0" x2="80" y2="400" stroke="rgba(59, 130, 246, 0.6)" strokeWidth="2" />
                              
                              {/* Top Border - Full width from edge to edge */}
                              <line x1="0" y1="0" x2="1200" y2="0" stroke="rgba(59, 130, 246, 0.6)" strokeWidth="2" />
                              
                              {/* Right Border - Positioned at 1199 to account for 2px stroke width */}
                              <line x1="1199" y1="0" x2="1199" y2="400" stroke="rgba(59, 130, 246, 0.6)" strokeWidth="2" />
                              
                              {/* Y-Axis Scale Lines and Labels */}
                              {Array.from({ length: steps + 1 }, (_, i) => {
                                const value = commonMin + (range * i / steps);
                                const yPos = 400 - (i * 400 / steps);
                                // Adjust label position to prevent clipping at top/bottom
                                const labelY = Math.max(15, Math.min(yPos, 390));
                                return (
                                  <g key={i}>
                                    {/* Horizontal grid line - ISA-101 (skip top/bottom to avoid overlap with border) */}
                                    {i !== 0 && i !== steps && (
                                      <line 
                                        x1="80" 
                                        y1={yPos} 
                                        x2="1199" 
                                        y2={yPos} 
                                        stroke={ISA_101_TREND_CONFIG.colors.grid.major} 
                                        strokeWidth={ISA_101_TREND_CONFIG.strokes.grid.major} 
                                      />
                                    )}
                                    {/* Tick mark - ISA-101 */}
                                    <line 
                                      x1="75" 
                                      y1={yPos} 
                                      x2="85" 
                                      y2={yPos} 
                                      stroke={ISA_101_TREND_CONFIG.colors.grid.axis} 
                                      strokeWidth={ISA_101_TREND_CONFIG.strokes.grid.axis} 
                                    />
                                    {/* Value label with background - ISA-101 */}
                                    <rect 
                                      x="5" 
                                      y={labelY - 10} 
                                      width="70" 
                                      height="20" 
                                      fill={ISA_101_TREND_CONFIG.colors.background.yAxis}
                                      stroke={ISA_101_TREND_CONFIG.colors.grid.minor}
                                      strokeWidth="0.5"
                                      rx="2"
                                    />
                                    <text 
                                      x="40" 
                                      y={labelY + 5} 
                                      fill={ISA_101_TREND_CONFIG.colors.text.secondary} 
                                      fontSize={ISA_101_TREND_CONFIG.typography.fontSize.axisLabel} 
                                      fontFamily={ISA_101_TREND_CONFIG.typography.fontFamily.numeric}
                                      fontWeight={ISA_101_TREND_CONFIG.typography.fontWeight.values}
                                      textAnchor="middle"
                                    >
                                      {value.toFixed(1)}
                                    </text>
                                  </g>
                                );
                              })}
                              
                              {/* Y-Axis Unit Label - ISA-101 Compliant - CRITICAL for operations */}
                              <text 
                                x="40" 
                                y="8" 
                                fill={ISA_101_TREND_CONFIG.colors.text.highlight} 
                                fontSize={ISA_101_TREND_CONFIG.typography.fontSize.axisUnit} 
                                fontFamily={ISA_101_TREND_CONFIG.typography.fontFamily.primary}
                                fontWeight={ISA_101_TREND_CONFIG.typography.fontWeight.bold}
                                textAnchor="middle"
                              >
                                {/* Don't show windowId as unit label — show actual unit or nothing */}
                                {unit.startsWith('win_') ? '' : `[${unit.replace(/^\d+\s*/, '').trim()}]`}
                              </text>
                            </g>
                          );
                        })()}
                        
                        {/* Plot trend lines for each tag in this unit group */}
                        {tags.map((tag) => {
                          const tagIndex = selectedTags.findIndex(t => t.id === tag.id);
                          // Use different time range for historian mode vs live mode
                          const minutesRange = chartState.dataMode === 'live' ? 5 : chartState.timeRange;
                          
                          // INTELLIGENT DOWNSAMPLING: Show optimal points for clarity
                          // For historian mode with large datasets, downsample to ~500 visible points
                          // This prevents congested/unclear trends while maintaining data shape
                          const liveTrendData = getRenderedTrendData(tag.id, chartState.dataMode);
                          let trendData;
                          
                          if (liveTrendData && liveTrendData.length > 0) {
                            // INDUSTRIAL NAVIGATION: Apply scroll offset
                            const scrollOffset = chartState.scrollOffset || 0;
                            
                            if (chartState.dataMode === 'historian') {
                              // For historian mode: intelligent downsampling
                              const MAX_VISIBLE_POINTS = 500; // ISA-101 recommendation for clear visualization
                              
                              if (liveTrendData.length <= MAX_VISIBLE_POINTS) {
                                // Small dataset - show all points
                                const endIndex = liveTrendData.length - scrollOffset;
                                const startIndex = Math.max(0, endIndex - liveTrendData.length);
                                trendData = liveTrendData.slice(startIndex, endIndex);
                              } else {
                                // Large dataset - downsample intelligently
                                const endIndex = liveTrendData.length - scrollOffset;
                                const startIndex = Math.max(0, endIndex - MAX_VISIBLE_POINTS);
                                
                                // Calculate sampling interval to get ~500 points
                                const availablePoints = endIndex - startIndex;
                                const sampleEvery = Math.max(1, Math.floor(availablePoints / MAX_VISIBLE_POINTS));
                                
                                // Sample evenly across the range
                                trendData = [];
                                for (let i = startIndex; i < endIndex; i += sampleEvery) {
                                  trendData.push(liveTrendData[i]);
                                }
                                
                                // Always include the last point
                                if (trendData.length > 0 && trendData[trendData.length - 1] !== liveTrendData[endIndex - 1]) {
                                  trendData.push(liveTrendData[endIndex - 1]);
                                }
                                
                              }
                            } else {
                              // Live mode - show last 30 points
                              const endIndex = liveTrendData.length - scrollOffset;
                              const startIndex = Math.max(0, endIndex - 30);
                              trendData = liveTrendData.slice(startIndex, endIndex);
                            }
                            
                          } else {
                            // No live data available - do NOT generate demo data
                            trendData = [];
                          }
                          
                          // GENERIC SCALE CALCULATION FOR PLOTTING - Works for any value range
                          // Get all actual data values for this unit group
                          const allDataValuesForScale = tags.flatMap(t => {
                            const ltd = getRenderedTrendData(t.id, chartState.dataMode);
                            return ltd && ltd.length > 0 ? ltd.map(d => d.value) : [t.value || 0];
                          });
                          
                          // Include limits only if they're meaningful
                          const limitsForScale = tags.flatMap(t => {
                            const limits = [];
                            if (t.loLimit !== undefined && t.loLimit !== 0) limits.push(t.loLimit);
                            if (t.hiLimit !== undefined && t.hiLimit !== 100) limits.push(t.hiLimit);
                            return limits;
                          });
                          
                          const allValuesForScale = [...allDataValuesForScale, ...limitsForScale];
                          
                          // Handle edge cases
                          if (allValuesForScale.length === 0) {
                            allValuesForScale.push(0, 100);
                          }
                          
                          let scaleMin = Math.min(...allValuesForScale);
                          let scaleMax = Math.max(...allValuesForScale);
                          
                          // Add padding if range is zero
                          if (scaleMin === scaleMax) {
                            scaleMin = scaleMin - Math.abs(scaleMin * 0.1 || 10);
                            scaleMax = scaleMax + Math.abs(scaleMax * 0.1 || 10);
                          }
                          
                          // Add 10% padding
                          const scaleRange = scaleMax - scaleMin;
                          const scalePadding = scaleRange * 0.1;
                          const minVal = scaleMin - scalePadding;
                          const maxVal = scaleMax + scalePadding;
                          const range = maxVal - minVal;
                          
                          // CHART BOUNDARIES: Add padding on left/right to prevent clipping
                          const CHART_LEFT_PADDING = 80;
                          const CHART_RIGHT_PADDING = 80;
                          const CHART_WIDTH = 1200 - CHART_LEFT_PADDING - CHART_RIGHT_PADDING; // 1040px data area
                          
                          // Generate SVG path with padded boundaries
                          const pathData = trendData.map((point, i) => {
                            const x = CHART_LEFT_PADDING + (i / (trendData.length - 1)) * CHART_WIDTH;
                            const normalizedValue = ((point.value - minVal) / range);
                            const y = 400 - (normalizedValue * 400);
                            return `${i === 0 ? 'M' : 'L'} ${x} ${y}`;
                          }).join(' ');
                          
                          // Generate min/max band paths if enabled and data has min/max
                          let minBandPath = '';
                          let maxBandPath = '';
                          const hasMinMax = trendData.some(p => p.min !== undefined && p.max !== undefined);
                          
                          if (chartState.showMinMaxBand && hasMinMax) {
                            // Create area path for min values (bottom of band)
                            minBandPath = trendData.map((point: any, i) => {
                              const x = CHART_LEFT_PADDING + (i / (trendData.length - 1)) * CHART_WIDTH;
                              const normalizedMin = ((point.min - minVal) / range);
                              const y = 400 - (normalizedMin * 400);
                              return `${i === 0 ? 'M' : 'L'} ${x} ${y}`;
                            }).join(' ');
                            
                            // Create area path for max values (top of band)
                            maxBandPath = trendData.map((point: any, i) => {
                              const x = CHART_LEFT_PADDING + (i / (trendData.length - 1)) * CHART_WIDTH;
                              const normalizedMax = ((point.max - minVal) / range);
                              const y = 400 - (normalizedMax * 400);
                              return `${i === 0 ? 'M' : 'L'} ${x} ${y}`;
                            }).join(' ');
                          }
                          
                          return (
                            <g key={tag.id}>
                              {/* Min/Max Band - Industry standard for process variability */}
                              {chartState.showMinMaxBand && hasMinMax && (
                                <path
                                  d={`${maxBandPath} ${minBandPath.split('').reverse().join('').replace(/L/g, 'X').replace(/M/g, 'L').replace(/X/g, 'M')} Z`}
                                  fill={TAG_TREND_COLORS[tagIndex % TAG_TREND_COLORS.length]}
                                  fillOpacity="0.15"
                                  stroke="none"
                                />
                              )}
                              
                              {/* Trend Line - ISA-101 Compliant: Smooth, readable, high-contrast */}
                              <path
                                d={pathData}
                                fill="none"
                                stroke={TAG_TREND_COLORS[tagIndex % TAG_TREND_COLORS.length]}
                                strokeWidth={ISA_101_TREND_CONFIG.strokes.trendLine.normal}
                                opacity="1"
                                strokeLinejoin={ISA_101_TREND_CONFIG.strokes.rendering.lineJoin as any}
                                strokeLinecap={ISA_101_TREND_CONFIG.strokes.rendering.lineCap as any}
                                filter="drop-shadow(0 0 2px rgba(0,0,0,0.8))"
                                style={{ vectorEffect: 'non-scaling-stroke' }}
                              />
                              {/* Data Points - ISA-101 Compliant Markers */}
                              {trendData.map((point, i) => {
                                const x = CHART_LEFT_PADDING + (i / (trendData.length - 1)) * CHART_WIDTH;
                                const normalizedValue = ((point.value - minVal) / range);
                                const y = 400 - (normalizedValue * 400);
                                const isRecent = i >= trendData.length - ISA_101_TREND_CONFIG.markers.highlight.recentCount;
                                return (
                                  <g key={i}>
                                    {/* Outer ring for better visibility - ISA-101 */}
                                    <circle
                                      cx={x}
                                      cy={y}
                                      r={isRecent ? ISA_101_TREND_CONFIG.strokes.marker.recentRadius : ISA_101_TREND_CONFIG.strokes.marker.radius}
                                      fill="none"
                                      stroke={TAG_TREND_COLORS[tagIndex % TAG_TREND_COLORS.length]}
                                      strokeWidth={ISA_101_TREND_CONFIG.strokes.marker.strokeWidth}
                                      opacity={isRecent ? 1 : 0.6}
                                    />
                                    {/* Inner filled circle - ISA-101 */}
                                    <circle
                                      cx={x}
                                      cy={y}
                                      r={isRecent ? 3 : 2.5}
                                      fill={TAG_TREND_COLORS[tagIndex % TAG_TREND_COLORS.length]}
                                      stroke={ISA_101_TREND_CONFIG.colors.markers.stroke}
                                      strokeWidth={ISA_101_TREND_CONFIG.strokes.marker.strokeWidth}
                                      opacity={isRecent ? 1 : 0.7}
                                      style={{ cursor: 'pointer' }}
                                      onMouseEnter={(e) => {
                                        const rect = e.currentTarget.getBoundingClientRect();
                                        setTooltip({
                                          visible: true,
                                          x: rect.left + window.scrollX,
                                          y: rect.top + window.scrollY - 10,
                                          data: {
                                            time: point.time,
                                            value: point.value,
                                            min: (point as any).min,
                                            max: (point as any).max,
                                            count: (point as any).count
                                          },
                                          tagName: tag.name,
                                          isAggregated: chartState.dataMode === 'historian' && ((point as any).min !== undefined || (point as any).max !== undefined)
                                        });
                                      }}
                                      onMouseLeave={() => setTooltip(null)}
                                    >
                                      <title>{`${tag.name}: ${point.value.toFixed(2)}${(() => { const u = (tag.unit || '').replace(/^\d+\s*/, '').trim(); return u ? ` ${u}` : ''; })()}\n${point.time}`}</title>
                                    </circle>
                                    {/* Pulse effect for most recent point */}
                                    {i === trendData.length - 1 && (
                                      <circle
                                        cx={x}
                                        cy={y}
                                        r="8"
                                        fill="none"
                                        stroke={TAG_TREND_COLORS[tagIndex % TAG_TREND_COLORS.length]}
                                        strokeWidth="2"
                                        opacity="0.5"
                                      >
                                        <animate
                                          attributeName="r"
                                          from="5"
                                          to="12"
                                          dur="1.5s"
                                          repeatCount="indefinite"
                                        />
                                        <animate
                                          attributeName="opacity"
                                          from="0.8"
                                          to="0"
                                          dur="1.5s"
                                          repeatCount="indefinite"
                                        />
                                      </circle>
                                    )}
                                  </g>
                                );
                              })}
                            </g>
                          );
                        })}
                        
                        {/* Reference Lines (Hi/Lo Limits) - ENHANCED ISA-101 STYLE */}
                        {showReferencLines && tags.map((tag) => {
                          // Use same generic scale calculation as main chart
                          const allDataValuesForScale = tags.flatMap(t => {
                            const ltd = trendDataRef.current[t.id];
                            return ltd && ltd.length > 0 ? ltd.map(d => d.value) : [t.value || 0];
                          });
                          
                          const limitsForScale = tags.flatMap(t => {
                            const limits = [];
                            if (t.loLimit !== undefined && t.loLimit !== 0) limits.push(t.loLimit);
                            if (t.hiLimit !== undefined && t.hiLimit !== 100) limits.push(t.hiLimit);
                            return limits;
                          });
                          
                          const allValuesForScale = [...allDataValuesForScale, ...limitsForScale];
                          if (allValuesForScale.length === 0) allValuesForScale.push(0, 100);
                          
                          let scaleMin = Math.min(...allValuesForScale);
                          let scaleMax = Math.max(...allValuesForScale);
                          
                          if (scaleMin === scaleMax) {
                            scaleMin = scaleMin - Math.abs(scaleMin * 0.1 || 10);
                            scaleMax = scaleMax + Math.abs(scaleMax * 0.1 || 10);
                          }
                          
                          const scaleRange = scaleMax - scaleMin;
                          const scalePadding = scaleRange * 0.1;
                          const minVal = scaleMin - scalePadding;
                          const maxVal = scaleMax + scalePadding;
                          const range = maxVal - minVal;
                          
                          const tagIndex = selectedTags.findIndex(t => t.id === tag.id);
                          
                          // Hi Limit line
                          const hiY = 400 - (((tag.hiLimit || 100) - minVal) / range * 400);
                          const loY = 400 - (((tag.loLimit || 0) - minVal) / range * 400);
                          
                          // Ensure labels stay within visible bounds
                          const hiLabelY = Math.max(25, Math.min(hiY, 385));
                          const loLabelY = Math.max(25, Math.min(loY, 385));
                          
                          return (
                            <g key={`ref-${tag.id}`}>
                              {/* HI LIMIT */}
                              <line 
                                x1="80" 
                                y1={hiY} 
                                x2="1200" 
                                y2={hiY} 
                                stroke="#ef4444"
                                strokeWidth="2.5" 
                                strokeDasharray="8,4"
                                opacity="0.8" 
                              />
                              {/* HI Label on left side */}
                              <rect
                                x="85"
                                y={hiLabelY - 12}
                                width="90"
                                height="24"
                                fill="rgba(239, 68, 68, 0.3)"
                                stroke="#ef4444"
                                strokeWidth="2"
                                rx="4"
                              />
                              <text 
                                x="130" 
                                y={hiLabelY + 5} 
                                fill="#fee2e2"
                                fontSize="13" 
                                fontFamily="Consolas, monospace"
                                fontWeight="700"
                                textAnchor="middle"
                              >
                                HI: {tag.hiLimit}
                              </text>
                              
                              {/* LO LIMIT */}
                              <line 
                                x1="80" 
                                y1={loY} 
                                x2="1200" 
                                y2={loY} 
                                stroke="#3b82f6"
                                strokeWidth="2.5" 
                                strokeDasharray="8,4"
                                opacity="0.8" 
                              />
                              {/* LO Label on left side */}
                              <rect
                                x="85"
                                y={loLabelY - 12}
                                width="90"
                                height="24"
                                fill="rgba(59, 130, 246, 0.3)"
                                stroke="#3b82f6"
                                strokeWidth="2"
                                rx="4"
                              />
                              <text 
                                x="130" 
                                y={loLabelY + 5} 
                                fill="#bfdbfe"
                                fontSize="13" 
                                fontFamily="Consolas, monospace"
                                fontWeight="700"
                                textAnchor="middle"
                              >
                                LO: {tag.loLimit}
                              </text>
                            </g>
                          );
                        })}
                        
                        {/* Cursor Crosshairs - ENHANCED ISA-101 STYLE */}
                        {cursorPosition && cursorPosition.unit === unit && (() => {
                          // Calculate actual coordinates in SVG viewBox
                          const svg = svgRefs.current[unit];
                          if (!svg) return null;
                          
                          const rect = svg.getBoundingClientRect();
                          const scaleX = 1200 / (rect.width - 32); // Adjust for padding
                          const scaleY = 400 / 400;
                          
                          const svgX = cursorPosition.x * scaleX;
                          const svgY = cursorPosition.y * scaleY;
                          
                          // Calculate cursor value using IDENTICAL scale as the chart drawing code
                          // CRITICAL: must match the 10% padding + limit inclusion used in the plot path
                          const dataPoints = chartState.dataMode === 'historian' ? 10000 : 300;
                          const allDataPoints = tags.flatMap(tag => {
                            const liveTrend = trendDataRef.current[tag.id];
                            return liveTrend ? liveTrend.slice(-dataPoints).map(d => d.value) : [];
                          });
                          const limitsForCursor = tags.flatMap(t => {
                            const lims: number[] = [];
                            if (t.loLimit !== undefined && t.loLimit !== 0) lims.push(t.loLimit);
                            if (t.hiLimit !== undefined && t.hiLimit !== 100) lims.push(t.hiLimit);
                            return lims;
                          });
                          const allCursorVals = [...allDataPoints, ...limitsForCursor];
                          if (allCursorVals.length === 0) { allCursorVals.push(0, 100); }
                          let cScaleMin = Math.min(...allCursorVals);
                          let cScaleMax = Math.max(...allCursorVals);
                          if (cScaleMin === cScaleMax) {
                            cScaleMin -= Math.abs(cScaleMin * 0.1 || 10);
                            cScaleMax += Math.abs(cScaleMax * 0.1 || 10);
                          }
                          // Apply SAME 10% padding the chart drawing uses
                          const cScaleRange = cScaleMax - cScaleMin;
                          const cPadding = cScaleRange * 0.1;
                          const minVal = cScaleMin - cPadding;
                          const maxVal = cScaleMax + cPadding;
                          const range = maxVal - minVal || 1;
                          const cursorValue = maxVal - (svgY / 400 * range);
                          
                          return (
                            <g>
                              {/* Vertical crosshair */}
                              <line 
                                x1={svgX} 
                                y1="0" 
                                x2={svgX} 
                                y2="400" 
                                stroke="#fbbf24" 
                                strokeWidth="1.5" 
                                strokeDasharray="4,3"
                                opacity="0.9" 
                              />
                              {/* Horizontal crosshair */}
                              <line 
                                x1="80" 
                                y1={svgY} 
                                x2="1200" 
                                y2={svgY} 
                                stroke="#fbbf24" 
                                strokeWidth="1.5" 
                                strokeDasharray="4,3"
                                opacity="0.9" 
                              />
                              {/* Value tooltip - Enhanced industrial style */}
                              <rect
                                x={svgX < 1050 ? svgX + 12 : svgX - 145}
                                y={svgY - 35}
                                width="130"
                                height="30"
                                fill="rgba(20, 25, 30, 0.95)"
                                stroke="#fbbf24"
                                strokeWidth="2"
                                rx="4"
                                filter="drop-shadow(0 2px 4px rgba(0,0,0,0.5))"
                              />
                              <text 
                                x={svgX < 1050 ? svgX + 18 : svgX - 139} 
                                y={svgY - 13} 
                                fill="#fbbf24" 
                                fontSize="13" 
                                fontFamily="Consolas, monospace"
                                fontWeight="700"
                              >
                                {cursorValue.toFixed(2)}{(() => {
                                  if (!unit || unit === 'N/A' || unit.startsWith('win_')) return '';
                                  const cleaned = unit.replace(/^\d+\s*/, '').trim();
                                  return cleaned ? ` ${cleaned}` : '';
                                })()}
                              </text>
                            </g>
                          );
                        })()}
                        
                        {/* X-Axis Time Labels - ENHANCED INDUSTRIAL STYLE */}
                        {(() => {
                          // Get first tag's trend data for time labels - WORKS FOR BOTH LIVE AND HISTORIAN
                          const firstTag = tags[0];
                          const liveTrendData = trendDataRef.current[firstTag?.id];
                          
                          // Show time labels for both live MQTT data and historian database data
                          if (!liveTrendData || liveTrendData.length === 0) {
                            // No data available - show message instead of generating fallback labels
                            return (
                              <g>
                                <rect x="0" y="400" width="1200" height="50" fill="rgba(15, 20, 25, 0.9)" />
                                <line x1="0" y1="400" x2="1200" y2="400" stroke="rgba(59, 130, 246, 0.6)" strokeWidth="2" />
                                <text x="640" y="425" fill="#60a5fa" fontSize="14" 
                                  fontFamily="Consolas, monospace" fontWeight="600" textAnchor="middle">
                                  NO DATA AVAILABLE
                                </text>
                              </g>
                            );
                          }
                          
                          // INDUSTRIAL NAVIGATION: Apply scroll offset to time labels
                          const scrollOffset = chartState.scrollOffset || 0;
                          
                          // CRITICAL FIX: Use intelligent downsampling for time labels too
                          let trendData;
                          if (chartState.dataMode === 'historian') {
                            const MAX_VISIBLE_POINTS = 500;
                            if (liveTrendData.length <= MAX_VISIBLE_POINTS) {
                              const endIndex = liveTrendData.length - scrollOffset;
                              const startIndex = Math.max(0, endIndex - liveTrendData.length);
                              trendData = liveTrendData.slice(startIndex, endIndex);
                            } else {
                              const endIndex = liveTrendData.length - scrollOffset;
                              const startIndex = Math.max(0, endIndex - MAX_VISIBLE_POINTS);
                              const availablePoints = endIndex - startIndex;
                              const sampleEvery = Math.max(1, Math.floor(availablePoints / MAX_VISIBLE_POINTS));
                              
                              trendData = [];
                              for (let i = startIndex; i < endIndex; i += sampleEvery) {
                                trendData.push(liveTrendData[i]);
                              }
                              if (trendData.length > 0 && trendData[trendData.length - 1] !== liveTrendData[endIndex - 1]) {
                                trendData.push(liveTrendData[endIndex - 1]);
                              }
                            }
                          } else {
                            const endIndex = liveTrendData.length - scrollOffset;
                            const startIndex = Math.max(0, endIndex - 30);
                            trendData = liveTrendData.slice(startIndex, endIndex);
                          }
                          
                          // Show fewer labels in historian mode to fit date+time
                          const isHistorian = chartState.dataMode === 'historian';
                          const hasCustomRange = chartState.customStartDate && chartState.customEndDate;
                          const labelCount = isHistorian ? Math.min(5, trendData.length) : Math.min(7, trendData.length);
                          const step = Math.max(1, Math.floor(trendData.length / (labelCount - 1)));
                          
                          // Calculate label width based on mode - wider for custom date range
                          const labelWidth = (isHistorian && hasCustomRange) ? (showMilliseconds ? 160 : 130) : (isHistorian ? (showMilliseconds ? 140 : 110) : (showMilliseconds ? 100 : 64));
                          const labelHalfWidth = labelWidth / 2;
                          
                          return (
                            <g>
                              {/* X-Axis Background Panel - Extra tall for custom date range (two-line display) */}
                              <rect x="0" y="400" width="1200" height={(isHistorian && hasCustomRange) ? "70" : (isHistorian ? "60" : "50")} fill="rgba(15, 20, 25, 0.9)" />
                              {/* X-Axis Border - Full width from edge to edge */}
                              <line x1="0" y1="400" x2="1200" y2="400" stroke="rgba(59, 130, 246, 0.6)" strokeWidth="2" />
                              
                              {/* Time Labels */}
                              {(() => {
                                const timeLabels = Array.from({ length: labelCount }, (_, i) => {
                                  const index = Math.min(i * step, trendData.length - 1);
                                  const point = trendData[index];
                                  
                                  // Safety check: skip if point is undefined
                                  if (!point || !point.time) {
                                    return null;
                                  }
                                  
                                  // Debug log for first label
                                  if (i === 0) {
                                  }
                                  
                                  // Position label using same padding as data points (80px left + 1040px data area)
                                  const x = 80 + ((index / (trendData.length - 1)) * 1040);
                                
                                return (
                                  <g key={i}>
                                    {/* Tick mark */}
                                    <line 
                                      x1={x} 
                                      y1="397" 
                                      x2={x} 
                                      y2="407" 
                                      stroke="rgba(59, 130, 246, 0.8)" 
                                      strokeWidth="2" 
                                    />
                                    {/* Time label with background - taller for custom date range (two-line display) */}
                                    <rect 
                                      x={x - labelHalfWidth} 
                                      y="410" 
                                      width={labelWidth} 
                                      height={(isHistorian && hasCustomRange) ? "34" : (isHistorian ? "24" : "18")} 
                                      fill="rgba(15, 20, 25, 0.9)"
                                      stroke={i === labelCount - 1 ? "rgba(251, 191, 36, 0.5)" : "rgba(59, 130, 246, 0.2)"}
                                      strokeWidth="0.5"
                                      rx="2"
                                    />
                                    {/* Display date+time in two lines for custom range, single line otherwise */}
                                    {(isHistorian && hasCustomRange) ? (
                                      <>
                                        {/* Date line (top) */}
                                        <text
                                          x={x}
                                          y={422}
                                          fill={i === labelCount - 1 ? "#fbbf24" : "#60a5fa"}
                                          fontSize="9"
                                          fontFamily="Consolas, monospace"
                                          fontWeight="700"
                                          textAnchor="middle"
                                        >
                                          {point.time.split(' ')[0]}
                                        </text>
                                        {/* Time line (bottom) */}
                                        <text
                                          x={x}
                                          y={435}
                                          fill={i === labelCount - 1 ? "#fbbf24" : "#60a5fa"}
                                          fontSize="8"
                                          fontFamily="Consolas, monospace"
                                          fontWeight={i === labelCount - 1 ? "700" : "500"}
                                          textAnchor="middle"
                                        >
                                          {point.time.split(' ')[1]}
                                        </text>
                                      </>
                                    ) : (
                                      <text
                                        x={x}
                                        y={isHistorian ? 427 : 422}
                                        fill={i === labelCount - 1 ? "#fbbf24" : "#60a5fa"}
                                        fontSize={isHistorian ? "9" : (showMilliseconds ? "10" : "12")}
                                        fontFamily="Consolas, monospace"
                                        fontWeight={i === labelCount - 1 ? "700" : "500"}
                                        textAnchor="middle"
                                      >
                                        {point.time}
                                      </text>
                                    )}
                                  </g>
                                );
                              });
                              return timeLabels;
                            })()}
                              
                              {/* Time Axis Label */}
                              <text 
                                x="1180" 
                                y="442" 
                                fill="#3b82f6" 
                                fontSize="12" 
                                fontFamily="Consolas, monospace"
                                fontWeight="700"
                                textAnchor="end"
                              >
                                TIME
                              </text>
                            </g>
                          );
                        })()}
                      </svg>
                      </div>
                    </div>
                  </div>
                  );
                    } catch (error) {
                      logError('[Chart Render Error]', error, 'Unit:', unit);
                      return (
                        <div key={unit} style={{ padding: '20px', color: '#ff0000', backgroundColor: '#1a1a1a', margin: '10px' }}>
                          Error rendering chart for unit "{unit}": {error instanceof Error ? error.message : String(error)}
                        </div>
                      );
                    }
                  });
                } catch (error) {
                  logError('[Chart Group Error]', error);
                  return (
                    <div style={{ padding: '20px', color: '#ff0000', backgroundColor: '#1a1a1a', margin: '10px' }}>
                      Error grouping charts: {error instanceof Error ? error.message : String(error)}
                    </div>
                  );
                }
              })()}
            </div>
          ) : (
            <div style={{
              flex: 1,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '16px',
              color: ISA_COLORS.valueDisabled
            }}>
              SELECT UP TO {MAX_SELECTED_TAGS} TAGS FROM ASSET TREE TO VIEW TRENDS
            </div>
          )}
          </div>

        </div>

        {/* RIGHT - ALARM, TRIP & INTERLOCK PANEL */}
        <div style={{
            width: '350px',
            backgroundColor: ISA_COLORS.panel,
            borderLeft: `2px solid ${ISA_COLORS.border}`,
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
            gap: '4px',
            padding: '8px',
            height: '100%'
          }}>
            <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {/* ALARMS — takes all available space */}
              <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', border: `1px solid ${ISA_COLORS.border}`, backgroundColor: 'rgba(0,0,0,0.2)' }}>
                <div style={{ padding: '4px 8px', fontSize: '10px', fontWeight: 700, letterSpacing: '0.8px', color: ISA_COLORS.foreground, borderBottom: `1px solid ${ISA_COLORS.border}`, flexShrink: 0 }}>
                  ALARMS
                </div>
                <div style={{ flex: 1, minHeight: 0 }}>
                  {canViewAlarms ? <AlarmPanel /> : (
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#6b7280', fontSize: '13px' }}>No alarm access</div>
                  )}
                </div>
              </div>

            </div>
          </div>
      </div>

      {/* Industrial Tooltip - Shows Avg/Min/Max on hover */}
      {tooltip && tooltip.visible && (
        <div
          style={{
            position: 'fixed',
            left: `${tooltip.x}px`,
            top: `${tooltip.y}px`,
            transform: 'translate(-50%, -100%)',
            backgroundColor: ISA_COLORS.panel,
            border: `2px solid ${ISA_COLORS.border}`,
            padding: '12px 16px',
            borderRadius: '4px',
            fontSize: '12px',
            fontFamily: 'Consolas, monospace',
            color: ISA_COLORS.foreground,
            pointerEvents: 'none',
            zIndex: 10000,
            minWidth: '200px',
            boxShadow: '0 4px 12px rgba(0,0,0,0.8)'
          }}
        >
          <div style={{ fontWeight: 'bold', marginBottom: '8px', color: ISA_COLORS.valueNormal }}>
            {tooltip.tagName}
          </div>
          <div style={{ fontSize: '10px', color: ISA_COLORS.valueDisabled, marginBottom: '8px' }}>
            {tooltip.data.time}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: ISA_COLORS.valueDisabled }}>{tooltip.isAggregated ? 'Average:' : 'Value:'}</span>
              <span style={{ fontWeight: 'bold', color: '#3b82f6' }}>{tooltip.data.value.toFixed(2)}</span>
            </div>
            {tooltip.data.min !== undefined && (
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: ISA_COLORS.valueDisabled }}>Minimum:</span>
                <span style={{ fontWeight: 'bold', color: '#10b981' }}>{tooltip.data.min.toFixed(2)}</span>
              </div>
            )}
            {tooltip.data.max !== undefined && (
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: ISA_COLORS.valueDisabled }}>Maximum:</span>
                <span style={{ fontWeight: 'bold', color: '#ef4444' }}>{tooltip.data.max.toFixed(2)}</span>
              </div>
            )}
            {tooltip.data.count !== undefined && (
              <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '4px', paddingTop: '4px', borderTop: `1px solid ${ISA_COLORS.border}` }}>
                <span style={{ color: ISA_COLORS.valueDisabled }}>Points:</span>
                <span style={{ color: ISA_COLORS.foreground }}>{tooltip.data.count}</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* RBAC: Critical Operation Approval Modal */}
      <CriticalOperationModal
        isOpen={isApprovalModalOpen}
        onClose={cancelOperation}
        operationCode={pendingOperation?.code || ''}
        operationName={pendingOperation?.code || 'Critical Operation'}
        targetEquipment={pendingOperation?.equipmentName || ''}
        targetTag={pendingOperation?.equipmentId || ''}
        currentValue={''}
        targetValue={''}
        onApprovalReceived={onApprovalGranted}
      />

      {/* Debug Panel for Tag Data Inspection */}
      {showDebugPanel && (
        <div style={{
          position: 'fixed',
          top: '60px',
          right: '20px',
          width: '600px',
          maxHeight: '80vh',
          backgroundColor: ISA_COLORS.panel,
          border: `2px solid ${ISA_COLORS.alarmCritical}`,
          borderRadius: '6px',
          padding: '16px',
          zIndex: 10001,
          overflow: 'auto',
          fontFamily: 'Consolas, monospace',
          fontSize: '11px',
          boxShadow: '0 8px 24px rgba(0,0,0,0.9)'
        }}>
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: '16px',
            paddingBottom: '12px',
            borderBottom: `1px solid ${ISA_COLORS.border}`
          }}>
            <span style={{ 
              color: ISA_COLORS.alarmCritical, 
              fontWeight: 'bold', 
              fontSize: '14px' 
            }}>
              🐛 DEBUG PANEL - Tag Data Inspector
            </span>
            <button
              onClick={() => setShowDebugPanel(false)}
              style={{
                padding: '4px 12px',
                backgroundColor: ISA_COLORS.alarmCritical,
                color: ISA_COLORS.background,
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer',
                fontWeight: 'bold'
              }}
            >
              CLOSE
            </button>
          </div>

          {/* Section 1: Selected Tags Array */}
          <div style={{ marginBottom: '20px' }}>
            <div style={{ 
              color: '#60a5fa', 
              fontWeight: 'bold', 
              marginBottom: '8px',
              fontSize: '12px'
            }}>
              📊 Selected Tags Array ({selectedTags.length} tags)
            </div>
            <div style={{
              backgroundColor: ISA_COLORS.background,
              padding: '12px',
              borderRadius: '4px',
              border: `1px solid ${ISA_COLORS.border}`,
              maxHeight: '250px',
              overflow: 'auto'
            }}>
              <pre style={{ 
                margin: 0, 
                color: ISA_COLORS.foreground,
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word'
              }}>
                {JSON.stringify(selectedTags, null, 2)}
              </pre>
            </div>
          </div>

          {/* Section 2: localStorage Inspection */}
          <div style={{ marginBottom: '20px' }}>
            <div style={{ 
              color: '#60a5fa', 
              fontWeight: 'bold', 
              marginBottom: '8px',
              fontSize: '12px'
            }}>
              💾 localStorage Content
            </div>
            <div style={{
              backgroundColor: ISA_COLORS.background,
              padding: '12px',
              borderRadius: '4px',
              border: `1px solid ${ISA_COLORS.border}`,
              maxHeight: '200px',
              overflow: 'auto'
            }}>
              <div style={{ color: '#10b981', marginBottom: '8px' }}>
                <strong>hmi_selected_tags_full:</strong>
              </div>
              <pre style={{ 
                margin: 0, 
                color: ISA_COLORS.foreground,
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word'
              }}>
                {localStorage.getItem('hmi_selected_tags_full') || 'Not found'}
              </pre>
              <div style={{ color: '#10b981', marginTop: '12px', marginBottom: '8px' }}>
                <strong>hmi_selected_tag_ids:</strong>
              </div>
              <pre style={{ 
                margin: 0, 
                color: ISA_COLORS.foreground,
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word'
              }}>
                {localStorage.getItem('hmi_selected_tag_ids') || 'Not found'}
              </pre>
            </div>
          </div>

          {/* Section 3: Context Field Validation */}
          <div style={{ marginBottom: '20px' }}>
            <div style={{ 
              color: '#60a5fa', 
              fontWeight: 'bold', 
              marginBottom: '8px',
              fontSize: '12px'
            }}>
              📍 Context Field Validation
            </div>
            <div style={{
              backgroundColor: ISA_COLORS.background,
              padding: '12px',
              borderRadius: '4px',
              border: `1px solid ${ISA_COLORS.border}`
            }}>
              {selectedTags.length === 0 ? (
                <div style={{ color: ISA_COLORS.valueDisabled }}>
                  No tags selected
                </div>
              ) : (
                selectedTags.map((tag, idx) => {
                  const hasContext = !!(tag.plant || tag.area || tag.equipment);
                  return (
                    <div 
                      key={idx}
                      style={{ 
                        marginBottom: '8px',
                        paddingBottom: '8px',
                        borderBottom: idx < selectedTags.length - 1 ? `1px solid ${ISA_COLORS.border}` : 'none'
                      }}
                    >
                      <div style={{ 
                        color: hasContext ? '#10b981' : '#ef4444',
                        fontWeight: 'bold'
                      }}>
                        {hasContext ? '✅' : '❌'} {tag.name || tag.id}
                      </div>
                      <div style={{ 
                        fontSize: '10px', 
                        color: ISA_COLORS.valueDisabled,
                        marginTop: '4px',
                        marginLeft: '20px'
                      }}>
                        Plant: {tag.plant || '(missing)'}<br />
                        Area: {tag.area || '(missing)'}<br />
                        Equipment: {tag.equipment || '(missing)'}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          {/* Section 4: Quick Actions */}
          <div>
            <div style={{ 
              color: '#60a5fa', 
              fontWeight: 'bold', 
              marginBottom: '8px',
              fontSize: '12px'
            }}>
              ⚡ Quick Actions
            </div>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                onClick={() => {
                  localStorage.removeItem('hmi_selected_tags_full');
                  localStorage.removeItem('hmi_selected_tag_ids');
                  alert('localStorage cleared. Please refresh the page.');
                }}
                style={{
                  padding: '6px 12px',
                  backgroundColor: '#ef4444',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  fontSize: '11px',
                  fontWeight: 'bold'
                }}
              >
                🗑️ Clear localStorage
              </button>
              <button
                onClick={() => {
                  const data = {
                    selectedTags,
                    localStorage: {
                      hmi_selected_tags_full: localStorage.getItem('hmi_selected_tags_full'),
                      hmi_selected_tag_ids: localStorage.getItem('hmi_selected_tag_ids')
                    },
                    timestamp: new Date().toISOString()
                  };
                  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement('a');
                  a.href = url;
                  a.download = `tag-debug-${Date.now()}.json`;
                  a.click();
                  URL.revokeObjectURL(url);
                }}
                style={{
                  padding: '6px 12px',
                  backgroundColor: '#3b82f6',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  fontSize: '11px',
                  fontWeight: 'bold'
                }}
              >
                💾 Export Debug Data
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Predictive Trend Modal — opens when a warning row is clicked ── */}
      {predictiveTrendTag && (
        <PredictiveTrendModal
          tagId={predictiveTrendTag.id}
          tagName={predictiveTrendTag.name}
          onClose={() => setPredictiveTrendTag(null)}
        />
      )}

      <style>{`
        @keyframes flash {
          0%, 50%, 100% { opacity: 1; }
          25%, 75% { opacity: 0.7; }
        }
      `}</style>
    </div>
  );
};




