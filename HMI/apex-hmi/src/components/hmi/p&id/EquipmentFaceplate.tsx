import { X } from "lucide-react";
import { ProcessEquipment } from "./types";
import { Button } from "@/components/ui/button";

interface EquipmentFaceplateProps {
  equipment: ProcessEquipment;
  realTimeData: Record<string, any>;
  onClose: () => void;
  onTagClick?: (tagId: string) => void;
}

export const EquipmentFaceplate = ({ equipment, realTimeData, onClose, onTagClick }: EquipmentFaceplateProps) => {
  const statusColors = {
    running: '#00C851',
    stopped: '#808080',
    alarm: '#FF4444',
    warning: '#FFB300',
    offline: '#666666',
  };

  const statusColor = statusColors[equipment.status] || statusColors.offline;

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 backdrop-blur-sm">
      <div className="bg-[#2A2A2C] border-2 border-[#404040] rounded-none w-[600px] max-h-[80vh] overflow-y-auto shadow-2xl">
        {/* Header */}
        <div className="bg-[#1C1C1E] border-b-2 border-[#404040] px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div
              className="w-3 h-3 rounded-full"
              style={{ backgroundColor: statusColor }}
            />
            <div>
              <h3 className="text-white font-bold uppercase tracking-wider">
                {equipment.name}
              </h3>
              <p className="text-xs text-gray-400 font-mono">
                {equipment.type.toUpperCase()} • READ-ONLY VIEW
              </p>
            </div>
          </div>
          <Button
            onClick={onClose}
            variant="ghost"
            size="icon"
            className="text-gray-400 hover:text-white hover:bg-[#404040]"
          >
            <X className="h-5 w-5" />
          </Button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-4">
          {/* Equipment Status */}
          <div className="bg-[#1C1C1E] border border-[#404040] p-4 rounded-none">
            <div className="text-xs text-gray-400 uppercase tracking-wider mb-2">
              Equipment Status
            </div>
            <div className="flex items-center gap-2">
              <span className="text-2xl font-bold uppercase tracking-wide" style={{ color: statusColor }}>
                {equipment.status}
              </span>
            </div>
          </div>

          {/* Linked Tags */}
          {equipment.linkedTags.length > 0 && (
            <div className="bg-[#1C1C1E] border border-[#404040] p-4 rounded-none">
              <div className="text-xs text-gray-400 uppercase tracking-wider mb-3">
                Process Tags ({equipment.linkedTags.length})
              </div>
              <div className="space-y-2">
                {equipment.linkedTags.map((tagId) => {
                  const tagData = realTimeData[tagId];
                  if (!tagData) return null;

                  const valueColor = 
                    tagData.status === 'alarm' ? '#FF0000' :
                    tagData.status === 'warning' ? '#FFFF00' : '#00FF00';

                  return (
                    <div
                      key={tagId}
                      className="flex items-center justify-between p-3 bg-[#2A2A2C] border border-[#404040] cursor-pointer hover:border-[#FFB300] transition-colors"
                      onClick={() => onTagClick && onTagClick(tagId)}
                    >
                      <div className="flex-1">
                        <div className="text-sm font-mono text-white font-bold">
                          {tagId}
                        </div>
                        <div className="text-xs text-gray-400">
                          {tagData.description || 'No description'}
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="text-lg font-mono font-bold" style={{ color: valueColor }}>
                          {typeof tagData.value === 'number' ? tagData.value.toFixed(2) : tagData.value}
                        </div>
                        <div className="text-xs text-gray-400 font-mono">
                          {tagData.unit}
                        </div>
                      </div>
                      <div className="ml-3">
                        <div
                          className="w-2 h-2 rounded-full"
                          style={{ backgroundColor: valueColor }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Additional Info */}
          <div className="bg-[#1C1C1E] border border-[#404040] p-4 rounded-none">
            <div className="text-xs text-gray-400 uppercase tracking-wider mb-2">
              Equipment Details
            </div>
            <div className="grid grid-cols-2 gap-3 text-sm font-mono">
              <div>
                <span className="text-gray-400">ID:</span>{' '}
                <span className="text-white">{equipment.id}</span>
              </div>
              <div>
                <span className="text-gray-400">Type:</span>{' '}
                <span className="text-white">{equipment.type.toUpperCase()}</span>
              </div>
            </div>
          </div>

          {/* Read-Only Notice */}
          <div className="bg-amber-500/10 border border-amber-500/30 p-3 rounded-none">
            <p className="text-xs text-amber-400 font-mono">
              ⚠️ READ-ONLY MODE: Control interactions are disabled. This is a visualization-only view.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
