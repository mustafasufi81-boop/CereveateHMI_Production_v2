import { ProcessTagOverlay } from "./types";

interface ProcessTagComponentProps {
  tagOverlay: ProcessTagOverlay;
  realTimeData: Record<string, any>;
  onTagClick?: (tagId: string) => void;
}

export const ProcessTagComponent = ({ tagOverlay, realTimeData, onTagClick }: ProcessTagComponentProps) => {
  const tagData = realTimeData[tagOverlay.tagId];
  const value = tagData?.value ?? '--';
  const unit = tagData?.unit ?? '';
  const status = tagData?.status ?? 'normal';
  
  // Status colors
  const statusColors = {
    normal: '#00FF00',
    warning: '#FFFF00',
    alarm: '#FF0000',
    offline: '#666666',
  };

  const textColor = statusColors[status as keyof typeof statusColors] || statusColors.normal;
  const fontSize = tagOverlay.fontSize || 12;

  const handleClick = () => {
    if (onTagClick) {
      onTagClick(tagOverlay.tagId);
    }
  };

  return (
    <g
      onClick={handleClick}
      style={{ cursor: onTagClick ? 'pointer' : 'default' }}
    >
      {/* Background Rectangle */}
      <rect
        x={tagOverlay.x - 5}
        y={tagOverlay.y - fontSize - 5}
        width={100}
        height={fontSize * 3 + 10}
        fill="#2A2A2C"
        stroke="#404040"
        strokeWidth="1"
        opacity="0.9"
        rx="3"
      />

      {/* Tag Label */}
      <text
        x={tagOverlay.x}
        y={tagOverlay.y}
        fill="#E5E5E5"
        fontSize={fontSize - 2}
        fontFamily="monospace"
        fontWeight="bold"
      >
        {tagOverlay.label}
      </text>

      {/* Tag Value */}
      {tagOverlay.showValue && (
        <text
          x={tagOverlay.x}
          y={tagOverlay.y + fontSize + 5}
          fill={textColor}
          fontSize={fontSize}
          fontFamily="monospace"
          fontWeight="bold"
        >
          {typeof value === 'number' ? value.toFixed(1) : value}
          {tagOverlay.showUnit && unit && ` ${unit}`}
        </text>
      )}

      {/* Status Indicator */}
      <circle
        cx={tagOverlay.x + 85}
        cy={tagOverlay.y + fontSize / 2}
        r="4"
        fill={textColor}
      >
        {status === 'alarm' && (
          <animate
            attributeName="opacity"
            values="1;0.3;1"
            dur="1s"
            repeatCount="indefinite"
          />
        )}
      </circle>
    </g>
  );
};
