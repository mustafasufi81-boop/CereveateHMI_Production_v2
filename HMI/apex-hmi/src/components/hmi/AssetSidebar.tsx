import { useState, useEffect, useRef, useCallback } from "react";
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
  TrendingUp,
  Component as ComponentIcon
} from "lucide-react";
import { cn } from "@/lib/utils";
import { AlarmPanel } from "./AlarmPanel";

// API Configuration - use relative URL so requests go through nginx proxy

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
  selectedTags?: string[]; // Array of selected tag IDs
  onTagToggle?: (tagId: string, tagData?: any) => void; // Toggle tag selection with optional tag data
  liveTagValues?: Record<string, any>; // Live OPC values keyed by tag_id
  onTagOpenNewWindow?: (tagId: string, tagData?: any) => void; // Open tag in a brand-new trend chart window
  onContextMenuRequest?: (state: any) => void; // Context menu callback (e.g. open predictive trend)
}

// Match the colors used in IndustrialHMIPrototype for consistency
const TAG_COLORS = [
  '#00FF00', // Bright Green
  '#00FFFF', // Cyan
  '#FF00FF', // Magenta
  '#FFFF00', // Yellow
  '#FF8800', // Orange
];

type ViewMode = 'topic' | 'equipment' | 'sub_equipment' | 'component';

const VIEW_MODES: { value: ViewMode; label: string; short: string }[] = [
  { value: 'topic',         label: 'Topic / PLC',    short: 'Topic' },
  { value: 'equipment',     label: 'Equipment',      short: 'Equip' },
  { value: 'sub_equipment', label: 'Sub-Equipment',  short: 'Sub' },
  { value: 'component',     label: 'Component',      short: 'Comp' },
];

/**
 * Walk the entire raw hierarchy and collect every tag, annotating each with
 * its ancestry (equipment name, sub-equipment name, component name) so all
 * four view-mode groupings can work from a single flat list.
 */
function collectAllTagsAnnotated(nodes: TreeNode[]): any[] {
  const result: any[] = [];
  function walk(
    nodes: TreeNode[],
    ctx: { equipment?: string; sub_equipment?: string; component?: string }
  ) {
    nodes.forEach(n => {
      const c = { ...ctx };
      if (n.type === 'equipment')     c.equipment     = n.name;
      if (n.type === 'sub_equipment') c.sub_equipment = n.name;
      if (n.type === 'component')     c.component     = n.name;
      if (n.tags) {
        n.tags.forEach(tag =>
          result.push({
            ...tag,
            _equipment:     tag.equipment     || c.equipment     || 'Unassigned',
            _sub_equipment: tag.sub_equipment || c.sub_equipment || 'Unassigned',
            _component:     tag.component     || c.component     || 'Unassigned',
          })
        );
      }
      if (n.children) walk(n.children, c);
    });
  }
  walk(nodes, {});
  return result;
}

/** Simple group-by helper */
function groupBy<T>(arr: T[], key: (t: T) => string): Map<string, T[]> {
  const m = new Map<string, T[]>();
  arr.forEach(item => {
    const k = key(item);
    if (!m.has(k)) m.set(k, []);
    m.get(k)!.push(item);
  });
  return m;
}

/**
 * Re-shape the full hierarchy into one of four view modes.
 * ALL modes start with Topic (server_progid) at the top level.
 *
 *  topic       → Topic → [tags flat]
 *  equipment   → Topic → Equipment → [all tags flat]
 *  sub_equip   → Topic → Equipment → Sub-Equipment → [all tags flat]
 *  component   → Topic → Equipment → Sub-Equipment → Component → [tags]
 */
function transformTree(tree: TreeNode[], mode: ViewMode): TreeNode[] {
  const all = collectAllTagsAnnotated(tree);

  if (mode === 'topic') {
    // Topic → tags (flat, no further grouping)
    const byTopic = groupBy(all, t => t.server_progid || 'Unknown');
    return Array.from(byTopic.entries()).map(([topic, tags]) => ({
      id: `t_${topic}`,
      name: topic,
      type: 'plant' as const,
      tag_count: tags.length,
      tags,
      children: [],
    }));
  }

  if (mode === 'equipment') {
    // Topic → Equipment → tags (all sub/component tags bubbled up)
    const byTopic = groupBy(all, t => t.server_progid || 'Unknown');
    return Array.from(byTopic.entries()).map(([topic, topicTags]) => {
      const byEquip = groupBy(topicTags, t => t._equipment);
      return {
        id: `t_${topic}`,
        name: topic,
        type: 'plant' as const,
        tag_count: topicTags.length,
        tags: [],
        children: Array.from(byEquip.entries()).map(([equip, tags]) => ({
          id: `t_${topic}_e_${equip}`,
          name: equip,
          type: 'equipment' as const,
          tag_count: tags.length,
          tags,
          children: [],
        })) as TreeNode[],
      } as TreeNode;
    });
  }

  if (mode === 'sub_equipment') {
    // Topic → Equipment → Sub-Equipment → tags (component tags bubbled up)
    const byTopic = groupBy(all, t => t.server_progid || 'Unknown');
    return Array.from(byTopic.entries()).map(([topic, topicTags]) => {
      const byEquip = groupBy(topicTags, t => t._equipment);
      return {
        id: `t_${topic}`,
        name: topic,
        type: 'plant' as const,
        tag_count: topicTags.length,
        tags: [],
        children: Array.from(byEquip.entries()).map(([equip, equipTags]) => {
          const bySub = groupBy(equipTags, t => t._sub_equipment);
          return {
            id: `t_${topic}_e_${equip}`,
            name: equip,
            type: 'equipment' as const,
            tag_count: equipTags.length,
            tags: [],
            children: Array.from(bySub.entries()).map(([sub, tags]) => ({
              id: `t_${topic}_e_${equip}_s_${sub}`,
              name: sub,
              type: 'sub_equipment' as const,
              tag_count: tags.length,
              tags,
              children: [],
            })) as TreeNode[],
          } as TreeNode;
        }) as TreeNode[],
      } as TreeNode;
    });
  }

  // component: Topic → Equipment → Sub-Equipment → Component → tags (full depth)
  const byTopic = groupBy(all, t => t.server_progid || 'Unknown');
  return Array.from(byTopic.entries()).map(([topic, topicTags]) => {
    const byEquip = groupBy(topicTags, t => t._equipment);
    return {
      id: `t_${topic}`,
      name: topic,
      type: 'plant' as const,
      tag_count: topicTags.length,
      tags: [],
      children: Array.from(byEquip.entries()).map(([equip, equipTags]) => {
        const bySub = groupBy(equipTags, t => t._sub_equipment);
        return {
          id: `t_${topic}_e_${equip}`,
          name: equip,
          type: 'equipment' as const,
          tag_count: equipTags.length,
          tags: [],
          children: Array.from(bySub.entries()).map(([sub, subTags]) => {
            const byComp = groupBy(subTags, t => t._component);
            return {
              id: `t_${topic}_e_${equip}_s_${sub}`,
              name: sub,
              type: 'sub_equipment' as const,
              tag_count: subTags.length,
              tags: [],
              children: Array.from(byComp.entries()).map(([comp, tags]) => ({
                id: `t_${topic}_e_${equip}_s_${sub}_c_${comp}`,
                name: comp,
                type: 'component' as const,
                tag_count: tags.length,
                tags,
                children: [],
              })) as TreeNode[],
            } as TreeNode;
          }) as TreeNode[],
        } as TreeNode;
      }) as TreeNode[],
    } as TreeNode;
  });
}

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

interface ContextMenuState {
  x: number;
  y: number;
  tagId: string;
  tagData: any;
}

interface TreeItemProps {
  node: TreeNode;
  level: number;
  selectedId: string;
  onSelect: (id: string, node?: TreeNode) => void;
  expandedIds: Set<string>;
  onToggle: (id: string) => void;
  selectedTags: string[];
  onTagToggle?: (tagId: string, tagData?: any) => void;
  liveTagValues?: Record<string, any>;
  onTagOpenNewWindow?: (tagId: string, tagData?: any) => void;
  onContextMenuRequest?: (state: ContextMenuState) => void;
}

const TreeItem = ({ node, level, selectedId, onSelect, expandedIds, onToggle, selectedTags, onTagToggle, liveTagValues, onTagOpenNewWindow, onContextMenuRequest }: TreeItemProps) => {
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
        
        <span
          title={node.name}
          className={cn(
            "text-sm flex-1 truncate",
            isSelected ? "text-primary font-medium" : "text-sidebar-foreground"
          )}
        >
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
              liveTagValues={liveTagValues}
              onTagOpenNewWindow={onTagOpenNewWindow}
              onContextMenuRequest={onContextMenuRequest}
            />
          ))}
          
          {hasTags && node.tags!.map((tag) => {
            const tagId = tag.tag_id;
            const isTagSelected = selectedTags.includes(tagId);
            const tagIndex = selectedTags.indexOf(tagId);
            const tagColor = tagIndex >= 0 ? TAG_COLORS[tagIndex % TAG_COLORS.length] : undefined;
            
            // Live OPC value for this tag
            const liveEntry = liveTagValues?.[tagId];
            const liveVal = liveEntry?.value;
            const liveQuality = liveEntry?.quality || '';
            const isGoodQuality = !liveQuality || liveQuality === 'G' || liveQuality?.toLowerCase?.() === 'good';
            const displayValue = liveVal !== undefined && liveVal !== null
              ? (typeof liveVal === 'number' ? liveVal.toFixed(2) : String(liveVal))
              : null;

            return (
            <div
              key={tagId}
              draggable
              onDragStart={(e) => {
                e.dataTransfer.effectAllowed = 'copy';
                e.dataTransfer.setData('application/hmi-tag', JSON.stringify({ tagId, tagData: tag }));
              }}
              className={cn(
                "tree-node flex items-center gap-2 group cursor-grab active:cursor-grabbing transition-all",
                isTagSelected && "selected"
              )}
              style={{ 
                paddingLeft: `${(level + 1) * 12 + 8}px`,
                backgroundColor: isTagSelected ? `${tagColor}20` : undefined,
                borderLeft: isTagSelected ? `3px solid ${tagColor}` : undefined
              }}
              onClick={(e) => {
                e.stopPropagation();
                if (onTagToggle) {
                  onTagToggle(tagId, tag);
                }
              }}
              onContextMenu={(e) => {
                e.preventDefault();
                e.stopPropagation();
                if (onContextMenuRequest) {
                  onContextMenuRequest({ x: e.clientX, y: e.clientY, tagId, tagData: tag });
                }
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
              <span
                title={tag.tag_name || tagId}
                className={cn(
                  "text-xs flex-1 truncate font-mono",
                  isTagSelected ? "font-semibold" : "text-sidebar-foreground"
                )}
                style={{ color: isTagSelected ? tagColor : undefined }}
              >
                {tag.tag_name || tagId}
              </span>
              {/* Live OPC value badge */}
              {displayValue !== null && (
                <span
                  title={`Quality: ${liveQuality || 'Good'}`}
                  className="text-[9px] font-mono px-1 py-0.5 rounded shrink-0"
                  style={{
                    backgroundColor: isGoodQuality ? 'rgba(0,255,100,0.12)' : 'rgba(255,80,80,0.15)',
                    color: isGoodQuality ? '#4ade80' : '#f87171',
                    border: `1px solid ${isGoodQuality ? 'rgba(74,222,128,0.3)' : 'rgba(248,113,113,0.3)'}`,
                    maxWidth: '64px',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap'
                  }}
                >
                  {displayValue}
                </span>
              )}
              {displayValue === null && (
                <span className="text-[9px] font-mono px-1 py-0.5 rounded shrink-0"
                  style={{ backgroundColor: 'rgba(100,100,100,0.15)', color: '#6b7280', border: '1px solid rgba(100,100,100,0.2)' }}
                >—</span>
              )}
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

export default function AssetSidebar({ selectedId: externalSelectedId, onSelect: externalOnSelect, selectedTags = [], onTagToggle, liveTagValues = {}, onTagOpenNewWindow, onContextMenuRequest: onParentContextMenuRequest }: AssetSidebarProps) {
  const [assetTree, setAssetTree] = useState<TreeNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [selectedId, setSelectedId] = useState<string>("");
  const [searchTerm, setSearchTerm] = useState<string>("");
  const [viewMode, setViewMode] = useState<ViewMode>('topic');
  const [sidebarWidth, setSidebarWidth] = useState<number>(256);
  const [isDragging, setIsDragging] = useState(false);
  const dragStartX = useRef<number>(0);
  const dragStartWidth = useRef<number>(256);
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);
  const contextMenuRef = useRef<HTMLDivElement>(null);

  const handleDragStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    dragStartX.current = e.clientX;
    dragStartWidth.current = sidebarWidth;
    setIsDragging(true);
  }, [sidebarWidth]);

  useEffect(() => {
    if (!isDragging) return;
    const onMouseMove = (e: MouseEvent) => {
      const delta = e.clientX - dragStartX.current;
      const newWidth = Math.min(520, Math.max(160, dragStartWidth.current + delta));
      setSidebarWidth(newWidth);
    };
    const onMouseUp = () => setIsDragging(false);
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
    return () => {
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    };
  }, [isDragging]);

  useEffect(() => {
    fetchAssetHierarchy();
  }, []);

  // Auto-expand top-level and second-level nodes whenever view mode changes
  useEffect(() => {
    if (assetTree.length === 0) return;
    const transformed = transformTree(assetTree, viewMode);
    const expanded = new Set<string>();
    transformed.forEach((topNode) => {
      expanded.add(topNode.id);
      (topNode.children ?? []).forEach((child) => {
        expanded.add(child.id);
        (child.children ?? []).forEach((grandchild) => {
          expanded.add(grandchild.id);
        });
      });
    });
    setExpandedIds(expanded);
  }, [viewMode, assetTree]);

  // Sync with external selectedId if provided
  useEffect(() => {
    if (externalSelectedId) {
      setSelectedId(externalSelectedId);
    }
  }, [externalSelectedId]);

  // Close context menu on outside click or Escape
  useEffect(() => {
    if (!contextMenu) return;
    const handleClick = () => setContextMenu(null);
    const handleKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setContextMenu(null); };
    window.addEventListener('click', handleClick);
    window.addEventListener('keydown', handleKey);
    return () => {
      window.removeEventListener('click', handleClick);
      window.removeEventListener('keydown', handleKey);
    };
  }, [contextMenu]);

  const handleTagToggle = (tagId: string, tagData?: any) => {
    if (onTagToggle) {
      onTagToggle(tagId, tagData);
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
      
      console.log('[AssetSidebar] 📡 Fetching from:', '/api/assets/hierarchy');
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
      
      // Expansion is handled by the viewMode useEffect that fires when assetTree changes
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

  const handleUnselectAll = () => {
    if (selectedTags.length === 0) return;
    // Unselect all tags by toggling each one
    selectedTags.forEach(tagId => {
      if (onTagToggle) {
        onTagToggle(tagId);
      }
    });
  };

  // Filter tree based on search term (pure function - no state updates)
  const filterTree = (nodes: TreeNode[], term: string): { filtered: TreeNode[], matchingIds: Set<string> } => {
    if (!term) return { filtered: nodes, matchingIds: new Set() };
    
    const lowerTerm = term.toLowerCase();
    const matchingIds = new Set<string>();
    
    const filtered = nodes.map(node => {
      const nameMatch = node.name.toLowerCase().includes(lowerTerm);
      const childResult = node.children ? filterTree(node.children, term) : { filtered: [], matchingIds: new Set() };
      const filteredChildren = childResult.filtered;
      
      // Merge child matching IDs
      childResult.matchingIds.forEach(id => matchingIds.add(id));
      
      const filteredTags = node.tags?.filter(tag => 
        tag.tag_id?.toLowerCase().includes(lowerTerm) ||
        tag.tag_name?.toLowerCase().includes(lowerTerm) ||
        tag.description?.toLowerCase().includes(lowerTerm)
      ) || [];

      if (nameMatch || filteredChildren.length > 0 || filteredTags.length > 0) {
        // Mark this node as matching if it has children or tags that match
        if (filteredChildren.length > 0 || filteredTags.length > 0) {
          matchingIds.add(node.id);
        }
        return {
          ...node,
          children: filteredChildren.length > 0 ? filteredChildren : node.children,
          tags: filteredTags.length > 0 ? filteredTags : node.tags
        };
      }
      return null;
    }).filter((node): node is TreeNode => node !== null);
    
    return { filtered, matchingIds };
  };

  const { filtered: filteredTree, matchingIds } = filterTree(transformTree(assetTree, viewMode), searchTerm);

  // Auto-expand matching nodes when search changes
  useEffect(() => {
    if (searchTerm && matchingIds.size > 0) {
      setExpandedIds(prev => {
        const newSet = new Set(prev);
        matchingIds.forEach(id => newSet.add(id));
        return newSet;
      });
    }
  }, [searchTerm, matchingIds.size]);

  return (
    <aside
      className="bg-sidebar border-r border-sidebar-border flex flex-col relative flex-shrink-0"
      style={{ width: sidebarWidth, height: 'calc(100vh - 60px)', maxHeight: 'calc(100vh - 60px)' }}
    >
      {/* Drag handle */}
      <div
        onMouseDown={handleDragStart}
        className="absolute top-0 right-0 w-1.5 h-full z-10 group flex items-center justify-center"
        style={{ cursor: 'col-resize' }}
        title="Drag to resize"
      >
        <div className={`w-0.5 h-full transition-colors ${
          isDragging ? 'bg-primary' : 'bg-transparent group-hover:bg-primary/50'
        }`} />
      </div>
      {/* Header - Fixed */}
      <div className="p-4 border-b border-sidebar-border flex-shrink-0">
        <div className="flex items-center gap-2 mb-3">
          <div className="w-8 h-8 rounded bg-primary/20 flex items-center justify-center">
            <Factory className="w-4 h-4 text-primary" />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-foreground">Asset Browser</h2>
            <p className="text-xs text-muted-foreground">Navigate hierarchy</p>
          </div>
        </div>
        
        {/* Search Input */}
        <input
          type="text"
          placeholder="Search tags..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="w-full px-3 py-2 text-xs border border-input bg-background rounded-md focus:outline-none focus:ring-2 focus:ring-primary"
        />

        {/* View Mode Switcher */}
        <div className="mt-2 flex rounded-md overflow-hidden border border-input" role="group" aria-label="Group tags by">
          {VIEW_MODES.map((m) => (
            <button
              key={m.value}
              title={m.label}
              onClick={() => setViewMode(m.value)}
              className={cn(
                "flex-1 py-1 text-[10px] font-medium transition-colors",
                viewMode === m.value
                  ? "bg-primary text-primary-foreground"
                  : "bg-background text-muted-foreground hover:bg-muted"
              )}
            >
              {m.short}
            </button>
          ))}
        </div>
        
        {/* Unselect All Button */}
        {selectedTags.length > 0 && (
          <button
            onClick={handleUnselectAll}
            className="w-full mt-2 px-3 py-1.5 text-xs bg-destructive/10 text-destructive hover:bg-destructive/20 rounded-md transition-colors"
          >
            Uncheck All ({selectedTags.length})
          </button>
        )}
      </div>

      {/* Asset Tree - Scrollable */}
      <div className="overflow-y-auto overflow-x-hidden py-2 flex-1" style={{ minHeight: 0 }}>
        {loading ? (
          <div className="flex items-center justify-center py-8">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary"></div>
          </div>
        ) : filteredTree.length === 0 ? (
          <div className="px-4 py-8 text-center">
            <p className="text-xs text-muted-foreground">
              {searchTerm ? `No results for "${searchTerm}"` : 'No assets found'}
            </p>
          </div>
        ) : (
          filteredTree.map((node) => (
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
              liveTagValues={liveTagValues}
              onTagOpenNewWindow={onTagOpenNewWindow}
              onContextMenuRequest={setContextMenu}
            />
          ))
        )}
      </div>

      {/* Right-click context menu */}
      {contextMenu && (
        <div
          ref={contextMenuRef}
          className="fixed z-50 rounded-md border border-border bg-popover shadow-lg py-1 min-w-[180px]"
          style={{ top: contextMenu.y, left: contextMenu.x }}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="px-3 py-1.5 text-[10px] font-mono text-muted-foreground border-b border-border truncate max-w-[200px]">
            {contextMenu.tagData?.tag_name || contextMenu.tagId}
          </div>
          <button
            className="w-full text-left px-3 py-2 text-xs hover:bg-accent hover:text-accent-foreground flex items-center gap-2"
            onClick={() => {
              if (onTagToggle) onTagToggle(contextMenu.tagId, contextMenu.tagData);
              setContextMenu(null);
            }}
          >
            <Activity className="w-3 h-3" />
            Add to Active Chart
          </button>
          <button
            className="w-full text-left px-3 py-2 text-xs hover:bg-accent hover:text-accent-foreground flex items-center gap-2"
            onClick={() => {
              if (onTagOpenNewWindow) onTagOpenNewWindow(contextMenu.tagId, contextMenu.tagData);
              setContextMenu(null);
            }}
          >
            <TrendingUp className="w-3 h-3" />
            Open in New Chart Window
          </button>
          <div className="border-t border-border my-1" />
          <button
            className="w-full text-left px-3 py-2 text-xs hover:bg-accent hover:text-accent-foreground flex items-center gap-2 text-yellow-400"
            onClick={() => {
              if (onParentContextMenuRequest) onParentContextMenuRequest(contextMenu);
              setContextMenu(null);
            }}
          >
            <span style={{ fontSize: '12px' }}>📈</span>
            View Predictive Trend
          </button>
        </div>
      )}
    </aside>
  );
}

export { AssetSidebar };
