import React from 'react';

interface InkBlotButtonProps {
  children: React.ReactNode;
  isActive: boolean;
  onClick: () => void;
  className?: string;
  variant?: 'default' | 'year' | 'small';
  title?: string;
}

const InkBlotButtonAlt: React.FC<InkBlotButtonProps> = ({
  children,
  isActive,
  onClick,
  className = '',
  variant = 'default',
  title,
}) => {
  // Quill ink blot paths - irregular splatters and bleeds
  const inkBlotPaths = [
    // Main ink blot with organic splatters
    'M25,15 C30,10 40,8 50,12 C60,16 65,20 70,30 C75,40 72,50 65,58 C58,66 48,70 38,68 C28,66 20,60 15,50 C10,40 12,30 18,22 C22,18 24,16 25,15 Z',

    // Secondary splatter
    'M20,25 C25,20 35,18 45,22 C55,26 60,35 58,45 C56,55 50,62 40,65 C30,68 18,65 12,55 C6,45 8,35 15,28 C18,26 19,25 20,25 Z',

    // Ink bleeding effect
    'M30,20 C35,15 45,17 55,22 C65,27 68,37 65,47 C62,57 55,65 45,67 C35,69 25,66 20,56 C15,46 18,36 25,28 C28,24 29,21 30,20 Z',
  ];

  // Random ink splatter dots - positioned dynamically
  const splatters = [
    { x: 15, y: 35, r: 1.5, opacity: 0.4 },
    { x: 70, y: 25, r: 0.8, opacity: 0.3 },
    { x: 80, y: 45, r: 1.2, opacity: 0.5 },
    { x: 10, y: 60, r: 0.6, opacity: 0.3 },
    { x: 60, y: 65, r: 1.0, opacity: 0.4 },
    { x: 85, y: 60, r: 0.4, opacity: 0.2 },
  ];

  const sizeClasses = {
    default: 'px-4 py-2 text-sm',
    year: 'px-3 py-2 text-sm',
    small: 'px-2 py-1 text-xs',
  };

  return (
    <button
      onClick={onClick}
      title={title}
      className={`
        relative font-medium transition-all duration-300
        ${sizeClasses[variant]}
        ${isActive ? 'text-white z-10' : 'text-scholar-600 hover:text-scholar-800'}
        ${className}
      `}
    >
      {/* Ink blot background when active */}
      {isActive && (
        <div className="absolute inset-0 pointer-events-none overflow-hidden">
          <svg
            width="100%"
            height="100%"
            viewBox="0 0 100 80"
            className="absolute inset-0 -z-10"
            preserveAspectRatio="none"
            style={{
              filter: 'drop-shadow(0 1px 3px rgba(0,0,0,0.3))',
            }}
          >
            {/* Background ink bleeding effect */}
            <path
              d={inkBlotPaths[2]}
              fill="rgba(139, 111, 78, 0.15)"
              opacity="0.6"
              transform="scale(1.4)"
              style={{
                filter: 'blur(4px)',
                transformOrigin: '50% 50%',
              }}
            />

            {/* Main ink blot */}
            <path d={inkBlotPaths[0]} fill="rgba(160, 130, 98, 0.9)" opacity="0.85" />

            {/* Secondary blot for texture */}
            <path
              d={inkBlotPaths[1]}
              fill="rgba(139, 111, 78, 0.8)"
              opacity="0.7"
              transform="scale(0.9) translate(5, 3)"
            />

            {/* Random ink splatters */}
            {splatters.map((splatter, index) => (
              <circle
                key={index}
                cx={splatter.x}
                cy={splatter.y}
                r={splatter.r}
                fill="rgba(124, 101, 72, 0.6)"
                opacity={splatter.opacity}
              />
            ))}

            {/* Ink drip effects */}
            <path
              d="M45,65 C47,70 48,75 46,78 C44,75 43,70 45,65 Z"
              fill="rgba(139, 111, 78, 0.5)"
              opacity="0.4"
            />
            <path
              d="M55,68 C56,72 57,76 55,78 C54,76 53,72 55,68 Z"
              fill="rgba(139, 111, 78, 0.4)"
              opacity="0.3"
            />

            {/* Feathered edges for organic feel */}
            <path
              d="M35,20 C32,18 30,22 33,24 C36,26 38,23 35,20 Z"
              fill="rgba(160, 130, 98, 0.3)"
              opacity="0.5"
            />
            <path
              d="M65,35 C68,33 70,37 67,39 C64,41 62,38 65,35 Z"
              fill="rgba(160, 130, 98, 0.3)"
              opacity="0.4"
            />
          </svg>
        </div>
      )}

      {/* Hover effect - subtle ink preview */}
      {!isActive && (
        <div className="absolute inset-0 pointer-events-none overflow-hidden opacity-0 hover:opacity-30 transition-opacity duration-300">
          <svg
            width="100%"
            height="100%"
            viewBox="0 0 100 80"
            className="absolute inset-0 -z-10"
            preserveAspectRatio="none"
          >
            <path d={inkBlotPaths[0]} fill="rgba(160, 130, 98, 0.3)" opacity="0.6" />
            {/* Light splatters on hover */}
            {splatters.slice(0, 3).map((splatter, index) => (
              <circle
                key={index}
                cx={splatter.x}
                cy={splatter.y}
                r={splatter.r * 0.8}
                fill="rgba(160, 130, 98, 0.2)"
                opacity={splatter.opacity * 0.5}
              />
            ))}
          </svg>
        </div>
      )}

      {/* Button content */}
      <span className="relative z-10">{children}</span>
    </button>
  );
};

export default InkBlotButtonAlt;
