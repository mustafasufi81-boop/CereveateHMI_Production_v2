// Enhanced Industrial HMI Dashboard - ISA-101 Compliant with P&ID Integration
// Merges IndustrialHMIPrototype visual design with HMIDashboard functionality

import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { Activity, AlertTriangle, Wifi, Database, Settings, User, LogOut, TrendingUp, Shield, Clock, Gauge, History } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/auth-context";
import { ProcessGraphic, sampleCompressorConfig, samplePumpConfig } from "./p&id";
import { AssetSidebar } from "./AssetSidebar";
import { UserHeader } from "./UserHeader";
import { LiveDataPanel } from "./LiveDataPanel";
import { HistoricalDataPanel } from "./HistoricalDataPanel";
import { TagValuePanel } from "./TagValuePanel";
import mqttWebSocketService from "@/services/mqtt-websocket";
import { cn } from "@/lib/utils";
import { MAX_SELECTED_TAGS } from "@/config/isa101-trend-config";

// ISA-101 Compliant Color System
const ISA_COLORS = {
  background: '#1C1C1E',
  foreground: '#E5E5E5',
  panel: '#2A2A2C',
  border: '#404040',
  
  equipmentRunning: '#00C851',
  equipmentStopped: '#808080',
  equipmentAlarm: '#FF4444',
  equipmentWarning: '#FFB300',
  
  valueNormal: '#00FF00',
  valueWarning: '#FFFF00',
  valueAlarm: '#FF0000',
  valueDisabled: '#666666',
  
  alarmP1: '#FF0000',
  alarmP2: '#FFB300',
  alarmP3: '#FFFF00',
  
  statusOnline: '#00C851',
  statusOffline: '#FF4444',
};

interface TreeNode {
  id: string;
  name: string;
  type: "plant" | "area" | "equipment" | "sub_equipment" | "component" | "tag";
  hasAlarm?: boolean;
  tag_count?: number;
  tags?: any[];
  children?: TreeNode[];
}

export const EnhancedHMIDashboard = () => {
  const { user } = useAuth();
  const [selectedEquipment, setSelectedEquipment] = useState("eq-m101");
  const [selectedNode, setSelectedNode] = useState<TreeNode | null>(null);
  const [activeTab, setActiveTab] = useState<"live" | "historian" | "p&id">("live");
  const [selectedTags, setSelectedTags] = useState<string[]>([]); // Max tags configurable
  const [selectedPID, setSelectedPID] = useState<"compressor" | "pump">("compressor");
  const [currentTime, setCurrentTime] = useState(new Date());
  // Real-time data for P&ID - Populated ONLY from MQTT (no static data)
  const [realTimeData, setRealTimeData] = useState<Record<string, any>>({});

  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  // MQTT WebSocket connection for real-time P&ID data
  useEffect(() => {
    console.log('🔌 [EnhancedHMI] Connecting to WebSocket for P&ID real-time data...');
    mqttWebSocketService.connect();

    const handleMQTTUpdate = (data: any) => {
      if (data.tags && Array.isArray(data.tags)) {
        const pidUpdates: Record<string, any> = {};
        
        data.tags.forEach((tag: any) => {
          const tagId = tag.tag_id;
          const value = tag.value_num ?? tag.value_text ?? tag.value_bool;
          
          if (tagId && value !== undefined) {
            // Determine status based on value and quality
            const status = tag.quality === 'GOOD' 
              ? (value > (tag.hi_limit || 1000) ? 'alarm' : (value > (tag.hi_warning || 900) ? 'warning' : 'normal'))
              : 'offline';
            
            pidUpdates[tagId] = {
              value: value,
              unit: tag.eng_unit || '',
              status: status,
              description: tag.description || tagId,
              timestamp: tag.time || new Date().toISOString()
            };
          }
        });
        
        if (Object.keys(pidUpdates).length > 0) {
          console.log(`✅ [EnhancedHMI P&ID] Updating ${Object.keys(pidUpdates).length} tags:`, Object.keys(pidUpdates));
          setRealTimeData(prev => ({ ...prev, ...pidUpdates }));
        }
      }
    };

    mqttWebSocketService.on('mqtt_tag_update', handleMQTTUpdate);

    return () => {
      mqttWebSocketService.off('mqtt_tag_update', handleMQTTUpdate);
    };
  }, []);

  const handleAssetSelect = (id: string, node?: TreeNode) => {
    console.log('[EnhancedHMIDashboard] Asset selected:', id, node);
    setSelectedEquipment(id);
    setSelectedNode(node || null);
  };

  const handleTagToggle = (tagId: string) => {
    if (selectedTags.includes(tagId)) {
      setSelectedTags(prev => prev.filter(id => id !== tagId));
    } else {
      if (selectedTags.length >= MAX_SELECTED_TAGS) {
        alert(`Maximum ${MAX_SELECTED_TAGS} tags allowed for trend display`);
        return;
      }
      setSelectedTags(prev => [...prev, tagId]);
    }
  };

  const handleTagClick = (tagId: string) => {
    console.log('Tag clicked:', tagId);
    // Open trend modal for the tag (read-only)
  };

  // Equipment name mapping
  const equipmentNames: Record<string, string> = {
    "eq-m101": "Mixer M-101",
    "eq-p201": "Pump P-201",
    "eq-t305": "Tank T-305",
  };

  return (
    <div className="min-h-screen flex" style={{ backgroundColor: ISA_COLORS.background }}>
      <div className="flex flex-1">
        {/* Asset Sidebar */}
        <AssetSidebar
          selectedId={selectedEquipment}
          onSelect={handleAssetSelect}
          selectedTags={selectedTags}
          onTagToggle={handleTagToggle}
        />

        <main className="flex-1 flex flex-col min-h-screen overflow-hidden">
          {/* Top Navigation Bar - ISA-101 Style */}
          <div 
            className="sticky top-0 z-10 border-b-2 shadow-2xl"
            style={{ 
              backgroundColor: ISA_COLORS.panel, 
              borderColor: ISA_COLORS.border 
            }}
          >
            <div className="px-6 py-3 flex items-center justify-between">
              {/* Left Section */}
              <div className="flex items-center gap-4">
                <div className="flex items-center gap-3">
                  <div className="relative">
                    <div 
                      className="w-3 h-3 rounded-full animate-pulse shadow-lg" 
                      style={{ backgroundColor: ISA_COLORS.statusOnline, boxShadow: `0 0 10px ${ISA_COLORS.statusOnline}` }}
                    />
                    <div 
                      className="absolute inset-0 w-3 h-3 rounded-full animate-ping opacity-30" 
                      style={{ backgroundColor: ISA_COLORS.statusOnline }}
                    />
                  </div>
                  <h1 className="text-xl font-black uppercase tracking-widest" style={{ color: ISA_COLORS.foreground }}>
                    <span style={{ color: '#FFB300' }}>INDUSTRIAL</span> HMI
                  </h1>
                </div>
                
                <div className="h-10 w-px" style={{ backgroundColor: ISA_COLORS.border }} />
                
                <div 
                  className="flex items-center gap-2 px-4 py-2 border" 
                  style={{ 
                    backgroundColor: `${ISA_COLORS.background}80`, 
                    borderColor: ISA_COLORS.border 
                  }}
                >
                  <Clock className="h-4 w-4" style={{ color: '#FFB300' }} />
                  <span className="text-sm font-mono" style={{ color: ISA_COLORS.foreground }}>
                    {currentTime.toLocaleString('en-US', { 
                      hour12: false,
                      month: 'short',
                      day: '2-digit',
                      hour: '2-digit',
                      minute: '2-digit',
                      second: '2-digit'
                    })}
                  </span>
                </div>
                
                <div className="h-10 w-px" style={{ backgroundColor: ISA_COLORS.border }} />
                
                {/* Selection Counter */}
                {selectedTags.length > 0 && (
                  <>
                    <div 
                      className="flex items-center gap-2 px-4 py-2 border" 
                      style={{ 
                        backgroundColor: `${ISA_COLORS.equipmentRunning}20`, 
                        borderColor: ISA_COLORS.equipmentRunning 
                      }}
                    >
                      <Activity className="h-4 w-4" style={{ color: ISA_COLORS.equipmentRunning }} />
                      <span className="text-sm font-mono font-semibold" style={{ color: ISA_COLORS.equipmentRunning }}>
                        SELECTED: {selectedTags.length}/{MAX_SELECTED_TAGS}
                      </span>
                    </div>
                    <div className="h-10 w-px" style={{ backgroundColor: ISA_COLORS.border }} />
                  </>
                )}
              </div>

              {/* Right Section - Navigation & User */}
              <div className="flex items-center gap-2">
                {user?.isAdmin && (
                  <>
                    <Link to="/admin">
                      <Button 
                        variant="outline" 
                        size="sm" 
                        className="gap-2 h-10 border-violet-500/40 bg-violet-950/30 text-violet-300 hover:bg-violet-500/20 hover:border-violet-400 font-semibold"
                      >
                        <Shield className="h-4 w-4" />
                        ADMIN
                      </Button>
                    </Link>
                    <div className="h-10 w-px" style={{ backgroundColor: ISA_COLORS.border }} />
                  </>
                )}
                
                {/* View Mode Buttons */}
                <Button
                  onClick={() => setActiveTab("live")}
                  variant="outline"
                  size="sm"
                  className={cn(
                    "gap-2 h-10 border-2 font-bold transition-all duration-200 uppercase tracking-wider",
                    activeTab === "live"
                      ? "text-white shadow-lg"
                      : "text-gray-400 hover:text-white"
                  )}
                  style={{
                    backgroundColor: activeTab === "live" ? ISA_COLORS.equipmentRunning : ISA_COLORS.panel,
                    borderColor: activeTab === "live" ? ISA_COLORS.equipmentRunning : ISA_COLORS.border,
                  }}
                >
                  <Activity className="h-4 w-4" />
                  LIVE
                </Button>
                
                <Button
                  onClick={() => setActiveTab("historian")}
                  variant="outline"
                  size="sm"
                  className={cn(
                    "gap-2 h-10 border-2 font-bold transition-all duration-200 uppercase tracking-wider",
                    activeTab === "historian"
                      ? "text-white shadow-lg"
                      : "text-gray-400 hover:text-white"
                  )}
                  style={{
                    backgroundColor: activeTab === "historian" ? '#0088FF' : ISA_COLORS.panel,
                    borderColor: activeTab === "historian" ? '#0088FF' : ISA_COLORS.border,
                  }}
                >
                  <Database className="h-4 w-4" />
                  HISTORIAN
                </Button>
                
                <Button
                  onClick={() => setActiveTab("p&id")}
                  variant="outline"
                  size="sm"
                  className={cn(
                    "gap-2 h-10 border-2 font-bold transition-all duration-200 uppercase tracking-wider",
                    activeTab === "p&id"
                      ? "text-white shadow-lg"
                      : "text-gray-400 hover:text-white"
                  )}
                  style={{
                    backgroundColor: activeTab === "p&id" ? '#FFB300' : ISA_COLORS.panel,
                    borderColor: activeTab === "p&id" ? '#FFB300' : ISA_COLORS.border,
                  }}
                >
                  <TrendingUp className="h-4 w-4" />
                  P&ID
                </Button>
                
                <div className="h-10 w-px mx-2" style={{ backgroundColor: ISA_COLORS.border }} />
                
                <UserHeader />
              </div>
            </div>
          </div>

          {/* Main Content Area */}
          <div className="flex-1 overflow-y-auto" style={{ backgroundColor: ISA_COLORS.background }}>
            <div className="p-6 space-y-4">
              {/* Equipment Header Card */}
              <div 
                className="border-2 shadow-2xl p-4" 
                style={{ 
                  backgroundColor: ISA_COLORS.panel, 
                  borderColor: ISA_COLORS.border 
                }}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <div 
                      className="w-4 h-4 rounded-full" 
                      style={{ backgroundColor: ISA_COLORS.equipmentRunning }}
                    />
                    <div>
                      <h2 className="text-2xl font-black uppercase tracking-wider" style={{ color: ISA_COLORS.foreground }}>
                        {equipmentNames[selectedEquipment] || "EQUIPMENT"}
                      </h2>
                      <p className="text-sm font-mono" style={{ color: '#808080' }}>
                        {selectedEquipment.toUpperCase()} • STATUS: RUNNING
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="text-right">
                      <div className="text-xs uppercase tracking-wider" style={{ color: '#808080' }}>
                        Last Update
                      </div>
                      <div className="text-sm font-mono font-bold" style={{ color: ISA_COLORS.equipmentRunning }}>
                        2 SECONDS AGO
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Content Area - Conditional Rendering */}
              <div className="space-y-4">
                {/* P&ID View */}
                {activeTab === "p&id" && (
                  <div 
                    className="border-2 overflow-hidden" 
                    style={{ 
                      backgroundColor: ISA_COLORS.panel, 
                      borderColor: ISA_COLORS.border 
                    }}
                  >
                    {/* P&ID Selector */}
                    <div 
                      className="border-b-2 p-3 flex items-center justify-between" 
                      style={{ 
                        backgroundColor: ISA_COLORS.background, 
                        borderColor: ISA_COLORS.border 
                      }}
                    >
                      <div className="flex items-center gap-3">
                        <span className="text-sm font-bold uppercase tracking-wider" style={{ color: ISA_COLORS.foreground }}>
                          SELECT P&ID:
                        </span>
                        <Button
                          onClick={() => setSelectedPID("compressor")}
                          variant="outline"
                          size="sm"
                          className={cn(
                            "font-mono font-bold uppercase",
                            selectedPID === "compressor"
                              ? "border-green-500 bg-green-500/20 text-green-400"
                              : "border-gray-600 bg-transparent text-gray-400"
                          )}
                        >
                          COMPRESSOR C-101
                        </Button>
                        <Button
                          onClick={() => setSelectedPID("pump")}
                          variant="outline"
                          size="sm"
                          className={cn(
                            "font-mono font-bold uppercase",
                            selectedPID === "pump"
                              ? "border-green-500 bg-green-500/20 text-green-400"
                              : "border-gray-600 bg-transparent text-gray-400"
                          )}
                        >
                          PUMP P-201
                        </Button>
                      </div>
                      <div className="text-xs uppercase tracking-wider" style={{ color: '#FFB300' }}>
                        ⚠️ READ-ONLY VIEW
                      </div>
                    </div>
                    
                    {/* P&ID Display */}
                    <div className="p-4">
                      <ProcessGraphic
                        config={selectedPID === "compressor" ? sampleCompressorConfig : samplePumpConfig}
                        realTimeData={realTimeData}
                        onTagClick={handleTagClick}
                      />
                    </div>
                  </div>
                )}

                {/* Live Data View */}
                {activeTab === "live" && (
                  <>
                    {selectedNode && selectedNode.type === "component" && selectedNode.tags ? (
                      <div 
                        className="border-2 overflow-hidden" 
                        style={{ 
                          backgroundColor: ISA_COLORS.panel, 
                          borderColor: ISA_COLORS.border 
                        }}
                      >
                        <TagValuePanel
                          selectedNodeId={selectedNode.id}
                          tags={selectedNode.tags}
                          componentName={selectedNode.name}
                        />
                      </div>
                    ) : (
                      <div 
                        className="border-2 overflow-hidden" 
                        style={{ 
                          backgroundColor: ISA_COLORS.panel, 
                          borderColor: ISA_COLORS.border 
                        }}
                      >
                        <LiveDataPanel 
                          equipmentId={selectedEquipment}
                          equipmentName={equipmentNames[selectedEquipment] || "Equipment"}
                          selectedTags={selectedTags}
                        />
                      </div>
                    )}
                  </>
                )}

                {/* Historian View */}
                {activeTab === "historian" && (
                  <div 
                    className="border-2 overflow-hidden" 
                    style={{ 
                      backgroundColor: ISA_COLORS.panel, 
                      borderColor: ISA_COLORS.border 
                    }}
                  >
                    <HistoricalDataPanel
                      equipmentId={selectedEquipment}
                      equipmentName={equipmentNames[selectedEquipment] || "Equipment"}
                    />
                  </div>
                )}
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
};
