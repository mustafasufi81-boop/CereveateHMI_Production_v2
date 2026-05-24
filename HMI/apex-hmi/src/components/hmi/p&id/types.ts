// P&ID Type Definitions - ISA-101 Compliant

export interface ProcessGraphicConfig {
  id: string;
  name: string;
  width: number;
  height: number;
  backgroundImage?: string;
  equipment: ProcessEquipment[];
  pipes: ProcessPipe[];
  tags: ProcessTagOverlay[];
}

export interface ProcessEquipment {
  id: string;
  type: 'pump' | 'valve' | 'tank' | 'motor' | 'exchanger' | 'compressor' | 'vessel';
  x: number;
  y: number;
  rotation: number;
  scale: number;
  linkedTags: string[];
  statusTag?: string;
  name: string;
  status: 'running' | 'stopped' | 'alarm' | 'warning' | 'offline';
}

export interface ProcessPipe {
  id: string;
  points: { x: number; y: number }[];
  flowDirection?: 'forward' | 'reverse' | 'none';
  flowRateTag?: string;
  color?: string;
  width?: number;
  animated?: boolean;
}

export interface ProcessTagOverlay {
  id: string;
  tagId: string;
  x: number;
  y: number;
  label: string;
  showValue: boolean;
  showUnit: boolean;
  fontSize?: number;
}

export interface EquipmentDetail {
  id: string;
  name: string;
  type: string;
  status: string;
  tags: {
    id: string;
    name: string;
    value: number;
    unit: string;
    status: 'normal' | 'warning' | 'alarm';
  }[];
}
