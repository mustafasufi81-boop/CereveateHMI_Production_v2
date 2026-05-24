import { useState, useEffect } from "react";
import { Activity, TrendingUp, Calendar } from "lucide-react";
import { cn } from "@/lib/utils";

interface Tag {
  tag_id: string;
  tag_name: string;
  data_type: string;
  eng_unit?: string;
  description?: string;
  value?: number | string | boolean;
  timestamp?: string;
}

interface TagValuePanelProps {
  selectedNodeId: string;
  tags: Tag[];
  componentName: string;
}

export function TagValuePanel({ selectedNodeId, tags, componentName }: TagValuePanelProps) {
  const [selectedTags, setSelectedTags] = useState<Set<string>>(new Set());
  const [tagValues, setTagValues] = useState<Map<string, any>>(new Map());
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (tags.length > 0 && selectedTags.size > 0) {
      fetchTagValues();
    }
  }, [selectedTags]);

  const fetchTagValues = async () => {
    console.log('[TagValuePanel] Fetching values for tags:', Array.from(selectedTags));
    setLoading(true);
    
    try {
      const token = localStorage.getItem('auth_token');
      const tagIds = Array.from(selectedTags);
      
      // Fetch latest values for selected tags
      const promises = tagIds.map(async (tagId) => {
        const response = await fetch(
          `/api/data/latest/${encodeURIComponent(tagId)}`,
          {
            headers: {
              'Authorization': `Bearer ${token}`,
              'Content-Type': 'application/json'
            }
          }
        );
        
        if (response.ok) {
          const data = await response.json();
          return { tagId, data };
        }
        return { tagId, data: null };
      });
      
      const results = await Promise.all(promises);
      const newValues = new Map();
      results.forEach(({ tagId, data }) => {
        if (data) {
          newValues.set(tagId, data);
        }
      });
      
      setTagValues(newValues);
      console.log('[TagValuePanel] ✅ Fetched values for', newValues.size, 'tags');
    } catch (error) {
      console.error('[TagValuePanel] ❌ Error fetching tag values:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleTagToggle = (tagId: string) => {
    const newSelected = new Set(selectedTags);
    
    if (newSelected.has(tagId)) {
      newSelected.delete(tagId);
    } else {
      // Check if we've reached the max limit of 5
      if (newSelected.size >= 5) {
        console.warn('[TagValuePanel] Maximum 5 tags can be selected');
        return;
      }
      newSelected.add(tagId);
    }
    
    setSelectedTags(newSelected);
    console.log('[TagValuePanel] Selected tags:', Array.from(newSelected));
  };

  const formatValue = (value: any, dataType: string, unit?: string) => {
    if (value === null || value === undefined) return 'N/A';
    
    let formatted = value;
    if (dataType === 'Float' || dataType === 'Double') {
      formatted = typeof value === 'number' ? value.toFixed(2) : value;
    }
    
    return unit ? `${formatted} ${unit}` : formatted;
  };

  const formatTimestamp = (timestamp: string) => {
    if (!timestamp) return '';
    const date = new Date(timestamp);
    return date.toLocaleString();
  };

  if (!tags || tags.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center text-muted-foreground">
          <Activity className="h-12 w-12 mx-auto mb-4 opacity-20" />
          <p className="text-sm">Select a component to view its tags</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-background">
      {/* Header */}
      <div className="border-b border-sidebar-border px-4 py-3">
        <h2 className="text-sm font-semibold text-foreground flex items-center gap-2">
          <Activity className="h-4 w-4" />
          {componentName}
        </h2>
        <p className="text-xs text-muted-foreground mt-1">
          {tags.length} tags available • {selectedTags.size}/5 selected
        </p>
      </div>

      {/* Tag List */}
      <div className="flex-1 overflow-y-auto">
        <div className="p-4 space-y-2">
          {tags.map((tag) => {
            const isSelected = selectedTags.has(tag.tag_id);
            const tagValue = tagValues.get(tag.tag_id);
            
            return (
              <div
                key={tag.tag_id}
                className={cn(
                  "border rounded-lg p-3 transition-colors cursor-pointer hover:bg-accent/50",
                  isSelected ? "border-primary bg-accent" : "border-border"
                )}
                onClick={() => handleTagToggle(tag.tag_id)}
              >
                <div className="flex items-start gap-3">
                  {/* Checkbox - Made more visible */}
                  <div className="mt-1 flex-shrink-0">
                    <div className={cn(
                      "h-5 w-5 rounded border-2 flex items-center justify-center cursor-pointer transition-colors",
                      isSelected 
                        ? "bg-primary border-primary" 
                        : "border-gray-400 bg-white hover:border-primary"
                    )}>
                      {isSelected && (
                        <svg className="h-3 w-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                        </svg>
                      )}
                    </div>
                  </div>

                  {/* Tag Info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-medium text-foreground truncate">
                        {tag.tag_name || tag.tag_id}
                      </span>
                      <span className="text-xs text-muted-foreground bg-muted px-2 py-0.5 rounded">
                        {tag.data_type}
                      </span>
                    </div>
                    
                    <p className="text-xs text-muted-foreground mt-1 font-mono">
                      {tag.tag_id}
                    </p>
                    
                    {tag.description && (
                      <p className="text-xs text-muted-foreground mt-1">
                        {tag.description}
                      </p>
                    )}

                    {/* Live Value - Only show if selected */}
                    {isSelected && tagValue && (
                      <div className="mt-2 pt-2 border-t border-border/50">
                        <div className="flex items-center justify-between">
                          <span className="text-xs text-muted-foreground">Latest Value:</span>
                          <span className="text-sm font-semibold text-primary">
                            {formatValue(tagValue.value, tag.data_type, tag.eng_unit)}
                          </span>
                        </div>
                        {tagValue.timestamp && (
                          <div className="flex items-center gap-1 mt-1 text-xs text-muted-foreground">
                            <Calendar className="h-3 w-3" />
                            {formatTimestamp(tagValue.timestamp)}
                          </div>
                        )}
                      </div>
                    )}

                    {isSelected && loading && !tagValue && (
                      <div className="mt-2 pt-2 border-t border-border/50">
                        <span className="text-xs text-muted-foreground animate-pulse">
                          Loading value...
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Footer - Show trend button when tags are selected */}
      {selectedTags.size > 0 && (
        <div className="border-t border-sidebar-border p-4">
          <button
            onClick={() => {
              console.log('[TagValuePanel] View trend for:', Array.from(selectedTags));
              // TODO: Navigate to trend view with selected tags
            }}
            className="w-full bg-primary text-primary-foreground hover:bg-primary/90 px-4 py-2 rounded-md text-sm font-medium flex items-center justify-center gap-2 transition-colors"
          >
            <TrendingUp className="h-4 w-4" />
            View Historical Trend
          </button>
        </div>
      )}
    </div>
  );
}
