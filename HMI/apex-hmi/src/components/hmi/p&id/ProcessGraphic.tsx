import { useState } from "react";
import { ProcessEquipmentSymbol } from "./ProcessEquipment";
import { ProcessPipeComponent } from "./ProcessPipe";
import { ProcessTagComponent } from "./ProcessTag";
import { EquipmentFaceplate } from "./EquipmentFaceplate";
import { ProcessGraphicConfig, ProcessEquipment } from "./types";
import { cn } from "@/lib/utils";

interface ProcessGraphicProps {
  config: ProcessGraphicConfig;
  realTimeData?: Record<string, any>;
  onTagClick?: (tagId: string) => void;
}

export const ProcessGraphic = ({ config, realTimeData = {}, onTagClick }: ProcessGraphicProps) => {
  const [selectedEquipment, setSelectedEquipment] = useState<ProcessEquipment | null>(null);
  const [hoveredEquipment, setHoveredEquipment] = useState<string | null>(null);

  const handleEquipmentClick = (equipment: ProcessEquipment) => {
    setSelectedEquipment(equipment);
  };

  const handleCloseFaceplate = () => {
    setSelectedEquipment(null);
  };

  return (
    <div className="relative w-full h-full bg-[#1C1C1E] border-2 border-[#404040] overflow-hidden">
      {/* SVG Canvas for P&ID */}
      <svg
        width={config.width}
        height={config.height}
        viewBox={`0 0 ${config.width} ${config.height}`}
        className="w-full h-full"
        style={{ minHeight: '600px' }}
      >
        {/* Background Image (if provided) */}
        {config.backgroundImage && (
          <image
            href={config.backgroundImage}
            x="0"
            y="0"
            width={config.width}
            height={config.height}
            opacity="0.3"
          />
        )}

        {/* Pipes Layer */}
        <g id="pipes-layer">
          {config.pipes.map((pipe) => (
            <ProcessPipeComponent
              key={pipe.id}
              pipe={pipe}
              flowRate={pipe.flowRateTag ? realTimeData[pipe.flowRateTag]?.value : undefined}
            />
          ))}
        </g>

        {/* Equipment Layer */}
        <g id="equipment-layer">
          {config.equipment.map((equipment) => (
            <ProcessEquipmentSymbol
              key={equipment.id}
              equipment={equipment}
              realTimeData={realTimeData}
              isHovered={hoveredEquipment === equipment.id}
              onClick={() => handleEquipmentClick(equipment)}
              onMouseEnter={() => setHoveredEquipment(equipment.id)}
              onMouseLeave={() => setHoveredEquipment(null)}
            />
          ))}
        </g>

        {/* Tag Overlays Layer */}
        <g id="tags-layer">
          {config.tags.map((tagOverlay) => (
            <ProcessTagComponent
              key={tagOverlay.id}
              tagOverlay={tagOverlay}
              realTimeData={realTimeData}
              onTagClick={onTagClick}
            />
          ))}
        </g>
      </svg>

      {/* Equipment Faceplate Modal (Read-Only) */}
      {selectedEquipment && (
        <EquipmentFaceplate
          equipment={selectedEquipment}
          realTimeData={realTimeData}
          onClose={handleCloseFaceplate}
          onTagClick={onTagClick}
        />
      )}

      {/* P&ID Title Bar */}
      <div className="absolute top-0 left-0 right-0 bg-[#2A2A2C] border-b-2 border-[#404040] px-4 py-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
            <h2 className="text-sm font-bold text-white uppercase tracking-wider">
              {config.name}
            </h2>
            <span className="text-xs text-gray-400 font-mono">READ-ONLY VIEW</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-400">
              Equipment: {config.equipment.length} | Tags: {config.tags.length}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};
