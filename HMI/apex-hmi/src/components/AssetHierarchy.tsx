import React, { useState, useEffect } from 'react';
import { ChevronRight, ChevronDown, Factory, Layers, Box, Cpu, Component, Tag } from 'lucide-react';

interface Tag {
  tag_id: string;
  tag_name: string;
  data_type: string;
  eng_unit: string;
  description: string;
  trip_category: string | null;
  criticality: number | null;
}

interface AssetNode {
  id: string;
  name: string;
  type: 'plant' | 'area' | 'equipment' | 'sub_equipment' | 'component';
  tag_count: number;
  children?: AssetNode[];
  tags?: Tag[];
}

interface AssetHierarchyResponse {
  hierarchy: AssetNode[];
  statistics: {
    total_tags: number;
    filtered_tags: number;
    plants: number;
    timestamp: string;
  };
}

const AssetHierarchy: React.FC = () => {
  const [hierarchy, setHierarchy] = useState<AssetNode[]>([]);
  const [statistics, setStatistics] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set());
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedNode, setSelectedNode] = useState<AssetNode | null>(null);

  useEffect(() => {
    fetchAssetHierarchy();
  }, []);

  const fetchAssetHierarchy = async () => {
    console.log('[AssetHierarchy] 🔍 Fetching asset hierarchy...');
    try {
      setLoading(true);
      const token = localStorage.getItem('auth_token'); // Fixed: use 'auth_token' instead of 'token'
      console.log('[AssetHierarchy] 🔑 Token:', token ? `${token.substring(0, 20)}...` : 'NOT FOUND');
      
      const response = await fetch('/api/assets/hierarchy', {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      console.log('[AssetHierarchy] 📥 Response status:', response.status);

      if (!response.ok) {
        const errorText = await response.text();
        console.error('[AssetHierarchy] ❌ Error response:', errorText);
        throw new Error(`Failed to fetch asset hierarchy: ${response.status}`);
      }

      const data: AssetHierarchyResponse = await response.json();
      console.log('[AssetHierarchy] ✅ Data received:', data);
      console.log('[AssetHierarchy] 📊 Hierarchy length:', data.hierarchy?.length || 0);
      console.log('[AssetHierarchy] 📊 Statistics:', data.statistics);
      
      setHierarchy(data.hierarchy);
      setStatistics(data.statistics);
      
      // Auto-expand first plant
      if (data.hierarchy.length > 0) {
        setExpandedNodes(new Set([data.hierarchy[0].id]));
        console.log('[AssetHierarchy] 🌳 Auto-expanded first plant:', data.hierarchy[0].name);
      } else {
        console.warn('[AssetHierarchy] ⚠️  No plants in hierarchy!');
      }
    } catch (err) {
      console.error('[AssetHierarchy] ❌ Exception:', err);
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  const toggleNode = (nodeId: string) => {
    setExpandedNodes(prev => {
      const newSet = new Set(prev);
      if (newSet.has(nodeId)) {
        newSet.delete(nodeId);
      } else {
        newSet.add(nodeId);
      }
      return newSet;
    });
  };

  const expandAll = () => {
    const allIds = new Set<string>();
    const collectIds = (nodes: AssetNode[]) => {
      nodes.forEach(node => {
        allIds.add(node.id);
        if (node.children) {
          collectIds(node.children);
        }
      });
    };
    collectIds(hierarchy);
    setExpandedNodes(allIds);
  };

  const collapseAll = () => {
    setExpandedNodes(new Set());
  };

  const getIcon = (type: string) => {
    switch (type) {
      case 'plant':
        return <Factory className="w-4 h-4 text-blue-600" />;
      case 'area':
        return <Layers className="w-4 h-4 text-green-600" />;
      case 'equipment':
        return <Box className="w-4 h-4 text-orange-600" />;
      case 'sub_equipment':
        return <Cpu className="w-4 h-4 text-purple-600" />;
      case 'component':
        return <Component className="w-4 h-4 text-pink-600" />;
      default:
        return <Tag className="w-4 h-4 text-gray-600" />;
    }
  };

  const getCriticalityColor = (criticality: number | null) => {
    if (!criticality) return 'bg-gray-100';
    switch (criticality) {
      case 5: return 'bg-red-100 text-red-800';
      case 4: return 'bg-orange-100 text-orange-800';
      case 3: return 'bg-yellow-100 text-yellow-800';
      case 2: return 'bg-blue-100 text-blue-800';
      case 1: return 'bg-green-100 text-green-800';
      default: return 'bg-gray-100';
    }
  };

  const filterNodes = (nodes: AssetNode[], term: string): AssetNode[] => {
    if (!term) return nodes;
    
    const lowerTerm = term.toLowerCase();
    return nodes.map(node => {
      const nameMatch = node.name.toLowerCase().includes(lowerTerm);
      const filteredChildren = node.children ? filterNodes(node.children, term) : [];
      const tagMatches = node.tags?.filter(tag => 
        tag.tag_id.toLowerCase().includes(lowerTerm) ||
        tag.tag_name?.toLowerCase().includes(lowerTerm) ||
        tag.description?.toLowerCase().includes(lowerTerm)
      ) || [];

      if (nameMatch || filteredChildren.length > 0 || tagMatches.length > 0) {
        return {
          ...node,
          children: filteredChildren.length > 0 ? filteredChildren : (node.children || []),
          tags: tagMatches.length > 0 ? tagMatches : (node.tags || [])
        };
      }
      return null;
    }).filter((node) => node !== null) as AssetNode[];
  };

  const renderNode = (node: AssetNode, level: number = 0) => {
    const isExpanded = expandedNodes.has(node.id);
    const hasChildren = node.children && node.children.length > 0;
    const hasTags = node.tags && node.tags.length > 0;
    const isSelected = selectedNode?.id === node.id;

    return (
      <div key={node.id} className="select-none">
        <div
          className={`flex items-center gap-2 py-2 px-3 hover:bg-gray-50 cursor-pointer transition-colors ${
            isSelected ? 'bg-blue-50 border-l-4 border-blue-500' : ''
          }`}
          style={{ paddingLeft: `${level * 20 + 12}px` }}
          onClick={() => {
            if (hasChildren || hasTags) {
              toggleNode(node.id);
            }
            setSelectedNode(node);
          }}
        >
          {(hasChildren || hasTags) && (
            <span className="flex-shrink-0">
              {isExpanded ? (
                <ChevronDown className="w-4 h-4 text-gray-500" />
              ) : (
                <ChevronRight className="w-4 h-4 text-gray-500" />
              )}
            </span>
          )}
          {!(hasChildren || hasTags) && <span className="w-4" />}
          
          <span className="flex-shrink-0">{getIcon(node.type)}</span>
          
          <span className="flex-1 font-medium text-sm text-gray-700">
            {node.name}
          </span>
          
          <span className="text-xs text-gray-500 bg-gray-100 px-2 py-1 rounded-full">
            {node.tag_count} tags
          </span>
        </div>

        {isExpanded && (
          <>
            {hasChildren && node.children!.map(child => renderNode(child, level + 1))}
            
            {hasTags && (
              <div className="ml-8" style={{ paddingLeft: `${level * 20}px` }}>
                {node.tags!.map(tag => (
                  <div
                    key={tag.tag_id}
                    className="flex items-center gap-2 py-1.5 px-3 hover:bg-gray-50 cursor-pointer text-sm border-l-2 border-gray-200"
                  >
                    <Tag className="w-3 h-3 text-gray-400" />
                    <span className="flex-1 text-gray-600 font-mono text-xs">
                      {tag.tag_id}
                    </span>
                    {tag.tag_name && (
                      <span className="text-xs text-gray-500">{tag.tag_name}</span>
                    )}
                    {tag.data_type && (
                      <span className="text-xs text-gray-400 bg-gray-50 px-1.5 py-0.5 rounded">
                        {tag.data_type}
                      </span>
                    )}
                    {tag.eng_unit && (
                      <span className="text-xs text-blue-600">{tag.eng_unit}</span>
                    )}
                    {tag.criticality && (
                      <span className={`text-xs px-2 py-0.5 rounded ${getCriticalityColor(tag.criticality)}`}>
                        L{tag.criticality}
                      </span>
                    )}
                    {tag.trip_category && (
                      <span className="text-xs bg-red-50 text-red-700 px-2 py-0.5 rounded">
                        {tag.trip_category}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    );
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Loading asset hierarchy...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4">
        <p className="text-red-800">Error: {error}</p>
        <button
          onClick={fetchAssetHierarchy}
          className="mt-2 text-sm text-red-600 hover:text-red-800 underline"
        >
          Retry
        </button>
      </div>
    );
  }

  const filteredHierarchy = filterNodes(hierarchy, searchTerm);

  return (
    <div className="h-full flex flex-col bg-white rounded-lg shadow-sm">
      {/* Header */}
      <div className="border-b border-gray-200 p-4">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-bold text-gray-800">Asset Hierarchy</h2>
          <div className="flex gap-2">
            <button
              onClick={expandAll}
              className="px-3 py-1 text-sm bg-blue-50 text-blue-600 hover:bg-blue-100 rounded transition-colors"
            >
              Expand All
            </button>
            <button
              onClick={collapseAll}
              className="px-3 py-1 text-sm bg-gray-50 text-gray-600 hover:bg-gray-100 rounded transition-colors"
            >
              Collapse All
            </button>
            <button
              onClick={fetchAssetHierarchy}
              className="px-3 py-1 text-sm bg-green-50 text-green-600 hover:bg-green-100 rounded transition-colors"
            >
              Refresh
            </button>
          </div>
        </div>

        {/* Search */}
        <input
          type="text"
          placeholder="Search assets or tags..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
        />

        {/* Statistics */}
        {statistics && (
          <div className="mt-4 grid grid-cols-3 gap-4">
            <div className="bg-blue-50 rounded-lg p-3">
              <p className="text-xs text-blue-600 font-medium">Total Tags</p>
              <p className="text-2xl font-bold text-blue-700">{statistics.total_tags}</p>
            </div>
            <div className="bg-green-50 rounded-lg p-3">
              <p className="text-xs text-green-600 font-medium">Plants</p>
              <p className="text-2xl font-bold text-green-700">{statistics.plants}</p>
            </div>
            <div className="bg-purple-50 rounded-lg p-3">
              <p className="text-xs text-purple-600 font-medium">Filtered</p>
              <p className="text-2xl font-bold text-purple-700">{statistics.filtered_tags}</p>
            </div>
          </div>
        )}
      </div>

      {/* Tree View */}
      <div className="flex-1 overflow-auto">
        {filteredHierarchy.length === 0 ? (
          <div className="flex items-center justify-center h-full text-gray-500">
            <p>No assets found matching "{searchTerm}"</p>
          </div>
        ) : (
          <div className="py-2">
            {filteredHierarchy.map(node => renderNode(node))}
          </div>
        )}
      </div>

      {/* Legend */}
      <div className="border-t border-gray-200 p-4 bg-gray-50">
        <p className="text-xs font-medium text-gray-600 mb-2">Hierarchy Levels:</p>
        <div className="flex flex-wrap gap-3 text-xs">
          <div className="flex items-center gap-1">
            <Factory className="w-3 h-3 text-blue-600" />
            <span className="text-gray-600">Plant</span>
          </div>
          <div className="flex items-center gap-1">
            <Layers className="w-3 h-3 text-green-600" />
            <span className="text-gray-600">Area</span>
          </div>
          <div className="flex items-center gap-1">
            <Box className="w-3 h-3 text-orange-600" />
            <span className="text-gray-600">Equipment</span>
          </div>
          <div className="flex items-center gap-1">
            <Cpu className="w-3 h-3 text-purple-600" />
            <span className="text-gray-600">Sub-Equipment</span>
          </div>
          <div className="flex items-center gap-1">
            <Component className="w-3 h-3 text-pink-600" />
            <span className="text-gray-600">Component</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AssetHierarchy;
