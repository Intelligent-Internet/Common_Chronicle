import React, { useState, useEffect, useCallback } from 'react';
import type { TimelineEvent, EventSourceInfo } from '../types';
import InkBlotButton from './InkBlotButton';
import ContentCard from './ContentCard';

interface FilterPanelProps {
  events: TimelineEvent[];
  sources: Record<string, EventSourceInfo>; // Dictionary of source references
  keywordToTitleMap: Map<string, string>;
  uniqueKeywords: string[];
  isOpen: boolean;
  onClose: () => void;
  onApplyFilters: (filters: { selectedKeyword: string | null; minRelevanceScore: number }) => void;
  currentFilters: { selectedKeyword: string | null; minRelevanceScore: number };
}

const FilterPanel: React.FC<FilterPanelProps> = ({
  events,
  sources,
  keywordToTitleMap,
  uniqueKeywords,
  isOpen,
  onClose,
  onApplyFilters,
  currentFilters,
}) => {
  // Local state for temporary filters (before applying)
  const [tempSelectedKeyword, setTempSelectedKeyword] = useState<string | null>(
    currentFilters.selectedKeyword
  );
  const [tempMinRelevanceScore, setTempMinRelevanceScore] = useState<number>(
    currentFilters.minRelevanceScore
  );

  // Update temp state when current filters change
  useEffect(() => {
    setTempSelectedKeyword(currentFilters.selectedKeyword);
    setTempMinRelevanceScore(currentFilters.minRelevanceScore);
  }, [currentFilters]);

  // Calculate filtered events based on current temp filters
  const getFilteredEvents = () => {
    let filteredEvents = events;

    // Apply source filter
    if (tempSelectedKeyword) {
      filteredEvents = filteredEvents.filter((event) => {
        if (event.source_snippets && typeof event.source_snippets === 'object') {
          return Object.keys(event.source_snippets).some(
            (sourceRef) => sources[sourceRef]?.source_page_title === tempSelectedKeyword
          );
        } else {
          console.warn(
            '[FilterPanel.tsx] Event has empty or invalid source_snippets in getFilteredEvents:',
            {
              eventId: event.id,
              eventDescription: event.description?.substring(0, 100) + '...',
              sourceSnippets: event.source_snippets,
              tempSelectedKeyword: tempSelectedKeyword,
            }
          );
          return false;
        }
      });
    }

    // Apply relevance filter
    filteredEvents = filteredEvents.filter(
      (event) =>
        event.relevance_score !== null &&
        event.relevance_score !== undefined &&
        event.relevance_score >= tempMinRelevanceScore
    );

    return filteredEvents;
  };

  // Calculate relevance score options based on ALL events (fixed options)
  const getRelevanceScoreOptions = () => {
    // Always use all events to calculate options, not filtered by source
    const validScores = events
      .map((event) => event.relevance_score)
      .filter((score): score is number => score !== null && score !== undefined);

    if (validScores.length === 0) {
      return [];
    }

    // Get unique scores and sort them in ascending order (low to high)
    const uniqueScores = [...new Set(validScores)].sort((a, b) => a - b);

    // Generate threshold options for each unique score
    const options = [];
    for (const score of uniqueScores) {
      // Calculate count based on current source selection (if any)
      let relevantEvents = events;
      if (tempSelectedKeyword) {
        relevantEvents = relevantEvents.filter((event) => {
          if (event.source_snippets && typeof event.source_snippets === 'object') {
            return Object.keys(event.source_snippets).some(
              (sourceRef) => sources[sourceRef]?.source_page_title === tempSelectedKeyword
            );
          } else {
            console.warn(
              '[FilterPanel.tsx] Event has empty or invalid source_snippets in relevance options:',
              {
                eventId: event.id,
                eventDescription: event.description?.substring(0, 100) + '...',
                sourceSnippets: event.source_snippets,
                tempSelectedKeyword: tempSelectedKeyword,
              }
            );
            return false;
          }
        });
      }

      const count = relevantEvents.filter(
        (event) =>
          event.relevance_score !== null &&
          event.relevance_score !== undefined &&
          event.relevance_score >= score
      ).length;

      if (count > 0) {
        options.push({ score, count });
      }
    }

    return options;
  };

  const relevanceOptions = getRelevanceScoreOptions();

  // --- Ensure lowest score is selected by default when opening panel ---
  useEffect(() => {
    if (isOpen && relevanceOptions.length > 0) {
      // If current tempMinRelevanceScore 不在 options 中，或为0，则默认选中最低分项
      const found = relevanceOptions.find((opt) => opt.score === tempMinRelevanceScore);
      if (!found) {
        setTempMinRelevanceScore(relevanceOptions[0].score);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, relevanceOptions]);

  // Calculate source counts for filtering
  const getSourceCounts = () => {
    const counts = new Map<string, number>();

    // Count all events that meet the current relevance score filter
    let totalCount = 0;
    for (const event of events) {
      if (
        event.relevance_score !== null &&
        event.relevance_score !== undefined &&
        event.relevance_score >= tempMinRelevanceScore
      ) {
        totalCount++;
        // Count unique sources for this event
        const uniqueSourcesForEvent = new Set<string>();
        if (event.source_snippets && typeof event.source_snippets === 'object') {
          Object.keys(event.source_snippets).forEach((sourceRef) => {
            const source = sources[sourceRef];
            if (source?.source_page_title) {
              uniqueSourcesForEvent.add(source.source_page_title);
            }
          });
        } else {
          console.warn(
            '[FilterPanel.tsx] Event has empty or invalid source_snippets in getSourceCounts:',
            {
              eventId: event.id,
              eventDescription: event.description?.substring(0, 100) + '...',
              sourceSnippets: event.source_snippets,
              relevanceScore: event.relevance_score,
            }
          );
        }
        uniqueSourcesForEvent.forEach((title) => {
          counts.set(title, (counts.get(title) || 0) + 1);
        });
      }
    }

    return { counts, totalCount };
  };

  const { counts: sourceCounts, totalCount } = getSourceCounts();
  const filteredEvents = getFilteredEvents();

  const handleApply = () => {
    onApplyFilters({
      selectedKeyword: tempSelectedKeyword,
      minRelevanceScore: tempMinRelevanceScore,
    });
    onClose();
  };

  const handleReset = () => {
    setTempSelectedKeyword(null);
    setTempMinRelevanceScore(0);
  };

  const handleCancel = useCallback(() => {
    setTempSelectedKeyword(currentFilters.selectedKeyword);
    setTempMinRelevanceScore(currentFilters.minRelevanceScore);
    onClose();
  }, [currentFilters.selectedKeyword, currentFilters.minRelevanceScore, onClose]);

  // Handle ESC key to cancel filters
  useEffect(() => {
    const handleEscapeKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && isOpen) {
        handleCancel();
      }
    };

    if (isOpen) {
      document.addEventListener('keydown', handleEscapeKey);
      return () => {
        document.removeEventListener('keydown', handleEscapeKey);
      };
    }
  }, [isOpen, handleCancel]);

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4"
      onClick={handleCancel}
    >
      <div
        className="bg-white dark:bg-slate rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <ContentCard padding="p-6">
          {/* Header */}
          <div className="flex justify-between items-center mb-6">
            <h3 className="text-xl font-sans font-semibold text-slate dark:text-mist">Filters</h3>
            <button
              onClick={handleCancel}
              className="text-pewter hover:text-slate dark:text-mist dark:hover:text-white"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>
          </div>

          {/* Source Filter */}
          <div className="mb-6">
            <h4 className="font-medium text-slate dark:text-mist mb-3">Source Articles</h4>
            <div className="flex flex-wrap gap-2">
              <InkBlotButton
                isActive={!tempSelectedKeyword}
                onClick={() => setTempSelectedKeyword(null)}
                variant="default"
                className="text-sm"
              >
                All Sources ({totalCount})
              </InkBlotButton>
              {uniqueKeywords.map((keyword) => {
                const count = sourceCounts.get(keyword) || 0;

                return (
                  <InkBlotButton
                    key={keyword}
                    isActive={tempSelectedKeyword === keyword}
                    onClick={() => setTempSelectedKeyword(keyword)}
                    variant="default"
                    className="text-sm"
                    title={keywordToTitleMap.get(keyword) || keyword}
                  >
                    {keywordToTitleMap.get(keyword) || keyword} ({count})
                  </InkBlotButton>
                );
              })}
            </div>
          </div>

          {/* Relevance Filter */}
          {relevanceOptions.length > 0 && (
            <div className="mb-6">
              <h4 className="font-medium text-slate dark:text-mist mb-3">Relevance Score</h4>
              <div className="flex flex-wrap gap-2">
                {relevanceOptions.map((option) => (
                  <InkBlotButton
                    key={option.score}
                    isActive={tempMinRelevanceScore === option.score}
                    onClick={() => setTempMinRelevanceScore(option.score)}
                    variant="default"
                    className="text-sm"
                  >
                    {option.score.toFixed(2)} ({option.count})
                  </InkBlotButton>
                ))}
              </div>
            </div>
          )}

          {/* Preview */}
          <div className="mb-6 p-4 bg-stone-50 dark:bg-slate/50 rounded-lg">
            <p className="text-sm text-pewter dark:text-mist">
              Preview: <span className="font-medium">{filteredEvents.length}</span> events will be
              shown
            </p>
          </div>

          {/* Actions */}
          <div className="flex justify-between items-center">
            <button
              onClick={handleReset}
              className="px-4 py-2 text-sm text-pewter hover:text-slate dark:text-mist dark:hover:text-white"
            >
              Reset Filters
            </button>
            <div className="flex gap-3">
              <button
                onClick={handleCancel}
                className="px-4 py-2 text-sm border border-stone-300 rounded-md hover:bg-stone-50 dark:border-mist/30 dark:hover:bg-slate/50"
              >
                Cancel
              </button>
              <button onClick={handleApply} className="btn btn-primary text-sm px-4 py-2">
                Apply Filters
              </button>
            </div>
          </div>
        </ContentCard>
      </div>
    </div>
  );
};

export default FilterPanel;
