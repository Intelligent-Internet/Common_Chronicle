import type { DataSourceIdentifier, DataSourceCheckboxState, ParsedDateInfo } from '../types';
import { getStartDateISO } from '../types';

export const normalizeTimestamp = (isoString: string | null | undefined): string | null => {
  if (!isoString) return null;

  let tempTimestamp = isoString;

  // Step 1: Normalize UTC representations.
  // Handles "YYYY-MM-DDTHH:mm:ss.sss+00:00Z" -> "YYYY-MM-DDTHH:mm:ss.sssZ"
  // Also handles "YYYY-MM-DDTHH:mm:ss.sss+00:00" -> "YYYY-MM-DDTHH:mm:ss.sssZ"
  if (tempTimestamp.includes('+00:00')) {
    if (tempTimestamp.endsWith('+00:00Z')) {
      tempTimestamp = tempTimestamp.replace(/\+00:00Z$/, 'Z');
    } else if (tempTimestamp.endsWith('+00:00')) {
      tempTimestamp = tempTimestamp.replace(/\+00:00$/, 'Z');
    }
  }

  // Step 2: Truncate fractional seconds to millisecond precision (3 digits).
  const parts = tempTimestamp.split('.');
  if (parts.length === 2) {
    const mainPart = parts[0]; // Everything before the dot
    const fractionalPartWithTz = parts[1]; // Everything after the dot (e.g., "443595Z" or "4Z" or "443595+02:00")

    let digits = '';
    let TzAwareRest = ''; // Timezone or other non-digit characters after fractional seconds

    for (let i = 0; i < fractionalPartWithTz.length; i++) {
      const char = fractionalPartWithTz[i];
      if (char >= '0' && char <= '9') {
        digits += char;
      } else {
        TzAwareRest = fractionalPartWithTz.substring(i);
        break; // Stop collecting digits once a non-digit is found
      }
    }

    if (digits.length > 3) {
      digits = digits.substring(0, 3); // Truncate to 3 digits (milliseconds)
    }
    // Reconstruct: main part + dot + (truncated/original) digits + timezone part
    tempTimestamp = mainPart + '.' + digits + TzAwareRest;
  }

  return tempTimestamp;
};

export const getDataSourcePreferenceString = (state: DataSourceCheckboxState): string => {
  const selected: DataSourceIdentifier[] = [];
  if (state.dataset_wikipedia_en) selected.push('dataset_wikipedia_en');
  if (state.online_wikipedia) selected.push('online_wikipedia');
  if (state.online_wikinews) selected.push('online_wikinews');
  if (selected.length === 0) return 'online_wikipedia'; // Default if nothing selected
  return selected.join(',');
};

export const getCheckboxStateFromString = (
  prefString: string | null | undefined
): DataSourceCheckboxState => {
  const newState: DataSourceCheckboxState = {
    dataset_wikipedia_en: false,
    online_wikipedia: false,
    online_wikinews: false,
  };

  if (!prefString) {
    // If no preference string, default to dataset_wikipedia_en
    newState.dataset_wikipedia_en = true;
    return newState;
  }

  // Parse strings like "key1=true,key2=false"
  const prefs = prefString.split(',');
  prefs.forEach((pref) => {
    const [key, value] = pref.split('=');
    if (key in newState && value === 'true') {
      // Type-safe property assignment using keyof operator
      if (
        key === 'dataset_wikipedia_en' ||
        key === 'online_wikipedia' ||
        key === 'online_wikinews'
      ) {
        newState[key as keyof DataSourceCheckboxState] = true;
      }
    }
  });

  // Fallback: If parsing results in no selections, default to first option.
  const anySelected = Object.values(newState).some((v) => v);
  if (!anySelected) {
    newState.dataset_wikipedia_en = true;
  }

  return newState;
};

export const getDomainFromUrl = (url: string): string => {
  try {
    const urlObj = new URL(url);
    return urlObj.hostname.replace('www.', '');
  } catch {
    return 'External Source'; // Fallback for invalid URLs
  }
};

export const getDataSourceLabel = (url?: string | null): string => {
  if (!url) return '';
  const domain = getDomainFromUrl(url);
  if (domain.includes('wikipedia.org')) return 'Wikipedia';
  if (domain.includes('wikinews.org')) return 'Wikinews';
  // Consider a more robust check for "dataset" if it's not part of domain
  if (domain.includes('dataset') || url.includes('dataset_wikipedia_en')) return 'Dataset';
  return ''; // Return empty string if no specific label applies
};

export const getSourceLinkText = (title?: string | null, url?: string | null): string => {
  if (title && title.trim()) return title;
  if (url) {
    const domain = getDomainFromUrl(url);
    if (domain !== 'External Source') {
      // Avoid "View on External Source" if URL was invalid
      return `View on ${domain}`;
    }
  }
  return 'View Source'; // Default fallback
};

export const formatProgressTimestamp = (isoString: string | null | undefined): string => {
  if (!isoString) return '--:--:--'; // Return placeholder if isoString is null or undefined
  const date = new Date(isoString);
  // Check if the date is valid after parsing
  if (isNaN(date.getTime())) {
    console.warn(`[timelineUtils.ts] Invalid date string received: "${isoString}"`);
    return '--:--:--'; // Return placeholder for invalid date strings
  }

  const year = date.getFullYear();
  // getMonth() returns 0-11, so add 1 for 1-12
  const month = (date.getMonth() + 1).toString().padStart(2, '0');
  const day = date.getDate().toString().padStart(2, '0');

  const timePart = date.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false, // Use 24-hour format
  });

  return `${year}-${month}-${day} ${timePart}`;
};

export const formatEventDate = (dateDetails: ParsedDateInfo | null | undefined): string => {
  if (!dateDetails) {
    return '';
  }

  // Priority 1: Use the display_text provided by backend (which already has proper formatting)
  if (dateDetails.display_text && dateDetails.display_text.trim()) {
    return dateDetails.display_text;
  }

  // Priority 2: Fallback to computed date formatting if display_text is missing
  const startDateISO = getStartDateISO(dateDetails);
  if (!startDateISO) {
    return dateDetails.original_text || '';
  }

  try {
    const date = new Date(startDateISO);
    const options: Intl.DateTimeFormatOptions = {
      year: 'numeric',
      timeZone: 'UTC', // Ensure consistency with backend date calculations
    };

    // Add month/day formatting based on precision
    if (dateDetails.precision === 'month' || dateDetails.precision === 'day') {
      options.month = 'long';
    }
    if (dateDetails.precision === 'day') {
      options.day = 'numeric';
    }

    return new Intl.DateTimeFormat('en-US', options).format(date);
  } catch (error) {
    console.error(`[timelineUtils.ts] Error formatting date:`, dateDetails, error);
    // Final fallback to original text
    return dateDetails.original_text || '';
  }
};

export const getEventYear = (event: {
  date_info: ParsedDateInfo | null;
  event_date_str: string;
}): number => {
  // Priority 1: Use structured date_info if available
  if (event.date_info) {
    const startDateISO = getStartDateISO(event.date_info);
    if (startDateISO) {
      try {
        return new Date(startDateISO).getFullYear();
      } catch {
        // Fall through to fallback method
      }
    }
  }

  // Priority 2: Fallback to regex extraction from event_date_str
  const yearMatch = event.event_date_str.match(/\d{4}/);
  return yearMatch ? parseInt(yearMatch[0], 10) : 0;
};

// BCE dates get negative values, CE dates get positive values for proper chronological ordering
export const getChronologicalSortValue = (event: {
  date_info: ParsedDateInfo | null;
  event_date_str: string;
}): number => {
  // Priority 1: Use structured date_info if available
  if (event.date_info && event.date_info.start_year !== null) {
    const year = event.date_info.start_year;

    // For BCE dates, the year is already negative in our data structure
    // For very ancient dates (geological time), we need to handle the scale properly
    if (event.date_info.is_bce) {
      // BCE years are stored as negative values in our system
      // For geological time (millions of years), keep the full negative value
      return year;
    } else {
      // CE dates are positive
      return year;
    }
  }

  // Priority 2: Fallback to parsing from event_date_str
  const yearMatch = event.event_date_str.match(/\d{4}/);
  if (yearMatch) {
    const year = parseInt(yearMatch[0], 10);
    // Trust the backend's structured is_bce field
    const isBCE = event.date_info?.is_bce ?? false;
    return isBCE ? -year : year;
  }

  // Default fallback
  return 0;
};

// Helper function to format year with K/M/B notation for large numbers
const formatYearWithScale = (year: number, isBCE: boolean): string => {
  const absoluteYear = Math.abs(year);

  // Handle geological time scales (millions/billions of years)
  if (absoluteYear >= 1000000) {
    const millions = absoluteYear / 1000000;
    if (millions >= 1000) {
      const billions = millions / 1000;
      return isBCE ? `${billions.toFixed(1)}B BCE` : `${billions.toFixed(1)}B`;
    } else {
      return isBCE ? `${millions.toFixed(0)}M BCE` : `${millions.toFixed(0)}M`;
    }
  } else if (absoluteYear >= 10000) {
    // Handle thousands (10K and above) - simplify large numbers
    const thousands = absoluteYear / 1000;
    // If it's a round number of thousands, show without decimal
    if (absoluteYear % 1000 === 0) {
      return isBCE ? `${thousands}K BCE` : `${thousands}K`;
    } else {
      // For non-round thousands, decide whether to show decimal or round
      if (thousands >= 100) {
        // For very large numbers (100K+), round to nearest thousand
        return isBCE ? `${Math.round(thousands)}K BCE` : `${Math.round(thousands)}K`;
      } else {
        // For smaller numbers (10K-99K), show one decimal if needed
        const rounded = Math.round(thousands * 10) / 10;
        return isBCE ? `${rounded}K BCE` : `${rounded}K`;
      }
    }
  } else {
    // For regular years (under 10,000)
    return isBCE ? `${absoluteYear} BCE` : `${absoluteYear}`;
  }
};

// Display-friendly year formatting with K/M/B notation for large numbers
export const getDisplayYear = (event: {
  date_info: ParsedDateInfo | null;
  event_date_str: string;
}): string => {
  if (event.date_info) {
    // Priority 1: Use start_year if available
    if (event.date_info.start_year !== null) {
      return formatYearWithScale(event.date_info.start_year, event.date_info.is_bce);
    }

    // Priority 2: If start_year is null but end_year is available, use end_year
    if (event.date_info.end_year !== null) {
      return formatYearWithScale(event.date_info.end_year, event.date_info.is_bce);
    }

    // Priority 3: If no year information is available, use display_text from date_info
    // This provides a clean, human-readable format instead of the verbose original text
    if (event.date_info.display_text && event.date_info.display_text !== event.event_date_str) {
      return event.date_info.display_text;
    }
  }

  // Priority 4: Try to extract year from string
  const yearMatch = event.event_date_str.match(/\d{4}/);
  if (yearMatch) {
    const year = parseInt(yearMatch[0], 10);
    // Trust the backend's structured is_bce field
    const isBCE = event.date_info?.is_bce ?? false;
    return isBCE ? `${year} BCE` : `${year}`;
  }

  // Priority 5: If no year can be extracted, try to use a shortened version of the date string
  // Remove verbose time information and keep only the essential date part
  let shortenedDate = event.event_date_str;

  // Remove time zone information and detailed time stamps
  shortenedDate = shortenedDate.replace(
    /\b\d{1,2}:\d{2}:\d{2}\s*(am|pm)?\s*(EST|PST|UTC|GMT)?\s*(\([^)]+\))?\s*/gi,
    ''
  );

  // Remove parenthetical explanations
  shortenedDate = shortenedDate.replace(/\([^)]+\)/g, '');

  // Remove "on" prefix and clean up
  shortenedDate = shortenedDate.replace(/^on\s+/i, '').trim();

  // If we managed to shorten it significantly, use the shortened version
  if (shortenedDate.length < event.event_date_str.length * 0.6 && shortenedDate.length > 0) {
    return shortenedDate;
  }

  // Final fallback: return the original string or 'Unknown Date'
  return event.event_date_str || 'Unknown Date';
};

// Helper function to filter out events with invalid timeline positioning
const filterValidTimelineEvents = <
  T extends {
    date_info: ParsedDateInfo | null;
    event_date_str: string;
    id: string;
  },
>(
  events: T[]
): T[] => {
  return events.filter((event) => {
    // 1. date_info cannot be null/undefined
    if (!event.date_info) {
      console.debug(`[timelineUtils] Filtering out event ${event.id}: date_info is null/undefined`);
      return false;
    }

    // 2. precision cannot be 'unknown'
    if (event.date_info.precision === 'unknown') {
      console.debug(`[timelineUtils] Filtering out event ${event.id}: precision is 'unknown'`);
      return false;
    }

    // 3. At least start_year or end_year must be present (not null)
    if (event.date_info.start_year === null && event.date_info.end_year === null) {
      console.debug(
        `[timelineUtils] Filtering out event ${event.id}: both start_year and end_year are null`
      );
      return false;
    }

    return true;
  });
};

// Chronological sorting with BCE/CE boundary handling and invalid event filtering
export const sortEventsChronologically = <
  T extends {
    date_info: ParsedDateInfo | null;
    event_date_str: string;
    id: string;
  },
>(
  events: T[]
): T[] => {
  // First filter out events that cannot be positioned on timeline
  const validEvents = filterValidTimelineEvents(events);

  // Log filtering results for debugging
  const filteredCount = events.length - validEvents.length;
  if (filteredCount > 0) {
    console.info(
      `[timelineUtils] Filtered out ${filteredCount} events with invalid timeline positioning out of ${events.length} total events`
    );
  }

  return [...validEvents].sort((a, b) => {
    const sortValueA = getChronologicalSortValue(a);
    const sortValueB = getChronologicalSortValue(b);

    if (sortValueA !== sortValueB) {
      return sortValueA - sortValueB;
    }

    // If sort values are the same, try to use more detailed date information
    const aStartDate = a.date_info ? getStartDateISO(a.date_info) : null;
    const bStartDate = b.date_info ? getStartDateISO(b.date_info) : null;

    if (aStartDate && bStartDate) {
      return aStartDate.localeCompare(bStartDate);
    }

    // Final fallback: maintain consistent order by comparing IDs
    return a.id.localeCompare(b.id);
  });
};

export const getUniqueYearsForNavigation = <
  T extends {
    date_info: ParsedDateInfo | null;
    event_date_str: string;
  },
>(
  events: T[]
): string[] => {
  const yearSet = new Set<string>();

  events.forEach((event) => {
    const displayYear = getDisplayYear(event);
    yearSet.add(displayYear);
  });

  // Convert to array and sort chronologically
  const years = Array.from(yearSet);

  // Sort by chronological value for proper BCE/CE ordering
  return years.sort((a, b) => {
    // Parse the display year back to get sort value
    const parseDisplayYear = (displayYear: string): number => {
      // Match patterns like "123B BCE", "456M BCE", "789K BCE", "123 BCE", "123B", "456M", "789K", "123"
      const match = displayYear.match(/^(\d+(?:\.\d+)?)\s*([KMB])?\s*(BCE)?$/);
      if (match) {
        let value = parseFloat(match[1]);
        const scale = match[2];
        const isBCE = !!match[3]; // BCE is present

        if (scale === 'K') value *= 1000;
        else if (scale === 'M') value *= 1000000;
        else if (scale === 'B') value *= 1000000000;

        // BCE dates are negative, CE dates (no BCE suffix) are positive
        if (isBCE) value = -value;

        return value;
      }

      // Fallback parsing for edge cases
      const yearMatch = displayYear.match(/\d+/);
      const year = yearMatch ? parseInt(yearMatch[0], 10) : 0;
      const isBCE = displayYear.includes('BCE');
      return isBCE ? -year : year;
    };

    return parseDisplayYear(a) - parseDisplayYear(b);
  });
};
