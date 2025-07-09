import React from 'react';

interface InkBlotButtonProps {
  children: React.ReactNode;
  isActive: boolean;
  onClick: () => void;
  className?: string;
  variant?: 'default' | 'year' | 'small';
  title?: string;
}

const InkBlotButton: React.FC<InkBlotButtonProps> = ({
  children,
  isActive,
  onClick,
  className = '',
  variant = 'default',
  title,
}) => {
  // Ancient seal/stamp irregular paths - more organic and hand-drawn feel
  const sealPaths = [
    // Main irregular seal shape with rough edges
    'M10,20 C8,15 12,8 18,6 C25,4 35,5 42,8 C50,12 58,10 65,15 C72,20 75,28 78,35 C80,42 77,50 73,57 C68,65 60,70 52,72 C45,74 38,73 30,70 C22,67 15,62 12,55 C9,48 8,40 10,32 C11,28 9,24 10,20 Z',

    // Alternative rough shape
    'M15,25 C12,18 16,10 22,7 C30,4 38,6 45,9 C52,12 59,15 64,22 C70,29 72,37 70,45 C68,53 63,60 56,65 C49,70 40,72 32,70 C24,68 17,63 13,56 C9,49 8,41 12,34 C14,30 13,27 15,25 Z',

    // Textured background shape
    'M8,30 C6,22 10,12 18,8 C26,4 36,5 44,8 C52,11 60,16 66,24 C72,32 74,41 71,49 C68,57 62,64 54,68 C46,72 37,73 28,70 C19,67 11,61 8,53 C5,45 6,37 8,30 Z',
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
      {/* Ancient seal background when active */}
      {isActive && (
        <div className="absolute inset-0 pointer-events-none overflow-hidden">
          <svg
            width="100%"
            height="100%"
            viewBox="0 0 80 80"
            className="absolute inset-0 -z-10"
            preserveAspectRatio="none"
            style={{
              filter: 'drop-shadow(0 2px 6px rgba(0,0,0,0.2))',
            }}
          >
            {/* Outer glow/blur for aged paper effect */}
            <path
              d={sealPaths[2]}
              fill="rgba(139, 111, 78, 0.2)"
              opacity="0.4"
              transform="scale(1.3)"
              style={{
                filter: 'blur(3px)',
                transformOrigin: '50% 50%',
              }}
            />

            {/* Main seal base */}
            <path d={sealPaths[0]} fill="rgba(160, 130, 98, 0.8)" opacity="0.9" />

            {/* Texture overlay for worn/aged effect */}
            <path
              d={sealPaths[1]}
              fill="rgba(139, 111, 78, 0.7)"
              opacity="0.6"
              transform="scale(0.95) translate(2, 1)"
            />

            {/* Inner highlight areas */}
            <ellipse
              cx="40"
              cy="35"
              rx="8"
              ry="12"
              fill="rgba(197, 157, 95, 0.5)"
              opacity="0.4"
              transform="rotate(-15 40 35)"
            />

            {/* Aged paper texture spots */}
            <circle cx="25" cy="25" r="2" fill="rgba(111, 88, 62, 0.3)" opacity="0.6" />
            <circle cx="55" cy="30" r="1.5" fill="rgba(111, 88, 62, 0.4)" opacity="0.5" />
            <circle cx="35" cy="55" r="1.8" fill="rgba(111, 88, 62, 0.2)" opacity="0.4" />
            <circle cx="50" cy="50" r="1.2" fill="rgba(111, 88, 62, 0.3)" opacity="0.3" />

            {/* Subtle ink bleed effects */}
            <path
              d="M20,40 C18,38 22,35 25,37 C28,39 26,42 23,41 C21,40 20,40 20,40 Z"
              fill="rgba(124, 101, 72, 0.3)"
              opacity="0.4"
            />
            <path
              d="M55,25 C57,23 60,26 58,29 C56,32 53,30 54,27 C55,26 55,25 55,25 Z"
              fill="rgba(124, 101, 72, 0.3)"
              opacity="0.3"
            />
          </svg>
        </div>
      )}

      {/* Hover effect - subtle seal preview */}
      {!isActive && (
        <div className="absolute inset-0 pointer-events-none overflow-hidden opacity-0 hover:opacity-25 transition-opacity duration-300">
          <svg
            width="100%"
            height="100%"
            viewBox="0 0 80 80"
            className="absolute inset-0 -z-10"
            preserveAspectRatio="none"
          >
            <path d={sealPaths[0]} fill="rgba(160, 130, 98, 0.4)" opacity="0.6" />
          </svg>
        </div>
      )}

      {/* Button content */}
      <span className="relative z-10">{children}</span>
    </button>
  );
};

export default InkBlotButton;
