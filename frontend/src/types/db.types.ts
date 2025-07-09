import type { TimelineEvent, WebSocketStatusMessage, DataSourcePreference } from './index';

export interface UserTaskRecord {
  id: string;
  viewpoint: string;
  dataSourcePref: DataSourcePreference;
  // For debugging and server log correlation
  serverRequestId?: string | null;
  finalEvents?: TimelineEvent[] | null;
  // Cleared when finalEvents arrive
  preliminaryEvents?: TimelineEvent[] | null;
  progressMessages?: WebSocketStatusMessage[] | null;
  error?: {
    message: string;
    step?: string;
    requestId?: string | null;
    statusCode?: number;
  } | null;
  createdAt: string;
  // LRU cache eviction based on last access
  lastAccessedAt: string;
  updatedAt: string;
  completedAt?: string | null;
  // Complete if has finalEvents or error
  isComplete: boolean;
  status: string;
}
