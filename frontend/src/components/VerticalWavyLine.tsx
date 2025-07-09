import React, { useMemo } from 'react';

interface VerticalWavyLineProps {
  className?: string;
  segments?: number;
  amplitude?: number;
  height: number;
  stroke?: string;
}

const VerticalWavyLine: React.FC<VerticalWavyLineProps> = ({
  className = 'text-parchment-400',
  segments = 50, // More segments for a long vertical line
  amplitude = 1.5,
  height,
  stroke,
}) => {
  const pathData = useMemo(() => {
    if (height <= 0) return '';

    let path = 'M 5 0';
    const segmentHeight = height / segments;

    for (let i = 1; i <= segments; i++) {
      const y = i * segmentHeight;
      // Randomly offset the x-coordinate
      const x = 5 + (Math.random() - 0.5) * amplitude * 2;
      path += ` L ${x.toFixed(2)} ${y.toFixed(2)}`;
    }
    return path;
  }, [segments, amplitude, height]);

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
};

export default VerticalWavyLine;
