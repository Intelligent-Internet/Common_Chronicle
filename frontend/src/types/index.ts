// Centralized type definitions for the Common Chronicle frontend

export interface ProcessedEntityInfo {
  entity_id: string | null;
  original_name: string;
  entity_type: string;
  is_verified_existent?: boolean | null;
}

export interface ParsedDateInfo {
  original_text: string;
  display_text: string;
  precision: 'day' | 'month' | 'year' | 'decade' | 'century' | 'millennium' | 'era' | 'unknown';
  start_year: number | null;
  start_month: number | null;
  start_day: number | null;
  end_year: number | null;
  end_month: number | null;
  end_day: number | null;
  is_bce: boolean;
}

// Simplified helper functions for ParsedDateInfo date calculations
// These mirror the backend logic in ParsedDateInfo.to_date_range()
export function getStartDateISO(dateInfo: ParsedDateInfo): string | null {
  if (!dateInfo.start_year) return null;

  const year = dateInfo.start_year;
  const month = dateInfo.start_month || 1;
  const day = dateInfo.start_day || 1;

  try {
    // Use UTC constructor to avoid timezone offset issues
    return new Date(Date.UTC(year, month - 1, day)).toISOString().split('T')[0];
  } catch {
    return null;
  }
}

export function getEndDateISO(dateInfo: ParsedDateInfo): string | null {
  if (!dateInfo.start_year) return null;

  let endYear = dateInfo.end_year || dateInfo.start_year;
  let endMonth = dateInfo.end_month || dateInfo.start_month || 1;
  let endDay = dateInfo.end_day || dateInfo.start_day || 1;

  // Apply precision-based expansion logic (matching backend)
  switch (dateInfo.precision) {
    case 'year':
      endMonth = 12;
      endDay = 31;
      break;
    case 'month':
      if (!dateInfo.end_day) {
        // Get last day of the month using UTC
        const tempDate = new Date(Date.UTC(endYear, endMonth, 0));
        endDay = tempDate.getUTCDate();
      }
      break;
    case 'decade':
      endYear = dateInfo.start_year + 9;
      endMonth = 12;
      endDay = 31;
      break;
    case 'century':
      endYear = dateInfo.start_year + 99;
      endMonth = 12;
      endDay = 31;
      break;
    case 'millennium':
      endYear = dateInfo.start_year + 999;
      endMonth = 12;
      endDay = 31;
      break;
    // For "day", "era", "unknown" - use the provided values or defaults
  }

  try {
    // Use UTC constructor to avoid timezone offset issues
    return new Date(Date.UTC(endYear, endMonth - 1, endDay)).toISOString().split('T')[0];
  } catch {
    return null;
  }
}

export interface EventSourceInfo {
  // Renamed from EventSourceInfoForFrontend
  source_language: string;
  source_page_title: string | null;
  source_url: string | null;
  source_document_id: string | null; // Add source document ID for document timeline creation
  source_type: string | null; // Type of source (dataset_wikipedia_en/online_wikipedia/online_wikinews)
}

// LLMRequestForFrontend and LLMResponseForFrontend from timeline.ts
// will be reconciled with LLMRequest and LLMResponse from api.ts later.
// For now, focus on types that are clearly moving.

export interface TimelineEvent {
  id: string;
  event_date_str: string;
  description: string;
  main_entities: ProcessedEntityInfo[];
  date_info: ParsedDateInfo | null;
  is_merged: boolean;
  source_snippets: Record<string, string | null>; // source_ref -> snippet mapping
  viewpoint_id: string | null;
  created_at: string;
  updated_at: string;

  relevance_score?: number | null; // Relevance score for filtering and ranking
}

export interface LLMRequest {
  model: string;
  system_prompt: string;
  user_prompt: string;
}

export interface LLMResponse {
  raw_response: string;
  model: string;
  usage?: Record<string, number> | null;
}

export interface TimelineResponseWrapper {
  events: TimelineEvent[];
}

export interface TaskError {
  message: string;
  step?: string;
  requestId?: string;
  statusCode?: number;
}

export interface WebSocketStatusMessage {
  type: 'status';
  message: string;
  step: string;
  timestamp?: string;
  data?: Record<string, unknown>;
  request_id: string;
}

export interface WebSocketErrorMessage {
  type: 'error';
  message: string;
  step?: string;
  request_id: string;
  status_code?: number;
}

export interface WebSocketPreliminaryEventsMessage {
  type: 'preliminary_events';
  events: TimelineEvent[];
  message: string;
  request_id: string;
  timestamp?: string;
}

export interface TaskCompletedMessage {
  type: 'task_completed';
  message: string;
  task_id: string;
  request_id: string;
  timestamp: string;
}

export interface TaskFailedMessage {
  type: 'task_failed';
  message: string;
  task_id: string;
  request_id: string;
  error?: string;
}

export interface HistoricalProgressMessage {
  type: 'historical_progress';
  steps: WebSocketStatusMessage[];
  request_id: string;
}

export type WebSocketMessage =
  | WebSocketStatusMessage
  | WebSocketErrorMessage
  | WebSocketPreliminaryEventsMessage
  | TaskCompletedMessage
  | TaskFailedMessage
  | HistoricalProgressMessage;

export interface TimelineWebSocketCallbacks {
  onOpen?: (requestId: string) => void;
  onStatusUpdate?: (status: WebSocketStatusMessage) => void;
  onHistoricalProgress?: (progress: HistoricalProgressMessage) => void;
  onPreliminaryEvents?: (preliminaryEvents: WebSocketPreliminaryEventsMessage) => void;
  onTaskCompleted?: (completion: TaskCompletedMessage) => void;
  onTaskFailed?: (failure: TaskFailedMessage) => void;
  onError?: (
    error: WebSocketErrorMessage | { type: 'error'; message: string; request_id?: string }
  ) => void;
  onClose?: (event: CloseEvent) => void;
}

export type DataSourceIdentifier = 'dataset_wikipedia_en' | 'online_wikipedia' | 'online_wikinews';

export type DataSourcePreference = string; // Alias for semantic clarity

export interface CreateEventPayload {
  event_description: string;
  start_date?: string | null;
  end_date?: string | null;
  main_entities: ProcessedEntityInfo[];
  source_url?: string | null;
  source_text_snippet?: string | null;
  confidence_score?: number | null;
  keywords?: string[] | null;
}

export interface CreateEventResponse {
  message: string;
  event_id: number; // Assuming this is correct from backend, was event_id: number, looks like an int
  successfully_linked_entities_count: number;
  entity_processing_summary_from_request: ProcessedEntityInfo[];
}

// --- Types previously in frontend/src/utils/timelineUtils.ts ---
// Will be added in the next step

export interface DataSourceCheckboxState {
  dataset_wikipedia_en: boolean;
  online_wikipedia: boolean;
  online_wikinews: boolean;
}

export interface TaskFormData {
  topic_text: string;
  data_source_pref: string;
  is_public?: boolean;
}

// --- START: API Data Structure Types ---

export interface UserInfo {
  id: string;
  username: string;
  created_at: string;
}

export interface BackendTaskRecord {
  id: string;
  topic_text: string | null; // Made nullable for canonical tasks
  task_type: 'synthetic_viewpoint' | 'entity_canonical' | 'document_canonical';
  entity_id: string | null;
  source_document_id: string | null;
  owner: UserInfo | null;
  is_public: boolean;
  status: 'pending' | 'processing' | 'completed' | 'failed' | string;
  viewpoint_id: string | null;
  processing_duration: number | null;
  config: {
    data_source_preference?: string;
  } | null;
  notes: string | null;
  created_at: string; // ISO date string
  updated_at: string; // ISO date string
  processed_at: string | null;
  progress_messages: WebSocketStatusMessage[] | null;
}

export interface ViewpointProgressStepInfo {
  id: string;
  step_name: string;
  message: string;
  event_timestamp: string;
}

export interface ViewpointInfo {
  id: string;
  status: string;
  topic: string;
  viewpoint_type: string;
  data_source_preference: string;
  canonical_source_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ViewpointDetailResponse {
  viewpoint: ViewpointInfo;
  progress_steps: ViewpointProgressStepInfo[];
  sources: Record<string, EventSourceInfo>; // Dictionary of source references
  timeline_events: TimelineEvent[];
}

export interface CreateTaskPayload {
  topic_text?: string;
  config?: {
    data_source_preference?: string;
  };
  is_public?: boolean;
}

export interface UpdateTaskSharingPayload {
  is_public: boolean;
}

export interface TaskResultResponse extends BackendTaskRecord {
  // Inherits all fields from BackendTaskRecord for consistency
  // and adds the detailed viewpoint information.
  // The 'progress_messages' from BackendTaskRecord is effectively for the simple /task/{id} GET,
  // while the raw steps are in viewpoint_details.progress_steps.
  viewpoint_details: ViewpointDetailResponse | null;
}

// NOTE: GetCachedTaskResultsOutput is deprecated and removed.
// The caching service will now store and retrieve objects that conform to TaskResultResponse.
