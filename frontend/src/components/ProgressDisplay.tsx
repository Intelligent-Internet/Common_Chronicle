import React, { useState, useMemo } from 'react';
import type { WebSocketStatusMessage } from '../types'; // Adjusted path
import { normalizeTimestamp, formatProgressTimestamp } from '../utils/timelineUtils'; // Adjusted path

interface ProgressDisplayProps {
  progressMessages: WebSocketStatusMessage[];
  latestProgressMessage: string | null;
  loading: boolean;
  viewingServerTaskId: string | null; // To determine if we are viewing a specific task's results
  isInitiallyExpanded?: boolean; // Optional prop to control initial expansion state
}

const ProgressDisplay: React.FC<ProgressDisplayProps> = ({
  progressMessages,
  latestProgressMessage,
  loading,
  viewingServerTaskId,
  isInitiallyExpanded = false, // Default to not expanded
}) => {
  const [isExpanded, setIsExpanded] = useState(isInitiallyExpanded);

  // Robust timestamp-based sorting with fallback handling for malformed data
  const sortedProgressMessages = useMemo(() => {
    if (!progressMessages || progressMessages.length === 0) return [];

    // Debug logging for timestamp processing issues
    console.log('[ProgressDisplay.tsx] Sorting progress messages:', {
      count: progressMessages.length,
      samples: progressMessages.slice(0, 3).map((msg) => ({
        message: msg.message?.substring(0, 50) + '...',
        timestamp: msg.timestamp,
        normalized: normalizeTimestamp(msg.timestamp),
        parsed: msg.timestamp ? new Date(msg.timestamp).getTime() : 'no timestamp',
      })),
    });

    return [...progressMessages].sort((a, b) => {
      // Handle timestamp normalization for cross-platform compatibility
      const aNormalized = normalizeTimestamp(a.timestamp);
      const bNormalized = normalizeTimestamp(b.timestamp);

      if (aNormalized && bNormalized) {
        const aTime = new Date(aNormalized).getTime();
        const bTime = new Date(bNormalized).getTime();

        // Debug timestamp comparison for troubleshooting
        if (progressMessages.length <= 5) {
          console.log('[ProgressDisplay.tsx] Comparing:', {
            a: {
              message: a.message?.substring(0, 30),
              original: a.timestamp,
              normalized: aNormalized,
              time: aTime,
            },
            b: {
              message: b.message?.substring(0, 30),
              original: b.timestamp,
              normalized: bNormalized,
              time: bTime,
            },
            result: bTime - aTime,
          });
        }

        // Valid timestamps: newest first
        if (!isNaN(aTime) && !isNaN(bTime)) {
          return bTime - aTime;
        }
      }

      // Fallback: prioritize valid timestamps over invalid ones
      if (aNormalized && !bNormalized) return -1;
      if (!aNormalized && bNormalized) return 1;

      // Both invalid: maintain original order
      return 0;
    });
  }, [progressMessages]);

  const isViewingTaskResult = !!viewingServerTaskId;
  const hasProgressMessages = sortedProgressMessages.length > 0;
  const hasLatestMessage = !!latestProgressMessage;

  if (!hasProgressMessages && !hasLatestMessage && !loading && !isViewingTaskResult) {
    return null;
  }

  if (loading && !hasProgressMessages && !hasLatestMessage) {
    return null;
  }

  const handleToggle = () => {
    setIsExpanded(!isExpanded);
  };

  return (
    <section className="mt-24 pt-8 border-t-2 border-dashed border-parchment-300">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-xl font-serif font-medium text-scholar-700">Research Process Log</h2>
        {hasProgressMessages && (
          <button
            onClick={handleToggle}
            className="text-sm text-scholar-600 hover:text-scholar-800 underline"
          >
            {isExpanded ? 'Collapse' : 'Show Details'} ({sortedProgressMessages.length} steps)
          </button>
        )}
      </div>
      <div className="mt-4">
        {isExpanded && hasProgressMessages ? (
          <ul className="list-none space-y-1 max-h-72 overflow-y-auto pr-2">
            {sortedProgressMessages.map((msg, index) => {
              const normalizedTimestamp = normalizeTimestamp(msg.timestamp);
              return (
                <li
                  key={`${msg.request_id}-${msg.step}-${index}`}
                  className="py-1 flex items-start gap-4 border-l-2 border-parchment-200 pl-4"
                >
                  {normalizedTimestamp && !isNaN(new Date(normalizedTimestamp).getTime()) ? (
                    <span className="text-xs text-scholar-500 flex-shrink-0 font-mono bg-parchment-50 px-2 py-1 rounded">
                      {formatProgressTimestamp(normalizedTimestamp)}
                    </span>
                  ) : (
                    <span className="text-xs text-scholar-500 flex-shrink-0 font-mono bg-parchment-50 px-2 py-1 rounded">
                      {formatProgressTimestamp(null)}
                    </span>
                  )}
                  <span className="flex-grow text-sm text-scholar-700 font-serif leading-normal">
                    {msg.message}
                  </span>
                </li>
              );
            })}
          </ul>
        ) : (
          <div className="text-sm text-scholar-700 font-serif leading-normal">
            {(() => {
              if (hasProgressMessages) {
                const latestMsg = sortedProgressMessages[0];
                const normalizedTs = normalizeTimestamp(latestMsg.timestamp);
                return (
                  <div className="flex items-start gap-4 border-l-2 border-parchment-200 pl-4 py-1">
                    {normalizedTs && !isNaN(new Date(normalizedTs).getTime()) && (
                      <span className="text-xs text-scholar-500 flex-shrink-0 font-mono bg-parchment-50 px-2 py-1 rounded">
                        {formatProgressTimestamp(normalizedTs)}
                      </span>
                    )}
                    <span className="flex-grow">{latestMsg.message}</span>
                  </div>
                );
              }
              return (
                <div className="border-l-2 border-parchment-200 pl-4 py-1">
                  {latestProgressMessage || (loading ? 'Initiating research...' : '')}
                </div>
              );
            })()}
          </div>
        )}
      </div>
    </section>
  );
};

export default ProgressDisplay;
