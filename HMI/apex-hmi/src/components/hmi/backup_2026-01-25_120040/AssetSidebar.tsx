import { useState, useEffect } from "react";
import { 
  ChevronRight, 
  ChevronDown, 
  Factory, 
  Box, 
  Cog, 
  Activity,
  AlertTriangle,
  Layers,
  Cpu,
  Component as ComponentIcon
} from "lucide-react";
import { cn } from "@/lib/utils";
import { AlarmPanel } from "./AlarmPanel";

interface TreeNode {
  id: string;
  name: string;
  type: "plant" | "area" | "equipment" | "sub_equipment" | "component" | "tag";
  hasAlarm?: boolean;
  tag_count?: number;
  tags?: any[];
  children?: TreeNode[];
}

interface AssetSidebarProps {
  selectedId: string;
  onSelect: (id: string, node?: TreeNode) => void;
  selectedTags?: string[]; // NEW: Array of selected tag IDs
  onTagToggle?: (tagId: string) => void; // NEW: Toggle tag selection
}

const TAG_COLORS = [
  '#ef4444', // red
  '#3b82f6', // blue
  '#10b981', // green
  '#f59e0b', // orange
  '#8b5cf6', // purple
];

const getIcon = (type: TreeNode["type"]) => {
  switch (type) {
    case "plant": return Factory;
    case "area": return Layers;
    case "equipment": return Cog;
    case "sub_equipment": return Cpu;
    case "component": return ComponentIcon;
    case "tag": return Activity;
  }
};

interface TreeItemProps {
  node: TreeNode;
  level: number;
  selectedId: string;
  onSelect: (id: string, node?: TreeNode) => void;
  expandedIds: Set<string>;
  onToggle: (id: string) => void;
  selectedTags: string[]; // NEW
  onTagToggle: (tagId: string) => void; // NEW
}

const TreeItem = ({ node, level, selectedId, onSelect, expandedIds, onToggle, selectedTags, onTagToggle }: TreeItemProps) => {
  const Icon = getIcon(node.type);
  const hasChildren = node.children && node.children.length > 0;
  const hasTags = node.tags && node.tags.length > 0;
  const isExpanded = expandedIds.has(node.id);
  const isSelected = selectedId === node.id;

  return (
    <div>
      <div
        className={cn(
          "tree-node flex items-center gap-2 group",
          isSelected && "selected"
        )}
        style={{ paddingLeft: `${level * 12 + 8}px` }}
        onClick={() => {
          if (node.type === "equipment" || node.type === "sub_equipment" || node.type === "component") {
            onSelect(node.id, node);
          }
          if (hasChildren || hasTags) {
            onToggle(node.id);
          }
        }}
      >
        {(hasChildren || hasTags) ? (
          <button 
            className="w-4 h-4 flex items-center justify-center text-muted-foreground hover:text-foreground"
            onClick={(e) => {
              e.stopPropagation();
              onToggle(node.id);
            }}
          >
            {isExpanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
          </button>
        ) : (
          <span className="w-4" />
        )}
        
        <Icon className={cn(
          "w-4 h-4",
          isSelected ? "text-primary" : "text-muted-foreground group-hover:text-foreground"
        )} />
        
        <span className={cn(
          "text-sm flex-1 truncate",
          isSelected ? "text-primary font-medium" : "text-sidebar-foreground"
        )}>
          {node.name}
        </span>

        {/* Tag count badge */}
        {node.tag_count && node.tag_count > 0 && (
          <span className="text-[10px] bg-muted text-muted-foreground px-1.5 py-0.5 rounded">
            {node.tag_count}
          </span>
        )}

        {node.hasAlarm && (
          <span className="relative flex h-2 w-2 mr-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-status-alarm opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-status-alarm"></span>
          </span>
        )}
      </div>

      {isExpanded && (
        <div>
          {hasChildren && node.children!.map((child) => (
            <TreeItem
              key={child.id}
              node={child}
              level={level + 1}
              selectedId={selectedId}
              onSelect={onSelect}
              expandedIds={expandedIds}
              onToggle={onToggle}
              selectedTags={selectedTags}
              onTagToggle={onTagToggle}
            />
          ))}
          
          {hasTags && node.tags!.map((tag) => {
            const tagId = tag.tag_id;
            const isTagSelected = selectedTags.includes(tagId);
            const tagIndex = selectedTags.indexOf(tagId);
            const tagColor = tagIndex >= 0 ? TAG_COLORS[tagIndex % TAG_COLORS.length] : undefined;
            
            return (
            <div
              key={tagId}
              className={cn(
                "tree-node flex items-center gap-2 group cursor-pointer transition-all",
                isTagSelected && "selected"
              )}
              style={{ 
                paddingLeft: `${(level + 1) * 12 + 8}px`,
                backgroundColor: isTagSelected ? `${tagColor}20` : undefined,
                borderLeft: isTagSelected ? `3px solid ${tagColor}` : undefined
              }}
              onClick={(e) => {
                e.stopPropagation();
                onTagToggle(tagId);
              }}
            >
              <span className="w-4">
                {isTagSelected && (
                  <div className="w-3 h-3 rounded-sm flex items-center justify-center" style={{ backgroundColor: tagColor }}>
                    <svg className="w-2 h-2 text-white" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                    </svg>
                  </div>
                )}
              </span>
              <Activity className={cn(
                "w-3 h-3",
                isTagSelected ? "text-foreground" : "text-muted-foreground group-hover:text-foreground"
              )} style={{ color: isTagSelected ? tagColor : undefined }} />
              <span className={cn(
                "text-xs flex-1 truncate font-mono",
                isTagSelected ? "font-semibold" : "text-sidebar-foreground"
              )} style={{ color: isTagSelected ? tagColor : undefined }}>
                {tag.tag_name || tagId}
              </span>
              {tag.trip_category && (
                <span className="relative flex h-2 w-2 mr-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-status-alarm opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-status-alarm"></span>
                </span>
              )}
            </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default function AssetSidebar({ selectedId: externalSelectedId, onSelect: externalOnSelect, selectedTags = [], onTagToggle }: AssetSidebarProps) {
  const [assetTree, setAssetTree] = useState<TreeNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [selectedId, setSelectedId] = useState<string>("");

  useEffect(() => {
    fetchAssetHierarchy();
  }, []);

  // Sync with external selectedId if provided
  useEffect(() => {
    if (externalSelectedId) {
      setSelectedId(externalSelectedId);
    }
  }, [externalSelectedId]);

  const handleTagToggle = (tagId: string) => {
    if (onTagToggle) {
      onTagToggle(tagId);
    }
  };

  const onSelect = (id: string, node?: TreeNode) => {
    console.log('[AssetSidebar] Selected asset:', id, node);
    setSelectedId(id);
    if (externalOnSelect) {
      externalOnSelect(id, node);
    }
  };

  const fetchAssetHierarchy = async () => {
    console.log('[AssetSidebar] 🔍 Starting to fetch asset hierarchy...');
    try {
      setLoading(true);
      const token = localStorage.getItem('auth_token'); // Changed from 'token' to 'auth_token'
      console.log('[AssetSidebar] 🔑 Token from localStorage:', token ? `${token.substring(0, 20)}...` : 'NOT FOUND');
      
      console.log('[AssetSidebar] 📡 Fetching from: /api/assets/hierarchy');
      const response = await fetch('/api/assets/hierarchy', {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      console.log('[AssetSidebar] 📥 Response status:', response.status, response.statusText);
      
      if (!response.ok) {
        const errorText = await response.text();
        console.error('[AssetSidebar] ❌ API Error:', errorText);
        throw new Error(`Failed to fetch asset hierarchy: ${response.status} - ${errorText}`);
      }

      const data = await response.json();
      console.log('[AssetSidebar] ✅ Data received:', JSON.stringify(data, null, 2));
      console.log('[AssetSidebar] 📊 Hierarchy length:', data.hierarchy?.length || 0);
      
      setAssetTree(data.hierarchy || []);
      
      // Auto-expand first plant and its first area
      if (data.hierarchy && data.hierarchy.length > 0) {
        const firstPlant = data.hierarchy[0];
        console.log('[AssetSidebar] 🌳 Auto-expanding first plant:', firstPlant.name);
        const expanded = new Set([firstPlant.id]);
        if (firstPlant.children && firstPlant.children.length > 0) {
          expanded.add(firstPlant.children[0].id);
          console.log('[AssetSidebar] 🌳 Auto-expanding first area:', firstPlant.children[0].name);
        }
        setExpandedIds(expanded);
      }
      console.log('[AssetSidebar] ✅ Asset hierarchy loaded successfully!');
    } catch (err) {
      console.error('[AssetSidebar] ❌ Error fetching asset hierarchy:', err);
      console.error('[AssetSidebar] ❌ Error details:', {
        message: err instanceof Error ? err.message : 'Unknown error',
        stack: err instanceof Error ? err.stack : undefined
      });
    } finally {
      setLoading(false);
      console.log('[AssetSidebar] 🏁 Fetch complete, loading state set to false');
    }
  };

  const handleToggle = (id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  return (
    <aside className="w-64 h-screen bg-sidebar border-r border-sidebar-border flex flex-col">
      {/* Header - Fixed */}
      <div className="p-4 border-b border-sidebar-border flex-shrink-0">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded bg-primary/20 flex items-center justify-center">
            <Factory className="w-4 h-4 text-primary" />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-foreground">Asset Browser</h2>
            <p className="text-xs text-muted-foreground">Navigate hierarchy</p>
          </div>
        </div>
      </div>

      {/* Asset Tree - Scrollable - 60% */}
      <div className="overflow-y-auto py-2 min-h-0" style={{ flex: '0 1 60%' }}>
        {loading ? (
          <div className="flex items-center justify-center py-8">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary"></div>
          </div>
        ) : assetTree.length === 0 ? (
          <div className="px-4 py-8 text-center">
            <p className="text-xs text-muted-foreground">No assets found</p>
          </div>
        ) : (
          assetTree.map((node) => (
            <TreeItem
              key={node.id}
              node={node}
              level={0}
              selectedId={selectedId}
              onSelect={onSelect}
              expandedIds={expandedIds}
              onToggle={handleToggle}
              selectedTags={selectedTags}
              onTagToggle={handleTagToggle}
            />
          ))
        )}
      </div>

      {/* Alarm Panel - 40% */}
      <div className="border-t border-sidebar-border" style={{ flex: '0 1 40%', minHeight: 0 }}>
        <AlarmPanel />
      </div>
    </aside>
  );
}

export { AssetSidebar };
