import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useParams, Link } from 'react-router-dom';
import { getTaskResult, getTimelineUpdatesWS, updateTaskSharing } from '../services/api';
import TimelineDisplay from '../components/TimelineDisplay';
import ProgressDisplay from '../components/ProgressDisplay';
import ChronicleHeader from '../components/ChronicleHeader';

import { exportEventsAsJson, exportEventsAsMarkdown } from '../utils/exportUtils';
import WavyLine from '../components/WavyLine';

import type {
  TimelineEvent,
  WebSocketStatusMessage,
  TimelineWebSocketCallbacks,
  TaskResultResponse,
} from '../types';

import { getTaskResultFromCache, cacheTaskResults } from '../services/indexedDB.service';
import { getUniqueYearsForNavigation } from '../utils/timelineUtils';

interface WebSocketControls {
  close: () => void;
  getSocket: () => WebSocket | null;
}

function TaskPage() {
  const { taskId } = useParams<{ taskId: string }>();
  const [task, setTask] = useState<TaskResultResponse | null>(null);
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedKeyword, setSelectedKeyword] = useState<string | null>(null);
  const [expandedSources, setExpandedSources] = useState<Record<string, boolean>>({});
  const [isQuickNavVisible, setIsQuickNavVisible] = useState(false);
  const [activeYear, setActiveYear] = useState<string | null>(null);
  const chronicleHeaderRef = useRef<HTMLDivElement>(null);

  const sourceFilterData = useMemo(() => {
    const sourceCounts = new Map<string, number>();
    const sourceTitleMap = new Map<string, string>();

    events.forEach((event) => {
      const uniqueSourcesForEvent = new Set<string>();
      event.sources.forEach((source) => {
        if (source.source_page_title) {
          uniqueSourcesForEvent.add(source.source_page_title);
        }
      });
      uniqueSourcesForEvent.forEach((title) => {
        sourceCounts.set(title, (sourceCounts.get(title) || 0) + 1);
        if (!sourceTitleMap.has(title)) {
          sourceTitleMap.set(title, title);
        }
      });
    });

    const uniqueSources = Array.from(sourceCounts.keys()).sort((a, b) => {
      // Sort by count descending, then alphabetically
      const countA = sourceCounts.get(a) || 0;
      const countB = sourceCounts.get(b) || 0;
      if (countA !== countB) {
        return countB - countA;
      }
      return a.localeCompare(b);
    });

    return {
      counts: sourceCounts,
      titles: sourceTitleMap,
      keywords: uniqueSources,
    };
  }, [events]);

  const filteredEvents = useMemo(() => {
    if (!selectedKeyword) {
      return events;
    }
    return events.filter((event) =>
      event.sources.some((source) => source.source_page_title === selectedKeyword)
    );
  }, [events, selectedKeyword]);

  // WebSocket related state for dynamic tasks
  const [progressMessages, setProgressMessages] = useState<WebSocketStatusMessage[]>([]);
  const [currentWebSocket, setCurrentWebSocket] = useState<WebSocketControls | null>(null);
  const [latestProgressMessage, setLatestProgressMessage] = useState<string | null>(null);
  const [isUpdatingShare, setIsUpdatingShare] = useState(false);

  const progressMessagesRef = useRef<WebSocketStatusMessage[]>(progressMessages);

  useEffect(() => {
    progressMessagesRef.current = progressMessages;
  }, [progressMessages]);

  // Utility function to truncate long text for page title
  const truncateTitle = (text: string, maxLength: number = 50): string => {
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength).trim() + '...';
  };

  // Update page title when task topic_text is available
  useEffect(() => {
    if (task?.topic_text) {
      const truncatedTitle = truncateTitle(task.topic_text);
      document.title = `Common Chronicle - ${truncatedTitle}`;
    } else {
      document.title = 'Common Chronicle - Chronicle Archive';
    }
  }, [task?.topic_text]);

  const timelineYears = useMemo(() => {
    if (!task?.viewpoint_details?.timeline_events) {
      return [];
    }

    // Use the new function that properly handles BCE/CE dates and chronological sorting
    return getUniqueYearsForNavigation(task.viewpoint_details.timeline_events);
  }, [task?.viewpoint_details?.timeline_events]);

  // Scroll-based navigation: Show/hide quick nav and track active year
  useEffect(() => {
    const handleScroll = () => {
      // Toggle quick nav visibility based on header position
      if (chronicleHeaderRef.current) {
        const headerBottom = chronicleHeaderRef.current.getBoundingClientRect().bottom;
        setIsQuickNavVisible(headerBottom < 0);
      }

      // Dynamic header offset calculation accounts for changing UI state
      const baseHeaderHeight = 80;
      const quickNavHeight = 64;
      const headerOffset = isQuickNavVisible ? baseHeaderHeight + quickNavHeight : baseHeaderHeight;

      // Find the year section closest to the top of the visible viewport
      let bestCandidate: string | null = null;
      let smallestDistance = Infinity;

      for (const year of timelineYears) {
        const element = document.getElementById(`year-${year}`);
        if (element) {
          const rect = element.getBoundingClientRect();
          // Only consider visible elements
          if (rect.top < window.innerHeight && rect.bottom > 0) {
            const distance = Math.abs(rect.top - (headerOffset + 50));
            if (distance < smallestDistance) {
              smallestDistance = distance;
              bestCandidate = year;
            }
          }
        }
      }
      setActiveYear(bestCandidate);
    };

    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, [timelineYears, isQuickNavVisible]);

  // WebSocket cleanup: Prevent memory leaks and dangling connections
  useEffect(() => {
    return () => {
      if (currentWebSocket) {
        console.log('[TaskPage.tsx] Cleaning up WebSocket connection on unmount.');
        currentWebSocket.close();
        setCurrentWebSocket(null);
      }
    };
  }, [currentWebSocket]);

  // Cache-first data fetching with WebSocket fallback for incomplete tasks
  useEffect(() => {
    let isActive = true; // Prevent state updates after unmount
    let websocketConnection: WebSocketControls | null = null;

    async function fetchTaskData() {
      if (!taskId) {
        setError('Invalid task ID');
        setLoading(false);
        return;
      }

      try {
        setLoading(true);
        setError(null);

        console.log(`[TaskPage.tsx] Fetching task data for ID: ${taskId}`);

        // Cache-first strategy: Load from cache for immediate rendering
        let cachedData: TaskResultResponse | null = null;
        try {
          cachedData = await getTaskResultFromCache(taskId);
          if (cachedData && isActive) {
            console.log(`[TaskPage.tsx] Found cached results for task ${taskId}`);
            setTask(cachedData);
            setEvents(cachedData.viewpoint_details?.timeline_events || []);
            setProgressMessages(cachedData.progress_messages || []);
          }
        } catch (cacheError) {
          console.error('[TaskPage.tsx] Error fetching cached data:', cacheError);
        }

        // Fetch from API, which will be the source of truth.
        const taskData = await getTaskResult(taskId);
        console.log(`[TaskPage.tsx] Task data received from API:`, taskData);

        if (!isActive) return; // Component unmounted, don't update state

        setTask(taskData);

        const timelineEvents = taskData.viewpoint_details?.timeline_events;
        if (timelineEvents && timelineEvents.length > 0) {
          setEvents(timelineEvents);

          // Cache the complete task data if it's in a final state
          try {
            if (taskData.status === 'completed' || taskData.status === 'failed') {
              await cacheTaskResults(taskData);
            }
          } catch (cacheError) {
            console.error('[TaskPage.tsx] Error caching task results:', cacheError);
          }
        } else if (taskData.status === 'completed' && !timelineEvents) {
          // Handle cases where a completed task has no events.
          setEvents([]);
        }

        // Set progress messages from the direct task endpoint response if available
        if (taskData.progress_messages) {
          setProgressMessages(taskData.progress_messages);
        }

        // If task is still processing, establish WebSocket connection
        if (taskData.status === 'processing' || taskData.status === 'pending') {
          // Close existing connection if any
          if (currentWebSocket) {
            console.log(
              '[TaskPage.tsx] Closing existing WebSocket connection before creating new one.'
            );
            currentWebSocket.close();
            setCurrentWebSocket(null);
          }

          console.log(
            `[TaskPage.tsx] Task ${taskId} is ${taskData.status}, establishing WebSocket connection`
          );
          setLatestProgressMessage(
            `Task is ${taskData.status}. Connecting for real-time updates...`
          );

          const callbacks: TimelineWebSocketCallbacks = {
            onOpen: (wsRequestId) => {
              if (!isActive) return;
              console.log(`[TaskPage.tsx] WebSocket opened for task ID: ${wsRequestId}`);
              setLatestProgressMessage('Connected. Monitoring task progress...');
            },
            onHistoricalProgress: (progressMsg) => {
              if (!isActive) return;
              console.log('[TaskPage.tsx] WebSocket historical progress:', progressMsg);
              setProgressMessages(progressMsg.steps);
              if (progressMsg.steps.length > 0) {
                setLatestProgressMessage(progressMsg.steps[0].message);

                // Find the most recent status from historical steps and update task status
                // Note: WebSocketStatusMessage doesn't have a status field in the type definition
                // The status is part of the step/message content, not a separate field
                const latestStatusStep = progressMsg.steps.find(
                  (step) => step.step && step.step.toLowerCase().includes('status')
                );
                if (latestStatusStep?.step) {
                  // Extract status from step name or message if needed
                  // This is a more type-safe approach than using 'any'
                  console.log('[TaskPage.tsx] Latest status step:', latestStatusStep);
                }
              }
            },
            onStatusUpdate: (statusMsg: WebSocketStatusMessage) => {
              if (!isActive) return;
              setProgressMessages((prev) => [statusMsg, ...prev]);
              setLatestProgressMessage(statusMsg.message);
              // Only update task status for explicit task-level completion signals
              // Do NOT update status based on intermediate step completions like "article_processing_completed"
              // Task status should only be updated by explicit WebSocket messages of type "task_completed" or "task_failed"
              // or by API responses from getTaskResult()
            },
            onPreliminaryEvents: (prelimMsg) => {
              if (!isActive) return;
              console.log('[TaskPage.tsx] WebSocket preliminary events:', prelimMsg);
              const isMergerDisabled =
                prelimMsg.message && prelimMsg.message.includes('raw events extracted');
              const defaultMessage = isMergerDisabled
                ? 'Raw events loaded. Processing complete if merger is disabled...'
                : 'Raw events loaded, merging in progress...';
              setLatestProgressMessage(prelimMsg.message || defaultMessage);
            },
            onTaskCompleted: (completionMsg) => {
              if (!isActive) return;
              console.log('[TaskPage.tsx] WebSocket received task_completed:', completionMsg);
              // When task completes, refetch the final result to get all events
              // This is more reliable than trying to construct the final state from WS messages.
              refetchTaskResult();
              setLatestProgressMessage('Task completed. Fetching final results...');
              // Close the WebSocket connection as it's no longer needed.
              websocketConnection?.close();
              setCurrentWebSocket(null);
            },
            onTaskFailed: (failureMsg) => {
              if (!isActive) return;
              console.log('[TaskPage.tsx] WebSocket received task_failed:', failureMsg);
              // When task fails, refetch the final result to get the failure details
              // This ensures we have the most up-to-date status and error information
              refetchTaskResult();
              setLatestProgressMessage(`Task failed: ${failureMsg.message || 'Unknown error'}`);
              // Close the WebSocket connection as it's no longer needed.
              websocketConnection?.close();
              setCurrentWebSocket(null);
            },
            onError: (errorMsg) => {
              if (!isActive) return;
              console.error('[TaskPage.tsx] WebSocket error:', errorMsg);
              setError(errorMsg.message || 'An unknown WebSocket error occurred.');
              setLatestProgressMessage(`An error occurred: ${errorMsg.message || 'Unknown error'}`);
              // Do NOT update task status here - WebSocket connection errors are not the same as task failures
              // Task status should only be updated by explicit "task_failed" messages or API responses
            },
            onClose: (closeEvent: CloseEvent) => {
              if (!isActive) return;
              console.log(
                `[TaskPage.tsx] WebSocket closed. Code: ${closeEvent.code}, Reason: ${closeEvent.reason}`
              );
              setCurrentWebSocket(null);
            },
          };

          websocketConnection = getTimelineUpdatesWS(taskId, callbacks);
          if (isActive) {
            setCurrentWebSocket(websocketConnection);
          }
        }
      } catch (err) {
        if (!isActive) return;
        console.error('[TaskPage.tsx] Failed to fetch task data:', err);
        setError(err instanceof Error ? err.message : 'An unknown error occurred');
      } finally {
        if (isActive) {
          setLoading(false);
        }
      }
    }

    fetchTaskData();

    // Cleanup function
    return () => {
      isActive = false;
      if (websocketConnection) {
        console.log('[TaskPage.tsx] Cleaning up WebSocket connection from useEffect cleanup.');
        websocketConnection.close();
        websocketConnection = null;
      }
    };
    // Deliberately not including currentWebSocket in dependencies to avoid re-connecting on every state change.
    // The connection is managed manually within the effect and cleaned up on unmount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [taskId]);

  const refetchTaskResult = useCallback(async () => {
    if (!taskId) return;
    try {
      console.log(`[TaskPage.tsx] Refetching final result for task ${taskId}...`);
      const resultData = await getTaskResult(taskId);
      setTask(resultData);
      setEvents(resultData.viewpoint_details?.timeline_events || []);
      // Cache the newly fetched final result
      if (resultData.status === 'completed' || resultData.status === 'failed') {
        await cacheTaskResults(resultData);
      }
      console.log(`[TaskPage.tsx] Successfully refetched and updated task state.`);
    } catch (err) {
      console.error(`[TaskPage.tsx] Failed to refetch task result:`, err);
      setError(err instanceof Error ? err.message : 'Failed to load final task results.');
    }
  }, [taskId]);

  const handleYearSelect = (year: string) => {
    const element = document.getElementById(`year-${year}`);
    if (element) {
      // Calculate the offset needed for the fixed headers
      // Only main header remains, no QuickNav
      const headerOffset = 80; // Main header height

      const elementTop = element.getBoundingClientRect().top + window.pageYOffset;
      const offsetPosition = elementTop - headerOffset;

      window.scrollTo({
        top: offsetPosition,
        behavior: 'smooth',
      });
    }
  };

  const toggleShowSources = (eventId: string) => {
    setExpandedSources((prev) => ({ ...prev, [eventId]: !prev[eventId] }));
  };

  const handleShareToggle = async (isPublic: boolean) => {
    if (!taskId || !task) return;
    setIsUpdatingShare(true);
    try {
      // API now returns the updated task object directly.
      const updatedTask = await updateTaskSharing(taskId, { is_public: isPublic });

      // Update state and cache with the new data from the single API call.
      setTask(updatedTask);
      try {
        await cacheTaskResults(updatedTask);
        console.log(
          `[TaskPage.tsx] Cached updated task results for task ${taskId} after sharing update.`
        );
      } catch (cacheError) {
        console.error('[TaskPage.tsx] Error caching updated task results:', cacheError);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update sharing status');
      // Optional: Add logic to revert optimistic UI updates here if you implement them.
    } finally {
      setIsUpdatingShare(false);
    }
  };

  const handleExport = (format: 'json' | 'markdown') => {
    if (!task) return;

    const eventsToExport = filteredEvents;

    if (format === 'json') {
      exportEventsAsJson(task, eventsToExport);
    } else if (format === 'markdown') {
      exportEventsAsMarkdown(task, eventsToExport);
    }
  };

  const handleFilterByKeyword = (keyword: string | null) => {
    setSelectedKeyword(keyword);
  };

  const getEventCountForKeyword = useCallback(
    (keyword: string) => {
      return sourceFilterData.counts.get(keyword) || 0;
    },
    [sourceFilterData.counts]
  );

  const totalEventsCount = filteredEvents.length;

  const hasRenderableContent =
    totalEventsCount > 0 ||
    loading ||
    (task && task.status !== 'completed' && task.status !== 'failed');

  // Handle loading and error states
  if (loading && !task) {
    return (
      <div className="flex justify-center items-center h-screen bg-parchment-50">
        <div className="text-center">
          <h2 className="text-2xl font-serif text-scholar-700">Loading Chronicle...</h2>
          <p className="text-scholar-500 mt-2">Retrieving records from the archives.</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex justify-center items-center h-screen bg-parchment-50">
        <div className="text-center max-w-xl mx-auto p-8 bg-red-50 border-2 border-red-200 rounded-lg">
          <h2 className="text-2xl font-serif text-red-800">Error Loading Chronicle</h2>
          <p className="text-red-700 mt-2 mb-4">{error}</p>
          <Link to="/" className="btn btn-primary">
            Back to Home
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen font-sans text-scholar-800">
      <div className="relative isolate">
        {/* TimelineQuickNav has been integrated into TimelineDisplay as vertical navigation */}

        {/* Main Content */}
        <div className="relative px-8 pb-16 pt-8">
          <div className="max-w-7xl mx-auto">
            <div ref={chronicleHeaderRef}>
              <ChronicleHeader
                task={task}
                onExport={handleExport}
                onShareToggle={handleShareToggle}
                isUpdatingShare={isUpdatingShare}
                timelineYears={timelineYears}
                activeYear={activeYear}
                onYearSelect={handleYearSelect}
                isQuickNavVisible={isQuickNavVisible}
                totalEventsCount={totalEventsCount}
              />
            </div>

            {hasRenderableContent && (
              <TimelineDisplay
                events={filteredEvents}
                activeYear={activeYear}
                onYearSelect={handleYearSelect}
                uniqueKeywords={sourceFilterData.keywords}
                keywordToTitleMap={sourceFilterData.titles}
                getEventCountForKeyword={getEventCountForKeyword}
                totalEventsCount={events.length}
                selectedKeyword={selectedKeyword}
                onSelectedKeywordChange={handleFilterByKeyword}
                expandedSources={expandedSources}
                onToggleShowSources={toggleShowSources}
              />
            )}

            {/* Progress Section (Moved to the bottom, collapsible) */}
            {(progressMessages.length > 0 || latestProgressMessage) && (
              <ProgressDisplay
                progressMessages={progressMessages}
                latestProgressMessage={latestProgressMessage}
                loading={loading && !events.length}
                viewingServerTaskId={taskId ?? null}
                isInitiallyExpanded={task?.status === 'processing' || task?.status === 'pending'}
              />
            )}
          </div>
        </div>

        {/* Manuscript footer */}
        <div className="relative px-8 pb-8">
          <div className="pt-12 text-center">
            <div className="flex justify-center mb-4">
              <WavyLine className="w-24 text-parchment-400" />
            </div>
            <p className="text-sm text-scholar-500 italic">
              Chronicle Archive - Digital Manuscript System
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default TaskPage;
