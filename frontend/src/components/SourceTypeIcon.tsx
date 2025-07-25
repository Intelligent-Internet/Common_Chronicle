import React from 'react';
import { getDataSourceDisplayNames } from '../utils/taskUtils';

interface SourceTypeIconProps {
  sourceType: string | null | undefined;
  className?: string;
  href?: string;
  title?: string;
}

const SourceTypeIcon: React.FC<SourceTypeIconProps> = ({
  sourceType,
  className = 'w-4 h-4',
  href,
  title,
}) => {
  // Get display name using the utility function
  const getDisplayName = (type: string | null | undefined): string => {
    if (!type) return 'Unknown Source';

    // Use the existing utility function to get consistent display names
    const displayNames = getDataSourceDisplayNames(type);
    return displayNames[0] || 'Other Source';
  };

  // Map source types to their display information
  const getSourceTypeInfo = (type: string | null | undefined) => {
    if (!type) {
      return {
        icon: (
          <svg className={className} fill="currentColor" viewBox="0 0 20 20">
            <path
              fillRule="evenodd"
              d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z"
              clipRule="evenodd"
            />
          </svg>
        ),
        label: getDisplayName(type),
        description: 'Unknown data source type',
      };
    }

    // Handle only the 3 official source types from dataSourceOptions
    const normalizedType = type.toLowerCase();

    // Online Wikipedia - globe icon for online sources
    if (normalizedType === 'online_wikipedia') {
      return {
        icon: (
          <svg className={className} fill="currentColor" viewBox="0 0 20 20">
            <path
              fillRule="evenodd"
              d="M10 18a8 8 0 100-16 8 8 0 000 16zM4.332 8.027a6.012 6.012 0 011.912-2.706C6.512 5.73 6.974 6 7.5 6A1.5 1.5 0 019 7.5V8a2 2 0 004 0 2 2 0 011.523-1.943A5.977 5.977 0 0116 10c0 .34-.028.675-.083 1H15a2 2 0 00-2 2v2.197A5.973 5.973 0 0110 16v-2a2 2 0 00-2-2 2 2 0 01-2-2 2 2 0 00-1.668-1.973z"
              clipRule="evenodd"
            />
          </svg>
        ),
        label: getDisplayName(type),
        description: 'Current, live articles from the global encyclopedia',
      };
    }

    // Dataset Wikipedia - database/storage icon for local dataset
    if (normalizedType === 'dataset_wikipedia_en') {
      return {
        icon: (
          <svg className={className} fill="currentColor" viewBox="0 0 20 20">
            <path d="M3 4a1 1 0 011-1h12a1 1 0 011 1v2a1 1 0 01-1 1H4a1 1 0 01-1-1V4zM3 10a1 1 0 011-1h12a1 1 0 011 1v2a1 1 0 01-1 1H4a1 1 0 01-1-1v-2zM3 16a1 1 0 011-1h12a1 1 0 011 1v2a1 1 0 01-1 1H4a1 1 0 01-1-1v-2z" />
          </svg>
        ),
        label: getDisplayName(type),
        description: 'A vast, locally-stored snapshot of English Wikipedia',
      };
    }

    // Online Wikinews - news icon
    if (normalizedType === 'online_wikinews') {
      return {
        icon: (
          <svg className={className} fill="currentColor" viewBox="0 0 20 20">
            <path
              fillRule="evenodd"
              d="M2 5a2 2 0 012-2h8a2 2 0 012 2v10a2 2 0 002 2H4a2 2 0 01-2-2V5zm3 1h6v4H5V6zm6 6H5v2h6v-2z"
              clipRule="evenodd"
            />
            <path d="M15 7h1a2 2 0 012 2v5.5a1.5 1.5 0 01-3 0V9a1 1 0 00-1-1h-1v-1z" />
          </svg>
        ),
        label: getDisplayName(type),
        description: 'Recent and archived news reports',
      };
    }

    // Default for unknown types - should not happen with valid source_type values
    return {
      icon: (
        <svg className={className} fill="currentColor" viewBox="0 0 20 20">
          <path
            fillRule="evenodd"
            d="M3 4a1 1 0 011-1h12a1 1 0 011 1v2a1 1 0 01-1 1H4a1 1 0 01-1-1V4zM3 10a1 1 0 011-1h6a1 1 0 011 1v6a1 1 0 01-1 1H4a1 1 0 01-1-1v-6zM14 9a1 1 0 00-1 1v6a1 1 0 001 1h2a1 1 0 001-1v-6a1 1 0 00-1-1h-2z"
            clipRule="evenodd"
          />
        </svg>
      ),
      label: getDisplayName(type),
      description: `Invalid source type: ${type}`,
    };
  };

  const sourceInfo = getSourceTypeInfo(sourceType);

  // Determine the tooltip content
  const tooltipTitle = title || `Visit source: ${sourceInfo.label}`;
  const showTooltip = title || href;

  const iconContent = (
    <div className="group relative inline-flex items-center">
      <div
        className={`${href ? 'text-pewter hover:text-slate dark:text-mist dark:hover:text-white cursor-pointer' : 'text-pewter dark:text-mist'} transition-colors duration-200`}
      >
        {sourceInfo.icon}
      </div>

      {/* Tooltip */}
      {showTooltip && (
        <div className="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 px-2 py-1 bg-charcoal dark:bg-slate text-white dark:text-white text-xs rounded whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity duration-200 pointer-events-none z-10">
          <div className="font-medium">{sourceInfo.label}</div>
          <div className="text-xs text-gray-300">{title ? title : sourceInfo.description}</div>
          {/* Tooltip arrow */}
          <div className="absolute top-full left-1/2 transform -translate-x-1/2 border-l-4 border-r-4 border-t-4 border-transparent border-t-charcoal dark:border-t-slate"></div>
        </div>
      )}
    </div>
  );

  // If href is provided, wrap in a link
  if (href) {
    return (
      <a href={href} target="_blank" rel="noopener noreferrer" title={tooltipTitle}>
        {iconContent}
      </a>
    );
  }

  return iconContent;
};

export default SourceTypeIcon;
