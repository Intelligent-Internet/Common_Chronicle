import React from 'react';

interface InkBlotButtonProps {
  children: React.ReactNode;
  isActive: boolean;
  onClick: () => void;
  className?: string;
  variant?: 'default' | 'year' | 'small';
  title?: string;
}

const InkBlotButtonSimple: React.FC<InkBlotButtonProps> = ({
  children,
  isActive,
  onClick,
  className = '',
  variant = 'default',
  title,
}) => {
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
        ${
          isActive
            ? 'text-white z-10 ink-blot-active'
            : 'text-scholar-600 hover:text-scholar-800 ink-blot-hover'
        }
        ${className}
      `}
      style={{
        // Hand-drawn irregular border effect using CSS
        border: isActive ? '2px solid rgba(160, 130, 98, 0.8)' : 'none',
        borderRadius: isActive ? '65% 35% 70% 30% / 30% 75% 25% 70%' : '4px',
        background: isActive
          ? 'radial-gradient(ellipse at 30% 40%, rgba(197, 157, 95, 0.9) 0%, rgba(160, 130, 98, 0.8) 45%, rgba(139, 111, 78, 0.7) 100%)'
          : 'transparent',
        boxShadow: isActive
          ? 'inset 0 2px 4px rgba(0,0,0,0.1), 0 2px 8px rgba(139, 111, 78, 0.3)'
          : 'none',
        transform: isActive ? 'rotate(-0.5deg)' : 'none',
        // Add subtle animation
        animation: isActive ? 'ink-settle 0.3s ease-out' : 'none',
      }}
    >
      {/* Add some CSS-based texture spots */}
      {isActive && (
        <>
          <div
            className="absolute w-1 h-1 bg-scholar-700 rounded-full opacity-20"
            style={{ top: '25%', left: '20%' }}
          />
          <div
            className="absolute w-1.5 h-1.5 bg-scholar-700 rounded-full opacity-15"
            style={{ top: '60%', right: '25%' }}
          />
          <div
            className="absolute w-0.5 h-0.5 bg-scholar-700 rounded-full opacity-25"
            style={{ top: '80%', left: '70%' }}
          />
        </>
      )}

      <span className="relative z-10">{children}</span>
    </button>
  );
};

export default InkBlotButtonSimple;
