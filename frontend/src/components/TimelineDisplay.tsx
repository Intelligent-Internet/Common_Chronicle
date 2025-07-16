import React, { useRef, useState, useEffect } from 'react';
import type { TimelineEvent } from '../types';
import ContentCard from './ContentCard';
import InkBlotButton from './InkBlotButton';
import VerticalWavyLine from './VerticalWavyLine';
import {
  formatEventDate,
  getDataSourceLabel,
  getSourceLinkText,
  sortEventsChronologically,
  getUniqueYearsForNavigation,
  getDisplayYear,
} from '../utils/timelineUtils';

interface TimelineDisplayProps {
  events: TimelineEvent[];
  activeYear: string | null;
  expandedSources: Record<string, boolean>;
  onToggleShowSources: (eventId: string) => void;
  onYearSelect?: (year: string) => void;
}

const TimelineDisplay: React.FC<TimelineDisplayProps> = ({
  events,
  activeYear,
  expandedSources,
  onToggleShowSources,
  onYearSelect,
}) => {
  // Add new state for navigation
  const [showNavigation, setShowNavigation] = React.useState(true);
  const [yearListStartIndex, setYearListStartIndex] = React.useState(0);
  const timelineContentRef = useRef<HTMLDivElement>(null);
  const [timelineHeight, setTimelineHeight] = useState(0);

  useEffect(() => {
    // Function to update height
    const updateHeight = () => {
      if (timelineContentRef.current) {
        setTimelineHeight(timelineContentRef.current.scrollHeight);
      }
    };

    const element = timelineContentRef.current; // Capture ref value

    // Update height on mount and when events change
    updateHeight();
    const resizeObserver = new ResizeObserver(updateHeight);
    if (element) {
      resizeObserver.observe(element);
    }

    return () => {
      // Use the captured value in the cleanup function
      if (element) {
        resizeObserver.unobserve(element);
      }
    };
  }, [events]);

  // Maximum number of years to show in the navigation at once
  const MAX_VISIBLE_YEARS = 8;

  // Use the new chronological sorting function that properly handles BCE/CE dates
  const sortedEvents = sortEventsChronologically(events);

  // Get unique years from events for vertical navigation, properly sorted chronologically
  const timelineYears = getUniqueYearsForNavigation(sortedEvents);

  // Calculate visible years for pagination
  const totalYears = timelineYears.length;
  const endIndex = Math.min(yearListStartIndex + MAX_VISIBLE_YEARS, totalYears);
  const visibleYears = timelineYears.slice(yearListStartIndex, endIndex);

  // Auto-center active year in navigation for better UX
  React.useEffect(() => {
    if (activeYear && timelineYears.length > MAX_VISIBLE_YEARS) {
      const activeIndex = timelineYears.indexOf(activeYear);
      if (activeIndex !== -1) {
        // Calculate ideal start position to center the active year
        const idealStart = Math.max(0, activeIndex - Math.floor(MAX_VISIBLE_YEARS / 2));
        const maxStart = Math.max(0, totalYears - MAX_VISIBLE_YEARS);
        const newStart = Math.min(idealStart, maxStart);
        setYearListStartIndex(newStart);
      }
    }
  }, [activeYear, timelineYears, totalYears]);

  // Progressive navigation: Show year navigation only when scrolled past filters
  React.useEffect(() => {
    const handleScroll = () => {
      const scrollY = window.scrollY;

      // Show navigation after scrolling past filter area (~300px)
      const shouldShow = scrollY > 300;

      setShowNavigation(shouldShow);
    };

    window.addEventListener('scroll', handleScroll);
    handleScroll(); // Initialize on mount

    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  if (events.length === 0) {
    return (
      <div className="mt-12">
        <ContentCard className="max-w-md mx-auto" padding="p-8">
          <div className="text-center">
            <svg
              className="w-16 h-16 text-pewter mx-auto mb-6"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="1"
                d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
              />
            </svg>
            <h3 className="text-xl font-sans font-semibold text-slate dark:text-mist mb-2">
              No Matching Chronicles
            </h3>
            <p className="font-alt text-slate dark:text-mist leading-relaxed">
              No events match the current filter.
            </p>
          </div>
        </ContentCard>
      </div>
    );
  }

  let lastRenderedYear: string | null = null;

  return (
    <div className="mt-12 max-w-6xl mx-auto px-4">
      {/* Vertical Year Navigation & Timeline Container */}
      <div className="relative flex">
        {/* Smart Vertical Year Quick Navigation */}
        {timelineYears.length > 0 && onYearSelect && showNavigation && (
          <div className="fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-30 ml-[-36rem] transition-all duration-300 ease-in-out max-h-[90vh] flex flex-col">
            <ContentCard padding="p-4" className="backdrop-blur-sm shadow-lg flex-1 flex flex-col">
              <div className="flex flex-col gap-3 flex-1 min-h-0">
                {/* Top navigation button - always visible */}
                <InkBlotButton
                  isActive={false}
                  onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
                  variant="default"
                  className="w-14 h-8 text-xs font-medium"
                  title="Scroll to top"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth="2"
                      d="M5 15l7-7 7 7"
                    />
                  </svg>
                </InkBlotButton>

                <div className="h-px bg-pewter mx-2"></div>

                {/* Paginated year list */}
                <div className="flex flex-col gap-2 flex-1 overflow-hidden py-2 min-h-0">
                  <div className="flex flex-col gap-2">
                    {visibleYears.map((year) => {
                      // Adjust font size based on year string length (BCE years are typically longer)
                      const isBCE = year.includes('BCE');
                      const isLongYear = year.length > 6;
                      const fontSizeClass = isBCE || isLongYear ? 'text-xs' : 'text-sm';
                      const widthClass = isBCE || isLongYear ? 'w-16' : 'w-14';

                      return (
                        <InkBlotButton
                          key={year}
                          isActive={activeYear === year}
                          onClick={() => onYearSelect(year)}
                          variant="year"
                          className={`${widthClass} h-10 ${fontSizeClass} font-medium`}
                        >
                          {year}
                        </InkBlotButton>
                      );
                    })}
                  </div>
                </div>

                <div className="h-px bg-pewter mx-2"></div>

                {/* Bottom navigation button - always visible */}
                <InkBlotButton
                  isActive={false}
                  onClick={() =>
                    window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' })
                  }
                  variant="default"
                  className="w-14 h-8 text-xs font-medium"
                  title="Scroll to bottom"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth="2"
                      d="M19 9l-7 7-7-7"
                    />
                  </svg>
                </InkBlotButton>
              </div>
            </ContentCard>
          </div>
        )}

        {/* Main Timeline Content */}
        <div className="w-full relative pl-[18rem]" ref={timelineContentRef}>
          {/* The Time Weave - organic timeline spine, now using the performant component */}
          <div className="absolute left-24 top-0 h-full w-8 pointer-events-none">
            <VerticalWavyLine
              height={timelineHeight}
              amplitude={2}
              segments={100}
              stroke="url(#timelineGradient)"
            />
          </div>
          {/* Define the gradient and pattern for the wavy line */}
          <svg width="0" height="0" className="absolute">
            <defs>
              <linearGradient id="timelineGradient" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" stopColor="#919eae" stopOpacity="0.6" />
                <stop offset="30%" stopColor="#56696d" stopOpacity="0.9" />
                <stop offset="70%" stopColor="#56696d" stopOpacity="0.9" />
                <stop offset="100%" stopColor="#919eae" stopOpacity="0.6" />
              </linearGradient>

              {/* High-performance texture pattern for the timeline stroke */}
              <pattern
                id="timelineTexturePattern"
                patternUnits="userSpaceOnUse"
                width="150"
                height="150"
              >
                <image
                  href={`data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 150 150"><rect width="100%" height="100%" fill="#56696d"/><filter id="n"><feTurbulence type="fractalNoise" baseFrequency="0.7" numOctaves="5" stitchTiles="stitch"/></filter><rect width="100%" height="100%" filter="url(%23n)" opacity="0.4"/></svg>`}
                  width="150"
                  height="150"
                />
              </pattern>
            </defs>
          </svg>

          {/* Subtle ink spots along the timeline */}
          <div className="absolute left-7 top-0 h-full w-2 opacity-20">
            {[...Array(12)].map((_, i) => (
              <div
                key={i}
                className="absolute w-1 h-1 bg-pewter rounded-full"
                style={{
                  top: `${(i + 1) * 8}%`,
                  left: `${2 + Math.sin(i * 0.7) * 4}px`,
                  transform: `scale(${0.5 + Math.random() * 0.5})`,
                }}
              ></div>
            ))}
          </div>

          {/* Decorative manuscript-style flourishes */}
          <div className="absolute left-5 top-0 h-full w-6 opacity-15">
            {[...Array(8)].map((_, i) => (
              <div
                key={i}
                className="absolute text-pewter text-xs"
                style={{
                  top: `${(i + 1) * 12}%`,
                  left: `${Math.sin(i * 0.5) * 8}px`,
                  transform: `rotate(${Math.sin(i * 0.3) * 15}deg)`,
                }}
              >
                ※
              </div>
            ))}
          </div>

          {sortedEvents.map((event) => {
            const displayYear = getDisplayYear(event);
            const showYear = displayYear !== lastRenderedYear;
            lastRenderedYear = displayYear;

            return (
              <React.Fragment key={event.id}>
                {showYear && (
                  <div id={`year-${displayYear}`} className="relative my-6">
                    <div className="flex items-center" style={{ marginLeft: '-13rem' }}>
                      <div
                        className={`relative z-10 transition-all duration-300 ${
                          activeYear === displayYear ? 'scale-110' : 'scale-100'
                        }`}
                      >
                        {(() => {
                          // Adjust container and font size based on year string length
                          const isBCE = displayYear.includes('BCE');
                          const isLongYear = displayYear.length > 6;
                          const isVeryLongYear = displayYear.length > 10;

                          let containerWidth = 'w-24'; // default
                          let fontSize = 'text-xl'; // default

                          if (isVeryLongYear) {
                            containerWidth = 'w-32';
                            fontSize = 'text-base';
                          } else if (isBCE || isLongYear) {
                            containerWidth = 'w-28';
                            fontSize = 'text-lg';
                          }

                          return (
                            <div
                              className={`relative ${containerWidth} h-16 flex items-center justify-center`}
                            >
                              <svg
                                className="absolute w-full h-full"
                                viewBox="0 0 120 80"
                                style={{
                                  filter:
                                    activeYear === displayYear
                                      ? 'drop-shadow(0 4px 4px rgba(0,0,0,0.12))'
                                      : 'drop-shadow(0 2px 2px rgba(0,0,0,0.1))',
                                }}
                              >
                                <path
                                  d="M10 40 C5 20, 30 5, 60 8 S 115 15, 110 40 S 100 75, 60 72 S 15 60, 10 40Z"
                                  className={`fill-white dark:fill-slate ${
                                    activeYear === displayYear
                                      ? 'stroke-slate dark:stroke-sky-blue'
                                      : 'stroke-pewter dark:stroke-mist'
                                  }`}
                                  strokeWidth="4"
                                />
                              </svg>
                              <span
                                className={`relative font-sans ${fontSize} font-semibold leading-none text-center px-1 ${
                                  activeYear === displayYear
                                    ? 'text-charcoal dark:text-white'
                                    : 'text-slate dark:text-mist'
                                }`}
                              >
                                {displayYear}
                              </span>
                            </div>
                          );
                        })()}
                      </div>
                      <div className="ml-4 flex items-center gap-1">
                        {/* Decorative dots with decreasing size */}
                        <div className="w-2 h-2 bg-slate rounded-full"></div>
                        <div className="w-1.5 h-1.5 bg-pewter rounded-full"></div>
                        <div className="w-1 h-1 bg-pewter rounded-full opacity-80"></div>
                        <div className="w-0.5 h-0.5 bg-pewter rounded-full opacity-60"></div>
                        {/* Classical flourish */}
                        <span className="text-pewter text-sm ml-1 opacity-30">❦</span>
                        {/* Ink brush stroke */}
                        <svg className="w-8 h-2 ml-2 opacity-40" viewBox="0 0 32 8">
                          <path
                            d="M2 4 Q8 2 16 4 Q24 6 30 4"
                            stroke="#919eae"
                            strokeWidth="1.5"
                            fill="none"
                            strokeLinecap="round"
                            opacity="0.6"
                          />
                        </svg>
                      </div>
                    </div>
                  </div>
                )}

                <div className="relative mb-12 max-w-2xl">
                  {/* Irregular connector line from timeline to card */}
                  <svg
                    className="absolute top-1/2 w-[176px] h-auto text-pewter dark:text-mist"
                    style={{ left: '-11rem', transform: 'translateY(-50%)' }}
                    viewBox="0 0 176 10"
                    fill="none"
                    xmlns="http://www.w3.org/2000/svg"
                  >
                    <path
                      d="M0 5 Q88 2 176 5"
                      stroke="url(#timelineTexturePattern)"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                    />
                  </svg>
                  {/* Hollow circle on the timeline spine */}
                  <div
                    className="absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full border-2 border-slate bg-white shadow-sm dark:bg-slate dark:border-mist"
                    style={{ left: '-11rem' }}
                  ></div>

                  {/* Date label on the connector line */}
                  {event.date_info && (
                    <div
                      className="absolute top-1/2 -translate-y-1/2"
                      style={{
                        left: '-5.5rem',
                        transform: 'translateX(-50%) translateY(-50%)',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      <span className="bg-white px-2 py-0.5 rounded-sm text-sm font-alt text-slate shadow-sm dark:bg-slate dark:text-mist">
                        {formatEventDate(event.date_info)}
                      </span>
                    </div>
                  )}

                  <ContentCard padding="p-6">
                    <div className="flex items-start justify-between mb-3">
                      <h3 className="font-sans text-xl font-semibold text-charcoal dark:text-white flex-1">
                        {event.description}
                      </h3>
                      {event.relevance_score !== null && event.relevance_score !== undefined && (
                        <div className="ml-4 flex-shrink-0">
                          <div
                            className={`px-3 py-1 rounded-full border ${
                              event.relevance_score >= 0.75
                                ? 'bg-green-100 border-green-300 text-green-800 dark:bg-green-900/20 dark:border-green-700 dark:text-green-400'
                                : event.relevance_score >= 0.5
                                  ? 'bg-yellow-100 border-yellow-300 text-yellow-800 dark:bg-yellow-900/20 dark:border-yellow-700 dark:text-yellow-400'
                                  : 'bg-red-100 border-red-300 text-red-800 dark:bg-red-900/20 dark:border-red-700 dark:text-red-400'
                            }`}
                            title={`Relevance Score: ${event.relevance_score.toFixed(2)} - ${
                              event.relevance_score >= 0.75
                                ? 'High relevance'
                                : event.relevance_score >= 0.5
                                  ? 'Medium relevance'
                                  : 'Low relevance'
                            }`}
                          >
                            <div className="flex items-center gap-1.5">
                              <svg
                                className="w-3.5 h-3.5"
                                fill="none"
                                stroke="currentColor"
                                viewBox="0 0 24 24"
                              >
                                <path
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  strokeWidth="2"
                                  d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
                                />
                              </svg>
                              <div className="flex flex-col items-center leading-tight">
                                <span className="text-sm font-bold -mt-0.5">
                                  {(event.relevance_score * 100).toFixed(0)}%
                                </span>
                              </div>
                            </div>
                          </div>
                        </div>
                      )}
                    </div>

                    {event.main_entities && event.main_entities.length > 0 && (
                      <div className="mb-4">
                        <div className="flex flex-wrap gap-2">
                          {event.main_entities.map((entity) => (
                            <span
                              key={entity.original_name}
                              className="px-2.5 py-1 text-xs font-medium text-slate bg-sky-blue/20 border border-sky-blue rounded-md flex items-center gap-1.5 dark:bg-sky-blue/10 dark:border-sky-blue/50 dark:text-mist"
                            >
                              {entity.original_name}
                              <span className="text-pewter dark:text-mist">
                                ({entity.entity_type})
                              </span>
                              {entity.is_verified_existent && (
                                <svg
                                  className="w-3 h-3 text-slate dark:text-sky-blue"
                                  fill="currentColor"
                                  viewBox="0 0 20 20"
                                >
                                  <path
                                    fillRule="evenodd"
                                    d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                                    clipRule="evenodd"
                                  />
                                </svg>
                              )}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}

                    {event.source_text_snippet && (
                      <blockquote className="border-l-4 border-pewter pl-4 text-sm text-slate italic my-4 font-alt dark:text-mist dark:border-mist">
                        {event.source_text_snippet}
                      </blockquote>
                    )}

                    {/* --- Source Information --- */}
                    <div className="mt-4 pt-4 border-t border-pewter/50 dark:border-mist/30">
                      {event.source_url && (
                        <div className="flex items-center gap-3 text-sm">
                          <svg
                            className="w-4 h-4 text-pewter flex-shrink-0 dark:text-mist"
                            fill="none"
                            stroke="currentColor"
                            viewBox="0 0 24 24"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth="2"
                              d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.246 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"
                            ></path>
                          </svg>
                          <a
                            href={event.source_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-slate hover:text-charcoal underline truncate font-alt dark:text-mist dark:hover:text-white"
                            title={event.source_url}
                          >
                            {getSourceLinkText(event.source_page_title, event.source_url)}
                          </a>
                        </div>
                      )}

                      {(() => {
                        const allSources = event.sources || [];

                        // Find the index of the source that is already displayed as the representative one.
                        const representativeSourceIndex = allSources.findIndex(
                          (s) =>
                            s.source_url === event.source_url &&
                            s.source_text_snippet === event.source_text_snippet
                        );

                        // "Other sources" are all sources EXCLUDING the representative one.
                        const otherSources = allSources.filter(
                          (_, index) => index !== representativeSourceIndex
                        );

                        if (otherSources.length === 0) {
                          return null;
                        }

                        return (
                          <>
                            <button
                              onClick={() => onToggleShowSources(event.id)}
                              className="text-xs text-slate hover:text-charcoal mt-2 flex items-center gap-1 font-alt dark:text-mist dark:hover:text-white"
                            >
                              {expandedSources[event.id]
                                ? 'Hide other sources'
                                : `Show ${otherSources.length} other source(s)`}
                              <svg
                                className={`w-3 h-3 transition-transform ${expandedSources[event.id] ? 'rotate-180' : ''}`}
                                fill="none"
                                stroke="currentColor"
                                viewBox="0 0 24 24"
                              >
                                <path
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  strokeWidth="2"
                                  d="M19 9l-7 7-7-7"
                                ></path>
                              </svg>
                            </button>

                            {expandedSources[event.id] && (
                              <div className="mt-3 space-y-3 pl-4 border-l-2 border-pewter/50 dark:border-mist/30">
                                {otherSources.map((source, idx) => (
                                  <div key={idx} className="text-xs font-alt">
                                    <div className="flex items-center gap-2">
                                      <svg
                                        className="w-3 h-3 text-pewter flex-shrink-0 dark:text-mist"
                                        fill="none"
                                        stroke="currentColor"
                                        viewBox="0 0 24 24"
                                      >
                                        <path
                                          strokeLinecap="round"
                                          strokeLinejoin="round"
                                          strokeWidth="2"
                                          d="M9 5l7 7-7-7"
                                        ></path>
                                      </svg>
                                      <a
                                        href={source.source_url || '#'}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="text-slate hover:text-charcoal underline truncate font-medium dark:text-mist dark:hover:text-white"
                                        title={source.source_url || 'No URL available'}
                                      >
                                        {getSourceLinkText(
                                          source.source_page_title,
                                          source.source_url || ''
                                        )}
                                      </a>
                                      {source.source_url &&
                                        getDataSourceLabel(source.source_url) && (
                                          <span className="text-pewter dark:text-mist">
                                            ({getDataSourceLabel(source.source_url)})
                                          </span>
                                        )}
                                    </div>
                                    {source.source_text_snippet && (
                                      <blockquote className="border-l-2 border-pewter pl-3 ml-1.5 mt-2 py-1 text-slate italic dark:text-mist dark:border-mist">
                                        "{source.source_text_snippet}"
                                      </blockquote>
                                    )}
                                  </div>
                                ))}
                              </div>
                            )}
                          </>
                        );
                      })()}
                    </div>
                    {/* --- End Source Information --- */}
                  </ContentCard>
                </div>
              </React.Fragment>
            );
          })}
        </div>
      </div>
    </div>
  );
};

export default TimelineDisplay;
