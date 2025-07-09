import React, { useEffect } from 'react';
import { Link } from 'react-router-dom';
import type { ExtendedUserTaskRecord } from '../services/indexedDB.service';
import { getCheckboxStateFromString } from '../utils/timelineUtils'; // Adjusted path
import WavyLine from './WavyLine';
import ParchmentPaper from './ParchmentPaper';

// Helper function to render task date
const renderTaskDate = (task: ExtendedUserTaskRecord): string => {
  const dateStr = task.createdAt;
  if (dateStr) {
    const dateObj = new Date(dateStr);
    if (!isNaN(dateObj.getTime())) {
      return dateObj.toLocaleString([], {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } else {
      console.warn(
        `[TaskListPanel.tsx] Invalid date string for task ${task.id} (createdAt): "${dateStr}". Falling back to default text.`
      );
    }
  }
  return 'Creation time: Processing...';
};

const getStatusStyles = (status: string): string => {
  switch (status) {
    case 'completed':
      return 'bg-sage-100 text-sage-800';
    case 'failed':
      return 'bg-red-100 text-red-800';
    case 'processing':
      return 'bg-blue-100 text-blue-800';
    case 'pending':
      return 'bg-amber-100 text-amber-800';
    default:
      return 'bg-parchment-200 text-scholar-700';
  }
};

interface TaskListPanelProps {
  isOpen: boolean;
  isLoading: boolean;
  tasks: ExtendedUserTaskRecord[];
  viewingTaskId: string | null;
  title?: string;
  onClose: () => void;
  onRefreshTasks: () => void;
}

const TaskListPanel: React.FC<TaskListPanelProps> = ({
  isOpen,
  isLoading,
  tasks,
  viewingTaskId,
  title = 'My Chronicles',
  onClose,
  onRefreshTasks,
}) => {
  // Effect to control body scroll when the panel is open
  useEffect(() => {
    if (isOpen) {
      // When the panel is open, prevent the body from scrolling.
      document.body.classList.add('overflow-hidden');
    }

    // The cleanup function runs when the component unmounts or `isOpen` changes.
    // This ensures the class is always removed when the panel is closed or gone.
    return () => {
      document.body.classList.remove('overflow-hidden');
    };
  }, [isOpen]); // Dependency array ensures this runs only when `isOpen` changes.

  if (!isOpen) {
    return null;
  }

  return (
    <>
      <div
        className="fixed inset-0 bg-scholar-900/60 backdrop-blur-sm z-30 transition-opacity duration-300 ease-in-out"
        onClick={onClose}
        aria-hidden="true"
      ></div>
      <div
        className={`fixed top-0 right-0 h-full w-full max-w-md bg-parchment-50 shadow-2xl z-40 transform transition-transform duration-300 ease-in-out ${
          isOpen ? 'translate-x-0' : 'translate-x-full'
        } p-6 flex flex-col border-l-4 border-parchment-200`}
      >
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-3xl font-serif text-scholar-800">{title}</h2>
          <div className="flex items-center gap-2">
            <button
              onClick={onRefreshTasks}
              disabled={isLoading}
              className="p-2 rounded-full hover:bg-parchment-200/60 focus:outline-none focus:ring-2 focus:ring-scholar-500/50 disabled:opacity-50 disabled:cursor-not-allowed text-scholar-600 hover:text-scholar-800 transition-colors"
              aria-label="Refresh chronicle list"
              title="Refresh chronicle list"
            >
              <svg
                className={`w-5 h-5 ${isLoading ? 'animate-spin' : ''}`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                />
              </svg>
            </button>
            <button
              onClick={onClose}
              className="p-1 rounded-full hover:bg-parchment-200/60 text-scholar-600 hover:text-scholar-800 transition-colors"
              aria-label={`Close ${title} panel`}
            >
              <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>
          </div>
        </div>

        {/* Decorative wavy line separator */}
        <div className="mb-6">
          <WavyLine className="text-parchment-300" />
        </div>

        {isLoading &&
          tasks.length === 0 && ( // Show loading only if there are no tasks to display yet
            <p className="text-scholar-600 italic">Loading chronicles...</p>
          )}
        {!isLoading && tasks.length === 0 && (
          <div className="text-center p-8 bg-parchment-100 border-2 border-dashed border-parchment-300 rounded-lg">
            <p className="font-serif text-scholar-700">No chronicles found in your archive.</p>
            <p className="text-sm text-scholar-500 mt-2">
              Create a new one to begin your research.
            </p>
          </div>
        )}
        {tasks.length > 0 && (
          <ul className="space-y-3 flex-1 overflow-y-auto -mr-2 pr-2">
            {tasks.map((task) => {
              const isActive = viewingTaskId === task.id;
              return (
                <li key={task.id}>
                  <Link
                    to={`/task/${task.id}`}
                    onClick={onClose} // Close panel when a task is clicked
                    className={`block cursor-pointer transition-all duration-150 group ${
                      isActive ? 'scale-105' : 'hover:scale-102'
                    }`}
                  >
                    <ParchmentPaper
                      padding="p-4"
                      className={isActive ? 'ring-2 ring-scholar-400/50' : ''}
                    >
                      <div className="flex justify-between items-center mb-2">
                        <p
                          className={`text-xs font-medium ${
                            isActive ? 'text-scholar-700' : 'text-scholar-500'
                          } group-hover:text-scholar-600`}
                        >
                          {renderTaskDate(task)}
                        </p>
                        <span
                          className={`text-xs px-2 py-0.5 rounded-full font-semibold ${getStatusStyles(
                            task.status
                          )}`}
                        >
                          {task.status.charAt(0).toUpperCase() + task.status.slice(1)}
                        </span>
                      </div>
                      <p
                        className={`text-base font-serif font-semibold truncate ${
                          isActive ? 'text-scholar-900' : 'text-scholar-800'
                        }`}
                        title={task.viewpoint || 'Untitled Chronicle'}
                      >
                        {task.viewpoint || 'Untitled Chronicle'}
                      </p>
                      <p
                        className={`text-xs mt-1 ${
                          isActive ? 'text-scholar-700' : 'text-scholar-600'
                        }`}
                      >
                        Source(s):{' '}
                        {(() => {
                          const pref = task.dataSourcePref;
                          if (!pref) return 'Not specified';
                          if (pref === 'none') return 'None selected';
                          const state = getCheckboxStateFromString(pref);
                          const displayParts: string[] = [];
                          if (state.online_wikipedia) displayParts.push('Wikipedia');
                          if (state.online_wikinews) displayParts.push('Wikinews');
                          if (state.dataset_wikipedia_en) displayParts.push('Dataset');
                          if (displayParts.length === 0) return `Invalid sources (${pref})`;
                          return displayParts.join(', ');
                        })()}
                      </p>
                      {task.status === 'failed' && task.error?.message && (
                        <p
                          className="mt-2 text-xs text-red-600 truncate bg-red-50 p-2 rounded-lg border border-red-200/50"
                          title={task.error.message}
                        >
                          <span className="font-semibold">Error:</span> {task.error.message}
                        </p>
                      )}
                    </ParchmentPaper>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </>
  );
};

export default TaskListPanel;
