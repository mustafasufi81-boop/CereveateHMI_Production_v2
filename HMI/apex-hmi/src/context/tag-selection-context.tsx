import { createContext, useContext, useEffect, useState, ReactNode } from 'react';

interface TagSelection {
  date: string;
  selectedPlant?: string;  // Legacy single plant support
  selectedPlants: string[];  // Multi-select plant support
  selectedArea?: string;  // Legacy single area support
  selectedAreas: string[];  // Multi-select area support
  selectedTags: string[];
}

interface TagSelectionContextType {
  selection: TagSelection;
  updateSelection: (updates: Partial<TagSelection>) => void;
  clearSelection: () => void;
}

const TagSelectionContext = createContext<TagSelectionContextType | undefined>(undefined);

const defaultSelection: TagSelection = {
  date: new Date().toISOString().split('T')[0],
  selectedPlants: [],
  selectedAreas: [],
  selectedTags: [],
};

const STORAGE_KEY = 'tag_selection';

export const TagSelectionProvider = ({ children }: { children: ReactNode }) => {
  const [selection, setSelection] = useState<TagSelection>(defaultSelection);
  const [isInitialized, setIsInitialized] = useState(false);

  // Load from localStorage on mount
  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        setSelection({ ...defaultSelection, ...parsed });
      }
    } catch (error) {
      console.error('Failed to load tag selection from localStorage:', error);
    }
    setIsInitialized(true);
  }, []);

  // Persist to localStorage whenever selection changes
  useEffect(() => {
    if (isInitialized) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(selection));
    }
  }, [selection, isInitialized]);

  const updateSelection = (updates: Partial<TagSelection>) => {
    setSelection(prev => ({ ...prev, ...updates }));
  };

  const clearSelection = () => {
    setSelection({ ...defaultSelection, date: new Date().toISOString().split('T')[0] });
    localStorage.removeItem(STORAGE_KEY);
  };

  return (
    <TagSelectionContext.Provider value={{ selection, updateSelection, clearSelection }}>
      {children}
    </TagSelectionContext.Provider>
  );
};

export const useTagSelection = () => {
  const context = useContext(TagSelectionContext);
  if (!context) {
    throw new Error('useTagSelection must be used within TagSelectionProvider');
  }
  return context;
};
