import React from 'react';
import { Link } from 'react-router-dom';
import type { ExtendedUserTaskRecord } from '../services/indexedDB.service';

import ParchmentPaper from './ParchmentPaper';

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
        ? 'text-sage-700'
        : task.status === 'failed'
          ? 'text-red-700'
          : 'text-scholar-600',
  };

  const sourceText = (() => {
    const pref = task.dataSourcePref;
    if (!pref || pref === 'none') return 'Source Not Specified';
    return pref;
  })();

  const statusDisplay =
    task.status === 'completed'
      ? 'Chronicle Complete'
      : task.status === 'processing'
        ? 'In Progress'
        : task.status === 'failed'
          ? 'Processing Failed'
          : 'Pending Review';

  return (
    <Link to={`/task/${task.id}`} target="_blank" rel="noopener noreferrer" className="block">
      <ParchmentPaper padding="p-0">
        <div className="p-6">
          <div className="flex items-start justify-between mb-4">
            <h3 className="text-xl font-serif font-bold text-scholar-800 group-hover:text-scholar-900 transition-colors duration-300 line-clamp-2 leading-tight">
              {task.viewpoint || 'Untitled Chronicle'}
            </h3>
          </div>

          <div className="space-y-3 text-sm text-scholar-700">
            <div className="flex items-center">
              <svg
                className="w-4 h-4 mr-2 text-scholar-500"
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
              <svg
                className="w-4 h-4 mr-2 text-scholar-500"
                fill="currentColor"
                viewBox="0 0 20 20"
              >
                <path d="M9 2a1 1 0 000 2h2a1 1 0 100-2H9z" />
                <path
                  fillRule="evenodd"
                  d="M4 5a2 2 0 012-2 3 3 0 003 3h2a3 3 0 003-3 2 2 0 012 2v11a2 2 0 01-2 2H6a2 2 0 01-2-2V5zm3 4a1 1 0 000 2h.01a1 1 0 100-2H7zm3 0a1 1 0 000 2h.01a1 1 0 100-2H10zm3 0a1 1 0 000 2h.01a1 1 0 100-2H13z"
                  clipRule="evenodd"
                />
              </svg>
              <span className="font-medium">Source:</span>
              <span className="ml-2">{sourceText}</span>
            </div>
            <div className="flex items-center">
              <svg
                className="w-4 h-4 mr-2 text-scholar-500"
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
            <hr className="border-t-2 border-dashed border-parchment-300/50 my-3" />
            <div className="space-y-2 text-sm text-scholar-600">
              <div className="flex items-center">
                <svg
                  className="w-4 h-4 mr-2 text-scholar-500"
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
                  className="w-4 h-4 mr-2 text-scholar-500"
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
            <div className="flex items-center text-scholar-600">
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
      </ParchmentPaper>
    </Link>
  );
};

export default TimelineCard;
