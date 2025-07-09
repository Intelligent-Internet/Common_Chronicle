import { useState, useEffect, useCallback } from 'react';
import { getPublicTimelines } from '../services/api';
import { getLocalPublicTasks, syncPublicTasks } from '../services/indexedDB.service';
import TimelineCard from '../components/TimelineCard';
import type { ExtendedUserTaskRecord } from '../services/indexedDB.service';

function PublicTimelinesPage() {
  const [publicTasks, setPublicTasks] = useState<ExtendedUserTaskRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const handleFetchPublicTasks = useCallback(async (isManualRefresh = false) => {
    if (isManualRefresh) {
      setIsLoading(true);
    }
    setError(null);
    try {
      console.log('[PublicTimelinesPage.tsx] Fetching public timelines from API...');
      const tasks = await getPublicTimelines({ limit: 50 });
      // The new API endpoint ensures tasks are completed and have events,
      // so client-side filtering is no longer necessary.

      console.log(`[PublicTimelinesPage.tsx] Syncing ${tasks.length} timelines to cache.`);
      await syncPublicTasks(tasks);

      const freshTasks = await getLocalPublicTasks();
      setPublicTasks(freshTasks);
    } catch (err) {
      console.error('[PublicTimelinesPage.tsx] Error fetching public timelines:', err);
      setError('Failed to load public timelines. See console for details.');
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Stale-While-Revalidate: Display cached content immediately, refresh in background
  useEffect(() => {
    let isMounted = true;

    const initializePage = async () => {
      // Stale: Show cached data immediately for better perceived performance
      console.log('[PublicTimelinesPage.tsx] Loading public tasks from cache...');
      const cachedTasks = await getLocalPublicTasks();
      if (isMounted && cachedTasks.length > 0) {
        setPublicTasks(cachedTasks);
        setIsLoading(false);
        console.log(`[PublicTimelinesPage.tsx] Displayed ${cachedTasks.length} tasks from cache.`);
      } else {
        setIsLoading(true);
      }

      // While-Revalidate: Fetch fresh data in background
      await handleFetchPublicTasks(false);
    };

    initializePage();

    return () => {
      isMounted = false;
    };
  }, [handleFetchPublicTasks]);

  return (
    <div className="min-h-screen font-sans text-scholar-800 isolate">
      <div className="container mx-auto p-8 max-w-4xl">
        <header className="text-center mb-12">
          <h1 className="text-5xl font-serif font-bold text-scholar-800 mb-4">
            The Public Archives
          </h1>
          <p className="text-lg text-scholar-600 max-w-2xl mx-auto italic">
            A collection of noteworthy chronicles, curated from the works of our esteemed scholars.
          </p>
          <div className="flex justify-center mt-6">
            <button
              onClick={() => handleFetchPublicTasks(true)}
              className="btn-secondary flex items-center gap-2"
              disabled={isLoading}
            >
              <svg
                className={`w-4 h-4 transition-transform ${isLoading ? 'animate-spin' : ''}`}
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
              {isLoading ? 'Refreshing...' : 'Refresh Archives'}
            </button>
          </div>
        </header>

        {/* Loading State */}
        {isLoading && (
          <div className="text-center py-12">
            <svg
              className="w-16 h-4 text-parchment-400 mb-4 mx-auto"
              viewBox="0 0 60 15"
              fill="currentColor"
            >
              <circle cx="7.5" cy="7.5" r="7.5" className="animate-pulse [animation-delay:-0.3s]">
                <animate
                  attributeName="r"
                  from="7.5"
                  to="7.5"
                  dur="1.5s"
                  begin="0s"
                  repeatCount="indefinite"
                  values="7.5; 3; 7.5"
                />
              </circle>
              <circle cx="30" cy="7.5" r="7.5" className="animate-pulse [animation-delay:-0.15s]">
                <animate
                  attributeName="r"
                  from="7.5"
                  to="7.5"
                  dur="1.5s"
                  begin="0s"
                  repeatCount="indefinite"
                  values="7.5; 3; 7.5"
                />
              </circle>
              <circle cx="52.5" cy="7.5" r="7.5" className="animate-pulse">
                <animate
                  attributeName="r"
                  from="7.5"
                  to="7.5"
                  dur="1.5s"
                  begin="0s"
                  repeatCount="indefinite"
                  values="7.5; 3; 7.5"
                />
              </circle>
            </svg>
            <p className="text-scholar-600 italic">Unsealing the archives...</p>
          </div>
        )}

        {/* Error State */}
        {error && (
          <div className="max-w-xl mx-auto p-8 bg-red-50 border-2 border-red-200 rounded-lg text-center">
            <h2 className="text-2xl font-serif text-red-800">Archive Error</h2>
            <p className="text-red-700 mt-2">{error}</p>
          </div>
        )}

        {/* Empty State */}
        {!isLoading && !error && publicTasks.length === 0 && (
          <div className="text-center py-16 px-8 bg-parchment-100/50 border-2 border-dashed border-parchment-300 rounded-lg">
            <svg
              className="h-20 w-20 text-scholar-400 mx-auto mb-6"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth="0.8"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4"
              />
            </svg>
            <h3 className="text-3xl font-serif text-scholar-700 mb-2">The Archives are Empty</h3>
            <p className="text-scholar-600">
              There are currently no featured chronicles available to display.
            </p>
          </div>
        )}

        {/* Success State - Stacked Cards */}
        {!isLoading && !error && publicTasks.length > 0 && (
          <div className="flex flex-col items-center">
            <p className="mb-8 text-sm text-scholar-500">
              Found {publicTasks.length} chronicle{publicTasks.length !== 1 ? 's' : ''} in the
              archives. Hover to inspect.
            </p>
            <div
              className="relative w-full"
              style={{
                maxWidth: '42rem',
                // Each card reveals 4rem, the last card is fully visible (15rem)
                height: `${(publicTasks.length - 1) * 4 + 15}rem`,
              }}
            >
              {publicTasks.map((task, index) => {
                // Deterministic but varied card positioning for visual appeal
                const rotations = [-1.2, 1.5, 0.8, -0.5, 1.8, -1.0];
                const offsets = [-3, 5, 2, -1, 6, -4];

                const initialRotation = rotations[index % rotations.length];
                const initialOffset = offsets[index % offsets.length];
                const initialTransform = `rotate(${initialRotation}deg) translateX(${initialOffset}px) scale(1)`;
                const hoverTransform = `rotate(0deg) scale(1.05) translateY(-10px)`;

                return (
                  <div
                    key={task.id}
                    className="group absolute w-full cursor-pointer transition-transform duration-300 ease-in-out"
                    style={{
                      top: `${index * 4}rem`, // 4rem = 64px
                      zIndex: index,
                      transform: initialTransform,
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.zIndex = '100';
                      e.currentTarget.style.transform = hoverTransform;
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.zIndex = index.toString();
                      e.currentTarget.style.transform = initialTransform;
                    }}
                  >
                    <TimelineCard task={task} />
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default PublicTimelinesPage;
