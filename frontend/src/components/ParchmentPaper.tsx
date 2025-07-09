import React, { useState, useRef, useLayoutEffect, useMemo, useId } from 'react';

interface ParchmentPaperProps {
  children: React.ReactNode;
  className?: string;
  padding?: string;
}

// Deterministic PRNG for consistent wavy borders across re-renders
function mulberry32(a: number) {
  return function () {
    let t = (a += 0x6d2b79f5);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const ParchmentPaper: React.FC<ParchmentPaperProps> = ({
  children,
  className = '',
  padding = 'p-6',
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [dims, setDims] = useState({ width: 0, height: 0 });
  const clipPathId = useId();
  // Store a seed for the PRNG, so the shape is consistent across re-renders
  const seedRef = useRef(Math.floor(Math.random() * 1e9));

  useLayoutEffect(() => {
    const element = containerRef.current;
    if (!element) return;

    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) {
        setDims({ width: entry.contentRect.width, height: entry.contentRect.height });
      }
    });

    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  // Generate wavy border path using deterministic randomness for parchment effect
  const wavyPathData = useMemo(() => {
    const { width, height } = dims;
    if (width === 0 || height === 0) return 'M 0 0 H 0 V 0 H 0 Z';

    // Seeded random ensures consistent border shape across re-renders
    const random = mulberry32(seedRef.current);

    const amp = 6; // Wave amplitude
    const step = 10; // Point spacing
    const points = [];

    // Generate perimeter points with random offset for organic look
    // Top edge
    for (let x = 0; x < width; x += step) {
      points.push(`${x.toFixed(2)},${((random() - 0.5) * amp).toFixed(2)}`);
    }
    points.push(`${width.toFixed(2)},${((random() - 0.5) * amp).toFixed(2)}`);

    // Right edge
    for (let y = 0; y < height; y += step) {
      points.push(`${(width + (random() - 0.5) * amp).toFixed(2)},${y.toFixed(2)}`);
    }
    points.push(`${(width + (random() - 0.5) * amp).toFixed(2)},${height.toFixed(2)}`);

    // Bottom edge
    for (let x = width; x > 0; x -= step) {
      points.push(`${x.toFixed(2)},${(height + (random() - 0.5) * amp).toFixed(2)}`);
    }
    points.push(`0,${(height + (random() - 0.5) * amp).toFixed(2)}`);

    // Left edge
    for (let y = height; y > 0; y -= step) {
      points.push(`${((random() - 0.5) * amp).toFixed(2)},${y.toFixed(2)}`);
    }

    return 'M' + points[0] + ' L' + points.slice(1).join(' L') + ' Z';
  }, [dims]);

  return (
    <div ref={containerRef} className={`group relative ${className}`}>
      {/* Hidden SVG to define the clip path */}
      <svg className="absolute w-0 h-0">
        <defs>
          <clipPath id={clipPathId}>
            <path d={wavyPathData} />
          </clipPath>
        </defs>
      </svg>
      {/* --- Border Layers --- */}
      {/* Layer 1: Solid base color for the border */}
      <div
        className="absolute inset-0"
        style={{
          backgroundColor: '#c7bba8', // An even lighter, more subtle brown
          clipPath: `url(#${clipPathId})`,
        }}
      ></div>
      {/* Layer 2: Noise texture overlay, blended with the base color */}
      <div
        className="absolute inset-0"
        style={{
          backgroundImage: `url('data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 80"><filter id="n"><feTurbulence type="fractalNoise" baseFrequency="0.15" numOctaves="2" stitchTiles="stitch"/></filter><rect width="100%" height="100%" filter="url(%23n)"/></svg>')`,
          clipPath: `url(#${clipPathId})`,
          mixBlendMode: 'multiply',
          opacity: 0.05,
        }}
      ></div>

      {/* --- Content Layer --- */}
      <div
        className="absolute inset-0.5 bg-parchment-100"
        style={{
          backgroundImage: `url('data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 150 150"><filter id="n"><feTurbulence type="fractalNoise" baseFrequency="0.7" numOctaves="5" stitchTiles="stitch"/></filter><rect width="100%" height="100%" filter="url(%23n)" opacity="0.07"/></svg>')`,
          clipPath: `url(#${clipPathId})`,
        }}
      ></div>

      {/* Crisp Content */}
      <div className={`relative ${padding}`}>{children}</div>
    </div>
  );
};

export default ParchmentPaper;
