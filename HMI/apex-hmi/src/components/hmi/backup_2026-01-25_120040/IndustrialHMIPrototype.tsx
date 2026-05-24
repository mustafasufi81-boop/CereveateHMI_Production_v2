import { useState, useEffect } from "react";
import { Activity, AlertTriangle, Wifi, Database, Settings, User, LogOut, TrendingUp } from "lucide-react";
import { cn } from "@/lib/utils";

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

// Generate trend data (last 30 points)
const generateTrendData = (baseValue: number, variance: number, minutes: number = 30) => {
  const dataPoints = 30; // Always generate 30 points for smooth curves
  return Array.from({ length: dataPoints }, (_, i) => ({
    time: new Date(Date.now() - (minutes - (i * minutes / (dataPoints - 1))) * 60000).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }),
    value: baseValue + (Math.sin(i / 3) * variance) + (Math.random() * variance * 0.3)
  }));
};

// Tag colors for multi-selection
const TAG_TREND_COLORS = [
  '#00FF00', // Bright Green
  '#00FFFF', // Cyan
  '#FF00FF', // Magenta
  '#FFFF00', // Yellow
  '#FF8800', // Orange
];

export const IndustrialHMIPrototype = () => {
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set(['plant-001', 'area-100', 'eq-comp-101']));
  const [selectedAsset, setSelectedAsset] = useState<Asset | null>(null);
  const [selectedTags, setSelectedTags] = useState<Tag[]>([]); // Changed to array for multi-selection
  const [alarms, setAlarms] = useState<Alarm[]>(INITIAL_ALARMS);
  const [currentTime, setCurrentTime] = useState(new Date());
  const [zoomLevel, setZoomLevel] = useState(1); // Zoom level: 1 = normal, 2 = 2x, 0.5 = 50%
  
  // Per-unit chart states: each unit has independent mode, time range, and date picker
  const [chartStates, setChartStates] = useState<Record<string, {
    dataMode: 'live' | 'historian';
    timeRange: number;
    showCustomDatePicker: boolean;
    customStartDate: string;
    customEndDate: string;
  }>>({});
  
  const [systemStatus] = useState({
    plc: true,
    opc: true,
    historian: true,
    alarmCount: { p1: 1, p2: 1, p3: 0 }
  });

  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

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
        return prev.filter(t => t.id !== tag.id);
      } else {
        // Select (max 5 tags)
        if (prev.length >= 5) {
          alert('Maximum 5 tags allowed for trend display');
          return prev;
        }
        return [...prev, tag];
      }
    });
  };

  const acknowledgeAlarm = (id: string) => {
    setAlarms(prev => prev.map(alm => alm.id === id ? { ...alm, acknowledged: true } : alm));
  };

  // Helper function to get or initialize chart state for a unit
  const getChartState = (unit: string) => {
    if (!chartStates[unit]) {
      return {
        dataMode: 'live' as const,
        timeRange: 5,
        showCustomDatePicker: false,
        customStartDate: '',
        customEndDate: ''
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
      const start = new Date(state.customStartDate);
      const end = new Date(state.customEndDate);
      const diffMinutes = Math.floor((end.getTime() - start.getTime()) / 60000);
      updateChartState(unit, {
        timeRange: diffMinutes,
        showCustomDatePicker: false
      });
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
      {/* ALARM BANNER - Priority 1 (Flashing) */}
      {activeP1Alarm && (
        <div style={{
          height: '48px',
          backgroundColor: ISA_COLORS.alarmP1,
          color: '#FFFFFF',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0 16px',
          borderBottom: `2px solid #000000`,
          animation: 'flash 1s infinite',
          fontWeight: 700,
          fontSize: '14px',
          fontFamily: 'Consolas, monospace'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <AlertTriangle style={{ width: '24px', height: '24px' }} />
            <span>[{activeP1Alarm.timestamp}]</span>
            <span>{activeP1Alarm.message}</span>
            {activeP1Alarm.value && <span>VALUE: {activeP1Alarm.value}</span>}
          </div>
          <button
            onClick={() => acknowledgeAlarm(activeP1Alarm.id)}
            style={{
              padding: '6px 16px',
              backgroundColor: '#FFFFFF',
              color: '#000000',
              border: '2px solid #000000',
              cursor: 'pointer',
              fontWeight: 700,
              fontSize: '12px'
            }}
          >
            ACKNOWLEDGE
          </button>
        </div>
      )}

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
            <div style={{ width: '12px', height: '12px', borderRadius: '50%', backgroundColor: systemStatus.plc ? ISA_COLORS.statusOnline : ISA_COLORS.statusOffline }} />
            <span>PLC: {systemStatus.plc ? 'ONLINE' : 'OFFLINE'}</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Wifi style={{ width: '14px', height: '14px', color: systemStatus.opc ? ISA_COLORS.statusOnline : ISA_COLORS.statusOffline }} />
            <span>OPC: {systemStatus.opc ? 'CONNECTED' : 'DISCONNECTED'}</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Database style={{ width: '14px', height: '14px', color: systemStatus.historian ? ISA_COLORS.statusOnline : ISA_COLORS.statusOffline }} />
            <span>HISTORIAN: {systemStatus.historian ? 'LOGGING' : 'STOPPED'}</span>
          </div>
          <div style={{ display: 'flex', gap: '16px', marginLeft: '24px' }}>
            <span style={{ color: ISA_COLORS.alarmP1, fontWeight: 700 }}>P1: {systemStatus.alarmCount.p1}</span>
            <span style={{ color: ISA_COLORS.alarmP2, fontWeight: 700 }}>P2: {systemStatus.alarmCount.p2}</span>
            <span style={{ color: ISA_COLORS.alarmP3, fontWeight: 700 }}>P3: {systemStatus.alarmCount.p3}</span>
          </div>
        </div>
        <div style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
          <span>{currentTime.toLocaleString('en-US', { hour12: false, month: '2-digit', day: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>
          <span>MODE: AUTO</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <User style={{ width: '14px', height: '14px' }} />
            <span>OPERATOR</span>
          </div>
        </div>
      </div>

      {/* MAIN CONTENT */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* LEFT - ASSET TREE */}
        <div style={{
          width: '280px',
          backgroundColor: ISA_COLORS.panel,
          borderRight: `2px solid ${ISA_COLORS.border}`,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden'
        }}>
          <div style={{
            padding: '12px 16px',
            borderBottom: `2px solid ${ISA_COLORS.border}`,
            fontWeight: 700,
            fontSize: '13px',
            textTransform: 'uppercase',
            backgroundColor: 'rgba(0,0,0,0.3)'
          }}>
            ASSET TAXONOMY
          </div>
          <div style={{ flex: 1, overflow: 'auto' }}>
            {renderAssetTree(ASSET_TREE)}
          </div>
        </div>

        {/* CENTER - TAG FACEPLATE / TRENDS */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'auto' }}>
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
                      {selectedTags[0].value.toFixed(1)}
                    </div>
                    <div style={{ fontSize: '20px', color: ISA_COLORS.foreground, marginTop: '8px' }}>
                      {selectedTags[0].unit}
                    </div>
                  </div>

                  {/* LIMITS & SETPOINT */}
                  <div style={{
                    display: 'grid',
                    gridTemplateColumns: '1fr 1fr 1fr',
                    gap: '16px',
                    padding: '16px',
                    backgroundColor: 'rgba(0,0,0,0.3)',
                    border: `1px solid ${ISA_COLORS.border}`
                  }}>
                    <div>
                      <div style={{ fontSize: '10px', color: ISA_COLORS.foreground, marginBottom: '4px' }}>SETPOINT</div>
                      <div style={{ fontSize: '18px', fontFamily: 'Consolas, monospace', color: ISA_COLORS.valueNormal }}>{selectedTags[0].sp}</div>
                    </div>
                    <div>
                      <div style={{ fontSize: '10px', color: ISA_COLORS.foreground, marginBottom: '4px' }}>HI LIMIT</div>
                      <div style={{ fontSize: '18px', fontFamily: 'Consolas, monospace', color: ISA_COLORS.alarmP1 }}>{selectedTags[0].hiLimit}</div>
                    </div>
                    <div>
                      <div style={{ fontSize: '10px', color: ISA_COLORS.foreground, marginBottom: '4px' }}>LO LIMIT</div>
                      <div style={{ fontSize: '18px', fontFamily: 'Consolas, monospace', color: ISA_COLORS.alarmP1 }}>{selectedTags[0].loLimit}</div>
                    </div>
                  </div>

                  {/* MODE CONTROL */}
                  <div style={{
                    display: 'flex',
                    gap: '8px',
                    justifyContent: 'center'
                  }}>
                    {['AUTO', 'MANUAL', 'HAND'].map(mode => (
                      <button
                        key={mode}
                        style={{
                          padding: '12px 24px',
                          backgroundColor: selectedTags[0].mode.toUpperCase() === mode ? ISA_COLORS.statusOnline : ISA_COLORS.panel,
                          color: selectedTags[0].mode.toUpperCase() === mode ? '#000000' : ISA_COLORS.foreground,
                          border: `2px solid ${ISA_COLORS.border}`,
                          cursor: 'pointer',
                          fontWeight: 700,
                          fontSize: '13px',
                          boxShadow: selectedTags[0].mode.toUpperCase() === mode ? 'inset 0 2px 4px rgba(0,0,0,0.3)' : 'none'
                        }}
                      >
                        {mode}
                      </button>
                    ))}
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
                    SELECTED TAGS ({selectedTags.length}/5)
                  </div>
                  <div style={{ padding: '16px', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '12px' }}>
                    {selectedTags.map((tag, index) => (
                      <div key={tag.id} style={{
                        padding: '12px',
                        backgroundColor: 'rgba(0,0,0,0.3)',
                        border: `2px solid ${TAG_TREND_COLORS[index % TAG_TREND_COLORS.length]}`,
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '8px'
                      }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <div style={{
                            width: '12px',
                            height: '12px',
                            borderRadius: '50%',
                            backgroundColor: TAG_TREND_COLORS[index % TAG_TREND_COLORS.length]
                          }} />
                          <span style={{ fontFamily: 'Consolas, monospace', fontSize: '12px', fontWeight: 700 }}>{tag.name}</span>
                        </div>
                        <div style={{ fontSize: '11px', color: ISA_COLORS.foreground }}>{tag.description}</div>
                        <div style={{
                          fontSize: '24px',
                          fontFamily: 'Consolas, monospace',
                          color: TAG_TREND_COLORS[index % TAG_TREND_COLORS.length],
                          fontWeight: 700
                        }}>
                          {tag.value.toFixed(1)} {tag.unit}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* TREND CHARTS - Grouped by Unit */}
              {(() => {
                // Group tags by unit
                const tagsByUnit = selectedTags.reduce((acc, tag) => {
                  if (!acc[tag.unit]) {
                    acc[tag.unit] = [];
                  }
                  acc[tag.unit].push(tag);
                  return acc;
                }, {} as Record<string, Tag[]>);

                return Object.entries(tagsByUnit).map(([unit, tags]) => {
                  const chartState = getChartState(unit);
                  
                  return (
                  <div key={unit} style={{
                    backgroundColor: ISA_COLORS.panel,
                    border: `2px solid ${ISA_COLORS.border}`,
                    boxShadow: 'inset 0 2px 4px rgba(0,0,0,0.5)'
                  }}>
                    <div style={{
                      padding: '12px 16px',
                      borderBottom: `2px solid ${ISA_COLORS.border}`,
                      backgroundColor: 'rgba(0,0,0,0.3)',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center'
                    }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <TrendingUp style={{ width: '16px', height: '16px' }} />
                          <span style={{ fontWeight: 700, fontSize: '13px' }}>
                            TREND - {chartState.dataMode === 'live' ? 'LAST 5 MINUTES' : `LAST ${chartState.timeRange >= 60 ? `${(chartState.timeRange / 60).toFixed(0)} HR${chartState.timeRange >= 120 ? 'S' : ''}` : `${chartState.timeRange} MIN`}`} ({unit})
                          </span>
                        </div>
                        
                        {/* Live / Historian Switch */}
                        <div style={{ display: 'flex', gap: '4px', backgroundColor: 'rgba(0,0,0,0.3)', padding: '4px', border: `1px solid ${ISA_COLORS.border}` }}>
                          <button
                            onClick={() => updateChartState(unit, { dataMode: 'live' })}
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
                            onClick={() => updateChartState(unit, { dataMode: 'historian' })}
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
                        
                        {/* Time Range Filter - Only show in Historian mode */}
                        {chartState.dataMode === 'historian' && (
                          <div style={{ display: 'flex', gap: '4px', backgroundColor: 'rgba(0,0,0,0.3)', padding: '4px', border: `1px solid ${ISA_COLORS.border}`, flexWrap: 'wrap' }}>
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
                                backgroundColor: chartState.showCustomDatePicker ? '#3b82f6' : 'transparent',
                                color: chartState.showCustomDatePicker ? '#FFFFFF' : ISA_COLORS.foreground,
                                border: 'none',
                                cursor: 'pointer',
                                fontWeight: 700,
                                fontSize: '10px',
                                fontFamily: 'Consolas, monospace'
                              }}
                            >
                              CUSTOM
                            </button>
                          </div>
                        )}
                        
                        {/* Tag Names for this unit */}
                        <div style={{ display: 'flex', gap: '12px', alignItems: 'center', flexWrap: 'wrap' }}>
                          {tags.map((tag, idx) => {
                            const tagIndex = selectedTags.findIndex(t => t.id === tag.id);
                            return (
                              <div key={tag.id} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
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
                                  {tag.name}
                                </span>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                      
                      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        {/* Zoom Controls */}
                        <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
                          <span style={{ fontSize: '10px', color: ISA_COLORS.foreground, marginRight: '4px' }}>ZOOM:</span>
                          <button
                            onClick={() => setZoomLevel(prev => Math.min(prev + 0.25, 3))}
                            style={{
                              padding: '4px 8px',
                              backgroundColor: ISA_COLORS.panel,
                              color: ISA_COLORS.foreground,
                              border: `1px solid ${ISA_COLORS.border}`,
                              cursor: 'pointer',
                              fontWeight: 700,
                              fontSize: '14px'
                            }}
                            title="Zoom In"
                          >
                            +
                          </button>
                          <span style={{ 
                            fontSize: '11px', 
                            fontFamily: 'Consolas, monospace',
                            minWidth: '40px',
                            textAlign: 'center',
                            color: ISA_COLORS.valueNormal
                          }}>
                            {(zoomLevel * 100).toFixed(0)}%
                          </span>
                          <button
                            onClick={() => setZoomLevel(prev => Math.max(prev - 0.25, 0.5))}
                            style={{
                              padding: '4px 8px',
                              backgroundColor: ISA_COLORS.panel,
                              color: ISA_COLORS.foreground,
                              border: `1px solid ${ISA_COLORS.border}`,
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
                              padding: '4px 12px',
                              backgroundColor: ISA_COLORS.panel,
                              color: ISA_COLORS.foreground,
                              border: `1px solid ${ISA_COLORS.border}`,
                              cursor: 'pointer',
                              fontWeight: 700,
                              fontSize: '10px',
                              fontFamily: 'Consolas, monospace'
                            }}
                            title="Reset Zoom"
                          >
                            RESET
                          </button>
                        </div>
                        <span style={{ fontSize: '11px', fontFamily: 'Consolas, monospace' }}>UPDATE: 1s</span>
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
                            onChange={(e) => updateChartState(unit, { customStartDate: e.target.value })}
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
                            onChange={(e) => updateChartState(unit, { customEndDate: e.target.value })}
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
                    
                    {/* SVG LINE CHART */}
                    <div style={{ padding: '16px', overflow: 'auto', backgroundColor: '#0a0a0b' }}>
                      <svg 
                        width={1200 * zoomLevel} 
                        height={400} 
                        viewBox={`0 0 ${1200 * zoomLevel} 400`} 
                        preserveAspectRatio="none"
                      >
                        {/* Grid Lines */}
                        <defs>
                          <pattern id={`grid-${unit}`} width="40" height="40" patternUnits="userSpaceOnUse">
                            <path d="M 40 0 L 0 0 0 40" fill="none" stroke={ISA_COLORS.border} strokeWidth="0.5" opacity="0.5"/>
                          </pattern>
                        </defs>
                        <rect width={1200 * zoomLevel} height="400" fill={`url(#grid-${unit})`} />
                        
                        {/* Calculate common min/max for tags with same unit */}
                        {(() => {
                          const allLimits = tags.flatMap(t => [t.loLimit || 0, t.hiLimit || 100]);
                          const commonMin = Math.min(...allLimits);
                          const commonMax = Math.max(...allLimits);
                          const range = commonMax - commonMin;
                          
                          // Y-axis reference lines and labels
                          const steps = 5;
                          return Array.from({ length: steps + 1 }, (_, i) => {
                            const value = commonMin + (range * i / steps);
                            const yPos = 400 - (i * 400 / steps);
                            return (
                              <g key={i}>
                                <line 
                                  x1="0" 
                                  y1={yPos} 
                                  x2={1200 * zoomLevel} 
                                  y2={yPos} 
                                  stroke={ISA_COLORS.border} 
                                  strokeWidth="1" 
                                  opacity="0.5" 
                                />
                                <text 
                                  x="10" 
                                  y={yPos - 5} 
                                  fill={ISA_COLORS.foreground} 
                                  fontSize="12" 
                                  fontFamily="Consolas"
                                  fontWeight="700"
                                >
                                  {value.toFixed(1)}
                                </text>
                              </g>
                            );
                          });
                        })()}
                        
                        {/* Plot trend lines for each tag in this unit group */}
                        {tags.map((tag) => {
                          const tagIndex = selectedTags.findIndex(t => t.id === tag.id);
                          // Use different time range for historian mode vs live mode
                          const minutesRange = chartState.dataMode === 'live' ? 5 : chartState.timeRange;
                          const dataPoints = chartState.dataMode === 'historian' ? Math.min(Math.floor(chartState.timeRange / 2), 60) : 30;
                          const trendData = generateTrendData(tag.value, 5, minutesRange).slice(0, dataPoints);
                          
                          // Use common scale for all tags with same unit
                          const allLimits = tags.flatMap(t => [t.loLimit || 0, t.hiLimit || 100]);
                          const minVal = Math.min(...allLimits);
                          const maxVal = Math.max(...allLimits);
                          const range = maxVal - minVal;
                          
                          // Generate SVG path
                          const pathData = trendData.map((point, i) => {
                            const x = (i / (trendData.length - 1)) * 1200 * zoomLevel;
                            const normalizedValue = ((point.value - minVal) / range);
                            const y = 400 - (normalizedValue * 400);
                            return `${i === 0 ? 'M' : 'L'} ${x} ${y}`;
                          }).join(' ');
                          
                          return (
                            <g key={tag.id}>
                              {/* Trend Line */}
                              <path
                                d={pathData}
                                fill="none"
                                stroke={TAG_TREND_COLORS[tagIndex % TAG_TREND_COLORS.length]}
                                strokeWidth="3"
                                opacity="0.9"
                              />
                              {/* Data Points */}
                              {trendData.map((point, i) => {
                                const x = (i / (trendData.length - 1)) * 1200 * zoomLevel;
                                const normalizedValue = ((point.value - minVal) / range);
                                const y = 400 - (normalizedValue * 400);
                                return (
                                  <circle
                                    key={i}
                                    cx={x}
                                    cy={y}
                                    r="3"
                                    fill={TAG_TREND_COLORS[tagIndex % TAG_TREND_COLORS.length]}
                                    stroke="#000000"
                                    strokeWidth="1"
                                    opacity={0.7 + (i / trendData.length) * 0.3}
                                  >
                                    <title>{`${tag.name}: ${point.value.toFixed(1)} ${tag.unit} at ${point.time}`}</title>
                                  </circle>
                                );
                              })}
                            </g>
                          );
                        })}
                      </svg>
                    </div>
                  </div>
                  );
                });
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
              SELECT UP TO 5 TAGS FROM ASSET TREE TO VIEW TRENDS
            </div>
          )}
        </div>

        {/* RIGHT - ALARM LIST */}
        <div style={{
          width: '400px',
          backgroundColor: ISA_COLORS.panel,
          borderLeft: `2px solid ${ISA_COLORS.border}`,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden'
        }}>
          <div style={{
            padding: '12px 16px',
            borderBottom: `2px solid ${ISA_COLORS.border}`,
            fontWeight: 700,
            fontSize: '13px',
            textTransform: 'uppercase',
            backgroundColor: 'rgba(0,0,0,0.3)',
            display: 'flex',
            justifyContent: 'space-between'
          }}>
            <span>ACTIVE ALARMS</span>
            <span>TOTAL: {alarms.length}</span>
          </div>
          <div style={{ flex: 1, overflow: 'auto' }}>
            {alarms.map(alarm => {
              const bgColor = alarm.priority === 1 ? ISA_COLORS.alarmP1 :
                             alarm.priority === 2 ? ISA_COLORS.alarmP2 :
                             ISA_COLORS.alarmP3;
              return (
                <div
                  key={alarm.id}
                  style={{
                    padding: '12px',
                    borderBottom: `1px solid ${ISA_COLORS.border}`,
                    backgroundColor: alarm.acknowledged ? ISA_COLORS.panel : bgColor,
                    color: alarm.acknowledged ? ISA_COLORS.foreground : '#000000',
                    opacity: alarm.acknowledged ? 0.6 : 1,
                    fontSize: '11px',
                    fontFamily: 'Consolas, monospace'
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                    <span style={{ fontWeight: 700 }}>P{alarm.priority} - {alarm.tagId}</span>
                    <span>{alarm.timestamp}</span>
                  </div>
                  <div style={{ marginBottom: '8px' }}>{alarm.message}</div>
                  {!alarm.acknowledged && (
                    <button
                      onClick={() => acknowledgeAlarm(alarm.id)}
                      style={{
                        padding: '4px 12px',
                        backgroundColor: '#000000',
                        color: '#FFFFFF',
                        border: '1px solid #FFFFFF',
                        cursor: 'pointer',
                        fontSize: '10px',
                        fontWeight: 700
                      }}
                    >
                      ACK
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>

      <style>{`
        @keyframes flash {
          0%, 50%, 100% { opacity: 1; }
          25%, 75% { opacity: 0.7; }
        }
      `}</style>
    </div>
  );
};
