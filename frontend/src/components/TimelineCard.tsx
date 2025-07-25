import React from 'react';
import { Link } from 'react-router-dom';
import type { ExtendedUserTaskRecord } from '../services/indexedDB.service';
import { getTaskTypeDisplayName, getDataSourceDisplayNames } from '../utils/taskUtils';

import ContentCard from './ContentCard';
import SourceTypeIcon from './SourceTypeIcon';

const TimelineCard: React.FC<{ task: ExtendedUserTaskRecord }> = ({ task }) => {
  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString([], {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    });
  };

  const statusInfo = {
    text: task.status.charAt(0).toUpperCase() + task.status.slice(1),
    className:
      task.status === 'completed'
        ? 'text-slate dark:text-sky-blue'
        : task.status === 'failed'
          ? 'text-red-700 dark:text-red-400'
          : 'text-slate dark:text-mist',
  };

  const sourceText = getDataSourceDisplayNames(task.dataSourcePref).join(', ');

  // Get primary source type for icon display based on dataSourcePref
  const getPrimarySourceType = (dataSourcePref: string | null | undefined) => {
    if (!dataSourcePref || dataSourcePref === 'default') {
      return 'dataset_wikipedia_en';
    }

    // Handle comma-separated multiple sources - return the first one
    const sources = dataSourcePref.split(',').map((s) => s.trim());
    return sources[0] || 'dataset_wikipedia_en';
  };

  const primarySourceType = getPrimarySourceType(task.dataSourcePref);

  const statusDisplay =
    task.status === 'completed'
      ? 'Chronicle Complete'
      : task.status === 'processing'
        ? 'In Progress'
        : task.status === 'failed'
          ? 'Processing Failed'
          : 'Pending Review';

  return (
    <Link to={`/task/${task.id}`} target="_blank" rel="noopener noreferrer" className="block group">
      <ContentCard padding="p-0" className="h-full flex flex-col">
        <div className="p-6 flex-grow">
          <div className="flex items-start justify-between mb-4">
            <h3 className="text-xl font-sans font-bold text-charcoal group-hover:text-slate transition-colors duration-300 line-clamp-2 leading-tight dark:text-white dark:group-hover:text-sky-blue">
              {task.viewpoint || 'Untitled Chronicle'}
            </h3>
          </div>

          <div className="space-y-3 text-sm text-slate dark:text-mist">
            <div className="flex items-center">
              <svg
                className="w-4 h-4 mr-2 text-pewter dark:text-mist"
                fill="currentColor"
                viewBox="0 0 20 20"
              >
                <path
                  fillRule="evenodd"
                  d="M6 2a1 1 0 00-1 1v1H4a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V6a2 2 0 00-2-2h-1V3a1 1 0 10-2 0v1H7V3a1 1 0 00-1-1zm0 5a1 1 0 000 2h8a1 1 0 100-2H6z"
                  clipRule="evenodd"
                />
              </svg>
              <span className="font-medium">Created:</span>
              <span className="ml-2">{formatDate(task.createdAt)}</span>
            </div>
            <div className="flex items-center">
              <SourceTypeIcon sourceType={primarySourceType} className="w-4 h-4 mr-2" />
              <span className="font-medium">Source:</span>
              <span className="ml-2">{sourceText}</span>
            </div>
            <div className="flex items-center">
              <svg
                className="w-4 h-4 mr-2 text-pewter dark:text-mist"
                fill="currentColor"
                viewBox="0 0 20 20"
              >
                <path
                  fillRule="evenodd"
                  d="M3 4a1 1 0 011-1h12a1 1 0 011 1v2a1 1 0 01-1 1H4a1 1 0 01-1-1V4zM3 10a1 1 0 011-1h6a1 1 0 011 1v6a1 1 0 01-1 1H4a1 1 0 01-1-1v-6zM14 9a1 1 0 00-1 1v6a1 1 0 001 1h2a1 1 0 001-1v-6a1 1 0 00-1-1h-2z"
                  clipRule="evenodd"
                />
              </svg>
              <span className="font-medium">Type:</span>
              <span className="ml-2">{getTaskTypeDisplayName(task.taskType)}</span>
            </div>
            <div className="flex items-center">
              <svg
                className="w-4 h-4 mr-2 text-pewter dark:text-mist"
                fill="currentColor"
                viewBox="0 0 20 20"
              >
                <path
                  fillRule="evenodd"
                  d="M10 18a8 8 0 100-16 8 8 0 000 16zm.707-10.293a1 1 0 00-1.414-1.414l-3 3a1 1 0 001.414 1.414L9 9.414V12a1 1 0 102 0V9.414l1.293 1.293a1 1 0 001.414-1.414l-3-3z"
                  clipRule="evenodd"
                />
              </svg>
              <span className="font-medium">Status:</span>
              <span className={`ml-2 font-semibold ${statusInfo.className}`}>{statusDisplay}</span>
            </div>
          </div>

          {/* Collapsible section */}
          <div className="overflow-hidden max-h-0 group-hover:max-h-40 transition-[max-height] duration-500 ease-in-out">
            <hr className="border-t-2 border-dashed border-mist/50 my-3 dark:border-mist/50" />
            <div className="space-y-2 text-sm text-slate dark:text-mist">
              <div className="flex items-center">
                <svg
                  className="w-4 h-4 mr-2 text-pewter dark:text-mist"
                  fill="currentColor"
                  viewBox="0 0 20 20"
                >
                  <path
                    fillRule="evenodd"
                    d="M5 4a1 1 0 00-1 1v10a1 1 0 001 1h10a1 1 0 001-1V5a1 1 0 00-1-1H5zm9 3H6v1h8V7zM6 9h8v1H6V9zm8 2H6v1h8v-1z"
                    clipRule="evenodd"
                  />
                </svg>
                <span className="font-medium">Last Updated:</span>
                <span className="ml-2">{formatDate(task.updatedAt)}</span>
              </div>
              <div className="flex items-center">
                <svg
                  className="w-4 h-4 mr-2 text-pewter dark:text-mist"
                  fill="currentColor"
                  viewBox="0 0 20 20"
                >
                  <path d="M10 2a1 1 0 00-1 1v1a1 1 0 002 0V3a1 1 0 00-1-1zM4 5a1 1 0 00-1 1v1a1 1 0 002 0V6a1 1 0 00-1-1zm12 0a1 1 0 00-1 1v1a1 1 0 002 0V6a1 1 0 00-1-1zM10 18a1 1 0 001-1v-1a1 1 0 00-2 0v1a1 1 0 001 1zM4 14a1 1 0 00-1 1v1a1 1 0 002 0v-1a1 1 0 00-1-1zm12 0a1 1 0 00-1 1v1a1 1 0 002 0v-1a1 1 0 00-1-1z" />
                  <path
                    fillRule="evenodd"
                    d="M10 4a6 6 0 100 12 6 6 0 000-12zM5.75 9a.75.75 0 00.75.75h6.5a.75.75 0 000-1.5h-6.5a.75.75 0 00-.75.75z"
                    clipRule="evenodd"
                  />
                </svg>
                <span className="font-medium">Manuscript ID:</span>
                <span className="ml-2 font-mono text-xs tracking-wider">{task.id}</span>
              </div>
            </div>
          </div>

          <div className="absolute bottom-4 right-5 opacity-0 group-hover:opacity-100 transition-opacity duration-300">
            <div className="flex items-center text-slate dark:text-mist">
              <span className="text-sm font-semibold">Explore</span>
              <svg className="w-5 h-5 ml-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M17 8l4 4m0 0l-4 4m4-4H3"
                />
              </svg>
            </div>
          </div>
        </div>
      </ContentCard>
    </Link>
  );
};

export default TimelineCard;
