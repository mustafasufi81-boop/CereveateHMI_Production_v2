import { ProcessEquipment } from "./types";
import { cn } from "@/lib/utils";

// ISA-101 Equipment Status Colors
const STATUS_COLORS = {
  running: '#00C851',
  stopped: '#808080',
  alarm: '#FF4444',
  warning: '#FFB300',
  offline: '#666666',
};

interface ProcessEquipmentSymbolProps {
  equipment: ProcessEquipment;
  realTimeData: Record<string, any>;
  isHovered: boolean;
  onClick: () => void;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
}

export const ProcessEquipmentSymbol = ({
  equipment,
  realTimeData,
  isHovered,
  onClick,
  onMouseEnter,
  onMouseLeave,
}: ProcessEquipmentSymbolProps) => {
  const statusColor = STATUS_COLORS[equipment.status] || STATUS_COLORS.offline;
  const strokeWidth = isHovered ? 3 : 2;

  const renderSymbol = () => {
    switch (equipment.type) {
      case 'pump':
        return (
          <g>
            {/* Pump Body - Circle */}
            <circle
              cx={equipment.x}
              cy={equipment.y}
              r={30 * equipment.scale}
              fill="none"
              stroke={statusColor}
              strokeWidth={strokeWidth}
            />
            {/* Pump Impeller - Triangle */}
            <path
              d={`M ${equipment.x} ${equipment.y - 15 * equipment.scale} 
                  L ${equipment.x + 13 * equipment.scale} ${equipment.y + 7.5 * equipment.scale} 
                  L ${equipment.x - 13 * equipment.scale} ${equipment.y + 7.5 * equipment.scale} Z`}
              fill={statusColor}
              opacity="0.7"
            />
            {/* Rotation animation for running pumps */}
            {equipment.status === 'running' && (
              <animateTransform
                attributeName="transform"
                attributeType="XML"
                type="rotate"
                from={`0 ${equipment.x} ${equipment.y}`}
                to={`360 ${equipment.x} ${equipment.y}`}
                dur="2s"
                repeatCount="indefinite"
              />
            )}
          </g>
        );

      case 'valve':
        return (
          <g>
            {/* Valve Body - Diamond */}
            <path
              d={`M ${equipment.x} ${equipment.y - 25 * equipment.scale}
                  L ${equipment.x + 25 * equipment.scale} ${equipment.y}
                  L ${equipment.x} ${equipment.y + 25 * equipment.scale}
                  L ${equipment.x - 25 * equipment.scale} ${equipment.y} Z`}
              fill="none"
              stroke={statusColor}
              strokeWidth={strokeWidth}
            />
            {/* Valve Stem */}
            <line
              x1={equipment.x}
              y1={equipment.y - 25 * equipment.scale}
              x2={equipment.x}
              y2={equipment.y - 40 * equipment.scale}
              stroke={statusColor}
              strokeWidth={strokeWidth}
            />
          </g>
        );

      case 'tank':
        return (
          <g>
            {/* Tank Body - Rectangle */}
            <rect
              x={equipment.x - 40 * equipment.scale}
              y={equipment.y - 50 * equipment.scale}
              width={80 * equipment.scale}
              height={100 * equipment.scale}
              fill="none"
              stroke={statusColor}
              strokeWidth={strokeWidth}
              rx="5"
            />
            {/* Level Indicator (if available) */}
            {equipment.statusTag && realTimeData[equipment.statusTag] && (
              <rect
                x={equipment.x - 38 * equipment.scale}
                y={equipment.y + 48 * equipment.scale - (realTimeData[equipment.statusTag].value || 0)}
                width={76 * equipment.scale}
                height={realTimeData[equipment.statusTag].value || 0}
                fill={statusColor}
                opacity="0.3"
              />
            )}
          </g>
        );

      case 'motor':
        return (
          <g>
            {/* Motor Body - Circle */}
            <circle
              cx={equipment.x}
              cy={equipment.y}
              r={25 * equipment.scale}
              fill="none"
              stroke={statusColor}
              strokeWidth={strokeWidth}
            />
            {/* Motor "M" Label */}
            <text
              x={equipment.x}
              y={equipment.y + 5}
              textAnchor="middle"
              fill={statusColor}
              fontSize={20 * equipment.scale}
              fontWeight="bold"
              fontFamily="monospace"
            >
              M
            </text>
          </g>
        );

      case 'compressor':
        return (
          <g>
            {/* Compressor Body - Trapezoid */}
            <path
              d={`M ${equipment.x - 30 * equipment.scale} ${equipment.y + 20 * equipment.scale}
                  L ${equipment.x - 20 * equipment.scale} ${equipment.y - 20 * equipment.scale}
                  L ${equipment.x + 20 * equipment.scale} ${equipment.y - 20 * equipment.scale}
                  L ${equipment.x + 30 * equipment.scale} ${equipment.y + 20 * equipment.scale} Z`}
              fill="none"
              stroke={statusColor}
              strokeWidth={strokeWidth}
            />
            {/* Compressor Blades */}
            <circle cx={equipment.x} cy={equipment.y} r={8 * equipment.scale} fill={statusColor} opacity="0.5" />
          </g>
        );

      case 'exchanger':
        return (
          <g>
            {/* Heat Exchanger - Two circles overlapping */}
            <circle
              cx={equipment.x - 15 * equipment.scale}
              cy={equipment.y}
              r={20 * equipment.scale}
              fill="none"
              stroke={statusColor}
              strokeWidth={strokeWidth}
            />
            <circle
              cx={equipment.x + 15 * equipment.scale}
              cy={equipment.y}
              r={20 * equipment.scale}
              fill="none"
              stroke={statusColor}
              strokeWidth={strokeWidth}
            />
          </g>
        );

      case 'vessel':
        return (
          <g>
            {/* Vessel - Ellipse */}
            <ellipse
              cx={equipment.x}
              cy={equipment.y}
              rx={30 * equipment.scale}
              ry={40 * equipment.scale}
              fill="none"
              stroke={statusColor}
              strokeWidth={strokeWidth}
            />
          </g>
        );

      default:
        return (
          <rect
            x={equipment.x - 20 * equipment.scale}
            y={equipment.y - 20 * equipment.scale}
            width={40 * equipment.scale}
            height={40 * equipment.scale}
            fill="none"
            stroke={statusColor}
            strokeWidth={strokeWidth}
          />
        );
    }
  };

  return (
    <g
      onClick={onClick}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      style={{ cursor: 'pointer' }}
      transform={`rotate(${equipment.rotation} ${equipment.x} ${equipment.y})`}
    >
      {renderSymbol()}
      
      {/* Equipment Label */}
      <text
        x={equipment.x}
        y={equipment.y + 60 * equipment.scale}
        textAnchor="middle"
        fill="#E5E5E5"
        fontSize={12}
        fontFamily="monospace"
        fontWeight="bold"
      >
        {equipment.name}
      </text>

      {/* Hover Effect */}
      {isHovered && (
        <circle
          cx={equipment.x}
          cy={equipment.y}
          r={50 * equipment.scale}
          fill="none"
          stroke="#FFB300"
          strokeWidth="2"
          strokeDasharray="5,5"
          opacity="0.5"
        />
      )}
    </g>
  );
};
