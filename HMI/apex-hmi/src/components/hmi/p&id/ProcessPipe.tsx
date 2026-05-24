import { ProcessPipe } from "./types";

interface ProcessPipeComponentProps {
  pipe: ProcessPipe;
  flowRate?: number;
}

export const ProcessPipeComponent = ({ pipe, flowRate }: ProcessPipeComponentProps) => {
  const pathData = pipe.points.map((point, index) => 
    `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`
  ).join(' ');

  const pipeColor = pipe.color || '#808080';
  const pipeWidth = pipe.width || 4;
  const isFlowing = flowRate !== undefined && flowRate > 0;

  return (
    <g>
      {/* Main Pipe Path */}
      <path
        d={pathData}
        fill="none"
        stroke={pipeColor}
        strokeWidth={pipeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
      />

      {/* Flow Animation - Moving Dots */}
      {pipe.animated && isFlowing && pipe.flowDirection !== 'none' && (
        <>
          {/* Animated Flow Dots */}
          <circle r="3" fill="#00FF00" opacity="0.8">
            <animateMotion
              dur={pipe.flowDirection === 'forward' ? '3s' : '3s'}
              repeatCount="indefinite"
              path={pathData}
            />
          </circle>
          <circle r="3" fill="#00FF00" opacity="0.6">
            <animateMotion
              dur={pipe.flowDirection === 'forward' ? '3s' : '3s'}
              repeatCount="indefinite"
              path={pathData}
              begin="1s"
            />
          </circle>
          <circle r="3" fill="#00FF00" opacity="0.4">
            <animateMotion
              dur={pipe.flowDirection === 'forward' ? '3s' : '3s'}
              repeatCount="indefinite"
              path={pathData}
              begin="2s"
            />
          </circle>
        </>
      )}

      {/* Flow Direction Arrow */}
      {pipe.flowDirection && pipe.flowDirection !== 'none' && (
        <g>
          {pipe.points.slice(0, -1).map((point, index) => {
            const nextPoint = pipe.points[index + 1];
            const midX = (point.x + nextPoint.x) / 2;
            const midY = (point.y + nextPoint.y) / 2;
            const angle = Math.atan2(nextPoint.y - point.y, nextPoint.x - point.x) * 180 / Math.PI;
            
            return (
              <g key={index} transform={`translate(${midX}, ${midY}) rotate(${angle})`}>
                <path
                  d="M -5 -5 L 5 0 L -5 5 Z"
                  fill={pipeColor}
                  opacity="0.7"
                />
              </g>
            );
          })}
        </g>
      )}
    </g>
  );
};
