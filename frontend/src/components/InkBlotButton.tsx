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
        relative font-medium transition-all duration-300 rounded-full
        ${sizeClasses[variant]}
        ${
          isActive
            ? 'bg-transparent border-2 border-sky-blue text-slate dark:text-sky-blue'
            : 'bg-transparent border-2 border-transparent text-slate hover:text-slate dark:text-mist dark:hover:text-sky-blue'
        }
        ${className}
      `}
    >
      {/* Button content */}
      <span className="relative z-10">{children}</span>
    </button>
  );
};

export default InkBlotButton;
