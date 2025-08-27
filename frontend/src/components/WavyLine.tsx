import React, { useMemo } from 'react';

interface WavyLineProps {
  direction: 'horizontal' | 'vertical';
  className?: string;
  segments?: number;
  amplitude?: number;
  height?: number; // Required for vertical direction
  stroke?: string;
}

const WavyLine: React.FC<WavyLineProps> = ({
  direction,
  className = 'text-parchment-400',
  segments = direction === 'vertical' ? 50 : 20,
  amplitude = direction === 'vertical' ? 1.5 : 2,
  height,
  stroke,
}) => {
  const pathData = useMemo(() => {
    if (direction === 'vertical' && (!height || height <= 0)) return '';

    if (direction === 'horizontal') {
      let path = 'M 0 5';
      const segmentWidth = 100 / segments;

      for (let i = 0; i <= segments; i++) {
        const x = i * segmentWidth;
        const y = 5 + (Math.random() - 0.5) * amplitude * 2;
        path += ` L ${x} ${y}`;
      }
      return path;
    } else {
      // Vertical direction
      let path = 'M 5 0';
      const segmentHeight = height! / segments;

      for (let i = 1; i <= segments; i++) {
        const y = i * segmentHeight;
        const x = 5 + (Math.random() - 0.5) * amplitude * 2;
        path += ` L ${x.toFixed(2)} ${y.toFixed(2)}`;
      }
      return path;
    }
  }, [direction, segments, amplitude, height]);

  if (direction === 'vertical' && (!height || height <= 0)) {
    return null;
  }

  if (direction === 'horizontal') {
    return (
      <svg
        className={`w-full h-3 ${className}`}
        viewBox="0 0 100 10"
        preserveAspectRatio="none"
        aria-hidden="true"
        style={{ filter: 'drop-shadow(0 1px 2px rgba(0,0,0,0.1))' }}
      >
        <path
          d={pathData}
          fill="none"
          stroke="currentColor"
          strokeWidth="1.2"
          strokeLinecap="round"
          style={{
            paintOrder: 'stroke fill',
            strokeDasharray: '0.5 0.5',
            strokeDashoffset: '0',
            opacity: '0.9',
          }}
        />
      </svg>
    );
  } else {
    // Vertical direction
    return (
      <svg
        className={`absolute left-4 top-0 h-full w-full ${className || ''}`}
        preserveAspectRatio="none"
        aria-hidden="true"
      >
        <path
          d={pathData}
          fill="none"
          stroke={stroke || 'currentColor'}
          strokeWidth="2"
          strokeLinecap="round"
        />
      </svg>
    );
  }
};

export default WavyLine;
