import { useState } from "react";
import { Link } from "react-router-dom";
import { History, Shield, Activity, Clock, Gauge, Database, TrendingUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { AssetSidebar } from "./AssetSidebar";
import { EquipmentHeader } from "./EquipmentHeader";
import { UserHeader } from "./UserHeader";
import { LiveDataPanel } from "./LiveDataPanel";
import { HistoricalDataPanel } from "./HistoricalDataPanel";
import { TagValuePanel } from "./TagValuePanel";
import { useAuth } from "@/context/auth-context";
import { cn } from "@/lib/utils";
import { MAX_SELECTED_TAGS } from "@/config/isa101-trend-config";

interface TreeNode {
  id: string;
  name: string;
  type: "plant" | "area" | "equipment" | "sub_equipment" | "component" | "tag";
  hasAlarm?: boolean;
  tag_count?: number;
  tags?: any[];
  children?: TreeNode[];
}

export const HMIDashboard = () => {
  const [selectedEquipment, setSelectedEquipment] = useState("eq-m101");
  const [selectedNode, setSelectedNode] = useState<TreeNode | null>(null);
  const [activeTab, setActiveTab] = useState("live");
  const [selectedTags, setSelectedTags] = useState<string[]>([]); // Track selected tags
  const { user } = useAuth();

  // Equipment name mapping
  const equipmentNames: Record<string, string> = {
    "eq-m101": "Mixer M-101",
    "eq-p201": "Pump P-201",
    "eq-t305": "Tank T-305",
  };

  const handleAssetSelect = (id: string, node?: TreeNode) => {
    console.log('[HMIDashboard] Asset selected:', id, node);
    setSelectedEquipment(id);
    setSelectedNode(node || null);
  };

  // Toggle tag selection (configurable max tags)
  const handleTagToggle = (tagId: string) => {
    if (selectedTags.includes(tagId)) {
      // Deselect
      setSelectedTags(prev => prev.filter(id => id !== tagId));
    } else {
      // Select (max limit)
      if (selectedTags.length >= MAX_SELECTED_TAGS) {
        alert(`Maximum ${MAX_SELECTED_TAGS} tags allowed. Please deselect a tag first.`);
        return;
      }
      setSelectedTags(prev => [...prev, tagId]);
    }
  };

  return (
    <div className="min-h-screen bg-background flex">
      <div className="flex flex-1">
        <AssetSidebar
          selectedId={selectedEquipment}
          onSelect={handleAssetSelect}
          selectedTags={selectedTags}
          onTagToggle={handleTagToggle}
        />

        <main className="flex-1 flex flex-col min-h-screen overflow-hidden">
          {/* Top Navigation Bar - Fixed - Industrial Design */}
          <div className="sticky top-0 z-10 bg-gradient-to-r from-slate-950 via-slate-900 to-slate-950 border-b-2 border-amber-500/30 shadow-2xl">
            <div className="px-6 py-2.5 flex items-center justify-between">
              {/* Left Section */}
              <div className="flex items-center gap-4">
                <div className="flex items-center gap-3">
                  <div className="relative">
                    <div className="w-2.5 h-2.5 rounded-full bg-green-500 animate-pulse shadow-lg shadow-green-500/50" />
                    <div className="absolute inset-0 w-2.5 h-2.5 rounded-full bg-green-500/30 animate-ping" />
                  </div>
                  <h1 className="text-lg font-black text-white uppercase tracking-widest">
                    <span className="text-amber-400">SCADA</span> CONTROL
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
                <div className="h-8 w-px bg-amber-500/40" />
                {/* Selection Counter */}
                {selectedTags.length > 0 && (
                  <>
                    <div className="flex items-center gap-2 px-3 py-1.5 bg-primary/20 border border-primary/50 rounded-md">
                      <Activity className="h-3.5 w-3.5 text-primary" />
                      <span className="text-xs font-mono text-primary font-semibold">
                        Selected: {selectedTags.length}/{MAX_SELECTED_TAGS}
                      </span>
                    </div>
                    <div className="h-8 w-px bg-amber-500/40" />
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
                        className="gap-2 h-9 border-violet-500/40 bg-violet-950/30 text-violet-300 hover:bg-violet-500/20 hover:border-violet-400 font-semibold"
                      >
                        <Shield className="h-4 w-4" />
                        Admin
                      </Button>
                    </Link>
                    <div className="h-8 w-px bg-slate-700/50" />
                  </>
                )}
                
                {/* Industrial Prototype Link */}
                <Link to="/industrial-prototype">
                  <Button 
                    variant="outline" 
                    size="sm" 
                    className="gap-2 h-9 border-cyan-500/40 bg-cyan-950/30 text-cyan-300 hover:bg-cyan-500/20 hover:border-cyan-400 font-semibold"
                  >
                    <Gauge className="h-4 w-4" />
                    ISA-101
                  </Button>
                </Link>
                
                {/* Enhanced HMI with P&ID Link */}
                <Link to="/enhanced-hmi">
                  <Button 
                    variant="outline" 
                    size="sm" 
                    className="gap-2 h-9 border-green-500/40 bg-green-950/30 text-green-300 hover:bg-green-500/20 hover:border-green-400 font-semibold"
                  >
                    <TrendingUp className="h-4 w-4" />
                    P&ID HMI
                  </Button>
                </Link>
                <div className="h-8 w-px bg-slate-700/50" />
                
                {/* Live Data & Historian Buttons */}
                <Button
                  onClick={() => setActiveTab("live")}
                  variant="outline"
                  size="sm"
                  className={cn(
                    "gap-2 h-9 border font-bold transition-all duration-200",
                    activeTab === "live"
                      ? "bg-emerald-600 border-emerald-500 text-white shadow-lg shadow-emerald-500/30 hover:bg-emerald-500"
                      : "border-slate-700/50 bg-slate-800/50 text-slate-300 hover:bg-slate-700/70 hover:border-slate-600"
                  )}
                >
                  <Activity className="h-4 w-4" />
                  LIVE DATA
                </Button>
                
                <Button
                  onClick={() => setActiveTab("historian")}
                  variant="outline"
                  size="sm"
                  className={cn(
                    "gap-2 h-9 border font-bold transition-all duration-200",
                    activeTab === "historian"
                      ? "bg-blue-600 border-blue-500 text-white shadow-lg shadow-blue-500/30 hover:bg-blue-500"
                      : "border-slate-700/50 bg-slate-800/50 text-slate-300 hover:bg-slate-700/70 hover:border-slate-600"
                  )}
                >
                  <Database className="h-4 w-4" />
                  HISTORIAN
                </Button>
                
                <div className="h-8 w-px bg-slate-700/50 mx-1" />
                
                <UserHeader />
              </div>
            </div>
          </div>

          {/* Main Content Area */}
          <div className="flex-1 overflow-y-auto bg-slate-950">
            <div className="p-6 space-y-4">
              {/* Equipment Header Card - Industrial Style */}
              <div className="bg-gradient-to-br from-slate-900 via-slate-900 to-slate-800 border-2 border-amber-600/30 rounded-lg shadow-2xl">
                <EquipmentHeader
                  name={equipmentNames[selectedEquipment] || "Equipment"}
                  tagId={selectedEquipment.toUpperCase()}
                  status="running"
                  hasAlarm={selectedEquipment === "eq-m101"}
                  lastUpdate="2 seconds ago"
                />
              </div>

              {/* Data Content - Show Tag Value Panel if component selected, otherwise show live/historian */}
              <div className="space-y-4">
                {selectedNode && selectedNode.type === "component" && selectedNode.tags ? (
                  <div className="bg-gradient-to-br from-slate-900 via-slate-900 to-slate-800 border-2 border-amber-600/30 rounded-lg shadow-2xl overflow-hidden">
                    <TagValuePanel
                      selectedNodeId={selectedNode.id}
                      tags={selectedNode.tags}
                      componentName={selectedNode.name}
                    />
                  </div>
                ) : (
                  <>
                    {activeTab === "live" && (
                      <LiveDataPanel
                        equipmentId={selectedEquipment}
                        equipmentName={equipmentNames[selectedEquipment]}
                      />
                    )}
                    
                    {activeTab === "historian" && (
                      <HistoricalDataPanel
                        equipmentId={selectedEquipment}
                        equipmentName={equipmentNames[selectedEquipment]}
                      />
                    )}
                  </>
                )}
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
};
