import React, { useMemo } from 'react';

interface WavyLineProps {
  className?: string;
  segments?: number;
  amplitude?: number;
}

const WavyLine: React.FC<WavyLineProps> = ({
  className = 'text-parchment-400',
  segments = 20,
  amplitude = 2,
}) => {
  const pathData = useMemo(() => {
    let path = 'M 0 5';
    const segmentWidth = 100 / segments;

    for (let i = 0; i <= segments; i++) {
      const x = i * segmentWidth;
      const y = 5 + (Math.random() - 0.5) * amplitude * 2;
      path += ` L ${x} ${y}`;
    }
    return path;
  }, [segments, amplitude]);

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
};

export default WavyLine;
