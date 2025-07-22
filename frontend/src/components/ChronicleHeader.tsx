import React, { useState } from 'react';
import type { TaskResultResponse, TimelineEvent } from '../types';
import { getTaskTypeDisplayName, getDataSourceDisplayNames } from '../utils/taskUtils';
import FilterPanel from './FilterPanel';
import {
  GlobeAltIcon,
  LockClosedIcon,
  UserCircleIcon,
  ChevronDownIcon,
  AdjustmentsHorizontalIcon,
} from '@heroicons/react/24/outline';

interface ChronicleHeaderProps {
  task: TaskResultResponse | null;
  onExport: (format: 'json' | 'markdown') => void;
  onShareToggle: (isPublic: boolean) => void;
  isUpdatingShare: boolean;
  timelineYears: string[];
  activeYear: string | null;
  onYearSelect: (year: string) => void;
  isQuickNavVisible: boolean;
  totalEventsCount: number;
  // Filter-related props
  events: TimelineEvent[];
  uniqueKeywords: string[];
  keywordToTitleMap: Map<string, string>;
  currentFilters: { selectedKeyword: string | null; minRelevanceScore: number };
  onFiltersChange: (filters: { selectedKeyword: string | null; minRelevanceScore: number }) => void;
}

const ChronicleHeader: React.FC<ChronicleHeaderProps> = ({
  task,
  onExport,
  onShareToggle,
  isUpdatingShare,
  timelineYears,
  activeYear,
  onYearSelect,
  isQuickNavVisible,
  totalEventsCount,
  events,
  uniqueKeywords,
  keywordToTitleMap,
  currentFilters,
  onFiltersChange,
}) => {
  const [isExportDropdownOpen, setIsExportDropdownOpen] = useState(false);
  const [isFilterPanelOpen, setIsFilterPanelOpen] = useState(false);

  // Check if any filters are active
  const hasActiveFilters =
    currentFilters.selectedKeyword !== null || currentFilters.minRelevanceScore > 0;

  if (!task) {
    return (
      <div className="text-center py-20">
        <h1 className="text-4xl font-serif text-scholar-800">Loading Chronicle...</h1>
      </div>
    );
  }

  const topicText = task.topic_text || 'Untitled Chronicle';
  const status = task.status || 'unknown';
  const dataSourcePref = task.viewpoint_details?.viewpoint?.data_source_preference;

  return (
    <header className="space-y-12 mb-16 max-w-4xl mx-auto px-4">
      {/* Page Title */}
      <div className="text-center relative">
        <div className="absolute top-1/2 left-0 w-full h-px bg-parchment-300 -z-10"></div>
        <div className="absolute top-1/2 right-0 w-full h-px bg-parchment-300 -z-10"></div>
        <div className="inline-block relative px-6 bg-parchment-50">
          <svg
            className="absolute -top-3 left-1/2 -translate-x-1/2 w-12 h-6 text-parchment-400"
            fill="currentColor"
            viewBox="0 0 50 25"
          >
            <path
              d="M25,0 C15,0 10,10 0,10 L0,15 C10,15 15,25 25,25 C35,25 40,15 50,15 L50,10 C40,10 35,0 25,0 Z"
              transform="scale(1, 0.6)"
            />
          </svg>
          <h1 className="text-5xl font-serif text-scholar-800 py-4" title={topicText}>
            {topicText}
          </h1>
          <svg
            className="absolute -bottom-3 left-1/2 -translate-x-1/2 w-12 h-6 text-parchment-400"
            fill="currentColor"
            viewBox="0 0 50 25"
          >
            <path
              d="M25,0 C15,0 10,10 0,10 L0,15 C10,15 15,25 25,25 C35,25 40,15 50,15 L50,10 C40,10 35,0 25,0 Z"
              transform="scale(1, -0.6)"
            />
          </svg>
        </div>
        <p className="mt-4 text-lg text-scholar-600 italic">
          "Reviewing the chronicles of scholarly research"
        </p>
      </div>

      {/* Simplified Control Bar */}
      <section className="mt-12">
        <div className="flex justify-between items-start gap-6">
          {/* Left: Task Info - Fixed Two-Row Layout */}
          <div className="flex flex-col gap-3 min-w-0 flex-1">
            {/* First Row: Core Info */}
            <div className="flex items-center gap-6 flex-wrap">
              {/* Owner Info */}
              {task.owner?.username && (
                <div
                  className="flex items-baseline gap-2 text-sm text-scholar-600"
                  title={`Owned by ${task.owner.username}`}
                >
                  <UserCircleIcon className="w-4 h-4" />
                  <span className="font-medium">{task.owner.username}</span>
                </div>
              )}
              {/* Task Type */}
              <div className="flex items-baseline gap-2">
                <span className="font-medium text-scholar-600 flex-shrink-0 text-sm">Type:</span>
                <span className="px-2.5 py-0.5 text-scholar-700 border border-parchment-300 rounded-md text-xs">
                  {getTaskTypeDisplayName(task.task_type)}
                </span>
              </div>
              {/* Status */}
              <div className="flex items-baseline gap-2">
                <span className="font-medium text-scholar-600 flex-shrink-0 text-sm">Status:</span>
                <span
                  className={`px-2.5 py-0.5 rounded-md text-xs font-medium border ${
                    status === 'completed'
                      ? 'bg-sage-100 text-sage-800 border-sage-300'
                      : status === 'processing' || status === 'pending'
                        ? 'bg-parchment-100 text-parchment-800 border-parchment-400'
                        : status === 'failed'
                          ? 'bg-red-100 text-red-800 border-red-300'
                          : 'bg-scholar-100 text-scholar-800 border-scholar-300'
                  }`}
                >
                  {status}
                </span>
              </div>
            </div>

            {/* Second Row: Data Sources */}
            {dataSourcePref && (
              <div className="flex items-baseline gap-2">
                <span className="font-medium text-scholar-600 flex-shrink-0 text-sm">
                  Source(s):
                </span>
                <div className="flex flex-wrap gap-1.5">
                  {getDataSourceDisplayNames(dataSourcePref).map((source, index) => (
                    <span
                      key={index}
                      className="px-2.5 py-0.5 text-scholar-700 border border-parchment-300 rounded-md text-xs"
                    >
                      {source}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Right: Operations */}
          <div className="flex-shrink-0 flex items-center gap-2 mt-0.5">
            {/* Share Button - only for owners */}
            {task.owner?.id && (
              <button
                onClick={() => onShareToggle(!task.is_public)}
                disabled={isUpdatingShare}
                className="btn btn-secondary-outline text-sm flex items-center justify-center gap-2"
                title={task.is_public ? 'Make Private' : 'Make Public'}
              >
                {task.is_public ? (
                  <GlobeAltIcon className="w-4 h-4" />
                ) : (
                  <LockClosedIcon className="w-4 h-4" />
                )}
                <span>
                  {isUpdatingShare ? 'Updating...' : task.is_public ? 'Public' : 'Private'}
                </span>
              </button>
            )}

            {/* Filters Button */}
            <button
              onClick={() => setIsFilterPanelOpen(true)}
              className={`btn text-sm flex items-center justify-center gap-2 ${
                hasActiveFilters ? 'btn-secondary' : 'btn-secondary-outline'
              }`}
              title="Filters"
            >
              <AdjustmentsHorizontalIcon className="w-4 h-4" />
              Filters
              {hasActiveFilters && (
                <span className="ml-1 px-1.5 py-0.5 text-xs bg-scholar-600 text-white rounded-full">
                  {
                    [currentFilters.selectedKeyword, currentFilters.minRelevanceScore > 0].filter(
                      Boolean
                    ).length
                  }
                </span>
              )}
            </button>

            <div className="relative">
              <button
                onClick={() => setIsExportDropdownOpen(!isExportDropdownOpen)}
                className="btn btn-secondary-outline text-sm flex items-center justify-center gap-2"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4"
                  />
                </svg>
                Export
              </button>
              {isExportDropdownOpen && (
                <div className="absolute right-0 mt-2 w-48 rounded-md shadow-lg bg-white ring-1 ring-black ring-opacity-5 z-50">
                  <div className="py-1">
                    <a
                      onClick={() => {
                        onExport('json');
                        setIsExportDropdownOpen(false);
                      }}
                      className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 cursor-pointer"
                    >
                      Export as JSON
                    </a>
                    <a
                      onClick={() => {
                        onExport('markdown');
                        setIsExportDropdownOpen(false);
                      }}
                      className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 cursor-pointer"
                    >
                      Export as Markdown
                    </a>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Filter Panel */}
        <FilterPanel
          events={events}
          keywordToTitleMap={keywordToTitleMap}
          uniqueKeywords={uniqueKeywords}
          isOpen={isFilterPanelOpen}
          onClose={() => setIsFilterPanelOpen(false)}
          onApplyFilters={onFiltersChange}
          currentFilters={currentFilters}
        />
      </section>

      {/* Quick Navigation Bar - shown on scroll */}
      {isQuickNavVisible && (
        <div className="sticky top-0 bg-stone-50/80 backdrop-blur-sm z-20 py-3 shadow-md -mx-8 px-8">
          <div className="max-w-4xl mx-auto flex items-center justify-between">
            <div className="flex-1">
              <h2 className="text-lg font-semibold truncate" title={topicText}>
                {topicText}
              </h2>
              <p className="text-sm text-stone-500">{totalEventsCount} events found</p>
            </div>
            <div className="flex items-center gap-4">
              <span className="text-sm font-medium">Jump to year:</span>
              <div className="relative">
                <select
                  value={activeYear || ''}
                  onChange={(e) => onYearSelect(e.target.value)}
                  className="pl-3 pr-8 py-1.5 border border-stone-300 rounded-md shadow-sm bg-white text-sm focus:outline-none focus:ring-2 focus:ring-rose-500 appearance-none"
                >
                  <option value="" disabled>
                    Select year...
                  </option>
                  {timelineYears.map((year) => (
                    <option key={year} value={year}>
                      {year}
                    </option>
                  ))}
                </select>
                <ChevronDownIcon className="w-5 h-5 text-stone-400 absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none" />
              </div>
            </div>
          </div>
        </div>
      )}
    </header>
  );
};

export default ChronicleHeader;
