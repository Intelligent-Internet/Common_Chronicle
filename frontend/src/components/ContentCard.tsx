import React from 'react';

interface ContentCardProps {
  children: React.ReactNode;
  className?: string;
  padding?: string;
}

/**
 * A simple styled container card that aligns with the new brand guidelines.
 * Replaces the old ParchmentPaper component's visual style.
 */
const ContentCard: React.FC<ContentCardProps> = ({ children, className = '', padding = 'p-6' }) => {
  // This component now renders a simple div with styles from the new brand guidelines,
  // matching the .content-card class defined in index.css.
  return (
    <div
      className={`bg-white border-2 border-mist rounded-2xl shadow-sm hover:shadow-md transition-shadow duration-200 dark:bg-charcoal dark:border-sky-blue ${className} ${padding}`}
    >
      {children}
    </div>
  );
};

export default ContentCard;
