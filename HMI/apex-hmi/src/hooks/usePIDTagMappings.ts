import { useState, useEffect } from 'react';

interface PIDTag {
  tagId: string;
  tagName: string;
  description: string;
  equipment: string;
  unit: string;
  dataType: string;
  limits: {
    hiLimit: number | null;
    hiWarning: number | null;
    loWarning: number | null;
    loLimit: number | null;
  };
  plant: string;
  area: string;
}

interface PIDTagMappingsResponse {
  count: number;
  tags: PIDTag[];
  timestamp: string;
}

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api';

/**
 * Custom hook to fetch P&ID tag mappings from tag_master
 * These mappings are used to initialize P&ID visualizations with real equipment tags
 */
export const usePIDTagMappings = () => {
  const [tags, setTags] = useState<PIDTag[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchPIDMappings = async () => {
      try {
        setLoading(true);
        const token = localStorage.getItem('token');
        
        const response = await fetch(`${API_BASE_URL}/tags/pid-mappings`, {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          }
        });

        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data: PIDTagMappingsResponse = await response.json();
        console.log(`🎨 [P&ID Hook] Loaded ${data.count} tag mappings from tag_master`);
        setTags(data.tags);
        setError(null);
      } catch (err) {
        console.error('❌ [P&ID Hook] Failed to load tag mappings:', err);
        setError(err instanceof Error ? err.message : 'Unknown error');
      } finally {
        setLoading(false);
      }
    };

    fetchPIDMappings();
  }, []);

  /**
   * Get tag mapping by tag name
   */
  const getTagByName = (tagName: string): PIDTag | undefined => {
    return tags.find(t => t.tagName === tagName || t.tagId === tagName);
  };

  /**
   * Get all tags for specific equipment
   */
  const getTagsByEquipment = (equipment: string): PIDTag[] => {
    return tags.filter(t => t.equipment.toLowerCase().includes(equipment.toLowerCase()));
  };

  /**
   * Get tag mappings grouped by equipment
   */
  const getTagsByEquipmentGrouped = (): Record<string, PIDTag[]> => {
    const grouped: Record<string, PIDTag[]> = {};
    tags.forEach(tag => {
      if (!grouped[tag.equipment]) {
        grouped[tag.equipment] = [];
      }
      grouped[tag.equipment].push(tag);
    });
    return grouped;
  };

  return {
    tags,
    loading,
    error,
    getTagByName,
    getTagsByEquipment,
    getTagsByEquipmentGrouped
  };
};
