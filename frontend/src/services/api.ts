import axios from 'axios';
import type {
  CreateTaskPayload,
  BackendTaskRecord,
  UpdateTaskSharingPayload,
  TaskResultResponse,
  WebSocketStatusMessage,
  WebSocketErrorMessage,
  WebSocketPreliminaryEventsMessage,
  WebSocketMessage,
  TimelineWebSocketCallbacks,
  TaskCompletedMessage,
  HistoricalProgressMessage,
  TaskFailedMessage,
} from '../types';

// Environment configuration
const VITE_API_BASE_URL = import.meta.env.VITE_API_BASE_URL;
const DEV_BACKEND_PORT = import.meta.env.VITE_DEV_BACKEND_PORT || 8080;
const WS_PROTOCOL_PROD = import.meta.env.VITE_WS_PROTOCOL_PROD || 'wss';
const WS_PROTOCOL_DEV = import.meta.env.VITE_WS_PROTOCOL_DEV || 'ws';

// Utility function to check if a hostname is an IP address
const isIpAddress = (hostname: string): boolean => {
  // IPv4 pattern
  const ipv4Pattern = /^(\d{1,3}\.){3}\d{1,3}$/;
  // IPv6 pattern (simplified)
  const ipv6Pattern = /^([0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}$/;

  return ipv4Pattern.test(hostname) || ipv6Pattern.test(hostname);
};

// Utility function to check if we need to add port number
const needsPort = (hostname: string): boolean => {
  return (
    hostname === 'localhost' ||
    hostname === '127.0.0.1' ||
    isIpAddress(hostname) ||
    import.meta.env.MODE === 'development'
  );
};

// Build API configuration
const buildApiConfig = () => {
  const currentHostname = window.location.hostname;
  const currentProtocol = window.location.protocol;

  // If explicit API base URL is set, use it directly
  if (VITE_API_BASE_URL && VITE_API_BASE_URL.trim() !== '') {
    const rawUrl = VITE_API_BASE_URL;
    const apiUrl = `${rawUrl}/api`;
    console.log(`[api.ts] Using explicit API_BASE_URL: ${apiUrl}`);
    return { apiUrl, rawUrl };
  }

  // Build URL based on current hostname
  const protocol = currentProtocol === 'https:' ? 'https:' : 'http:';
  const portPart = needsPort(currentHostname) ? `:${DEV_BACKEND_PORT}` : '';
  const rawUrl = `${protocol}//${currentHostname}${portPart}`;
  const apiUrl = `${rawUrl}/api`;

  console.log(`[api.ts] Auto-detected API_BASE_URL: ${apiUrl}`);
  return { apiUrl, rawUrl };
};

// Build WebSocket URL
const buildWebSocketUrl = () => {
  const currentHostname = window.location.hostname;
  const currentProtocol = window.location.protocol;

  // If explicit API base URL is set, derive WebSocket URL from it
  if (VITE_API_BASE_URL && VITE_API_BASE_URL.trim() !== '') {
    const url = new URL(VITE_API_BASE_URL);
    const wsProtocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${url.host}/api`;
    console.log(`[api.ts] Using explicit WebSocket URL: ${wsUrl}`);
    return wsUrl;
  }

  // Build WebSocket URL based on current hostname
  const wsProtocol = currentProtocol === 'https:' ? WS_PROTOCOL_PROD : WS_PROTOCOL_DEV;
  const portPart = needsPort(currentHostname) ? `:${DEV_BACKEND_PORT}` : '';
  const wsUrl = `${wsProtocol}://${currentHostname}${portPart}/api`;

  console.log(`[api.ts] Auto-detected WebSocket URL: ${wsUrl}`);
  return wsUrl;
};

// Initialize URLs
const { apiUrl: API_BASE_URL } = buildApiConfig();
const WS_BASE_URL = buildWebSocketUrl();

// Create axios instance
const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor: add auth token and error handling
api.interceptors.request.use(
  (config) => {
    // Auto-inject authentication token if available
    const token = localStorage.getItem('authToken');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    console.error('Request error:', error);
    return Promise.reject(error);
  }
);

// Unified error handling and authentication state management
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const errorMessage = error.response?.data?.detail || error.message || 'An error occurred';

    // Handle authentication errors
    if (error.response?.status === 401) {
      // Token is invalid or expired, remove it
      localStorage.removeItem('authToken');
      // Optionally trigger a global logout event or redirect
      console.warn('Authentication token expired or invalid. Please log in again.');
    }

    console.error('API Error:', errorMessage);
    // Log the full error response if available, for more detailed diagnostics
    if (error.response && error.response.data) {
      console.error('Full API Error Response:', error.response.data);
    }
    // Ensure a proper Error object is rejected, potentially with more details
    if (error.response?.data?.detail && typeof error.response.data.detail === 'string') {
      return Promise.reject(new Error(error.response.data.detail));
    } else if (error.response?.data && typeof error.response.data === 'object') {
      // If the detail is an object or array, stringify it or pick a relevant field
      // For now, stringifying to capture all details.
      try {
        const detailedMessage = JSON.stringify(error.response.data);
        return Promise.reject(new Error(detailedMessage));
      } catch (_e) {
        return Promise.reject(new Error(`API error with complex data structure. ${_e}`));
      }
    }
    return Promise.reject(new Error(errorMessage));
  }
);

export const createTask = async (payload: CreateTaskPayload): Promise<BackendTaskRecord> => {
  try {
    console.log('[api.ts] createTask payload to be sent to backend:', payload);
    const response = await api.post<BackendTaskRecord>('/tasks/', payload);
    return response.data;
  } catch (error) {
    console.error('Failed to create task:', error);
    if (axios.isAxiosError(error) && error.response) {
      throw new Error(error.response.data.detail || 'Failed to create task');
    }
    throw error;
  }
};

export const createEntityCanonicalTask = async (
  entityId: string,
  payload: CreateTaskPayload
): Promise<BackendTaskRecord> => {
  try {
    const requestPayload = {
      entity_id: entityId,
      config: payload.config,
      is_public: payload.is_public,
    };
    console.log(
      '[api.ts] createEntityCanonicalTask payload to be sent to backend:',
      requestPayload
    );
    const response = await api.post<BackendTaskRecord>(
      `/tasks/from-entity/${entityId}`,
      requestPayload
    );
    return response.data;
  } catch (error) {
    console.error('Failed to create entity canonical task:', error);
    if (axios.isAxiosError(error) && error.response) {
      throw new Error(error.response.data.detail || 'Failed to create entity canonical task');
    }
    throw error;
  }
};

export const createDocumentCanonicalTask = async (
  sourceDocumentId: string,
  payload: CreateTaskPayload
): Promise<BackendTaskRecord> => {
  try {
    const requestPayload = {
      source_document_id: sourceDocumentId,
      config: payload.config,
      is_public: payload.is_public,
    };
    console.log(
      '[api.ts] createDocumentCanonicalTask payload to be sent to backend:',
      requestPayload
    );
    const response = await api.post<BackendTaskRecord>(
      `/tasks/from-document/${sourceDocumentId}`,
      requestPayload
    );
    return response.data;
  } catch (error) {
    console.error('Failed to create document canonical task:', error);
    if (axios.isAxiosError(error) && error.response) {
      throw new Error(error.response.data.detail || 'Failed to create document canonical task');
    }
    throw error;
  }
};

export const getTasks = async (options?: {
  status?: string;
  owned_by_me?: boolean;
  limit?: number;
  offset?: number;
}): Promise<BackendTaskRecord[]> => {
  try {
    const params = new URLSearchParams();
    if (options?.status) {
      params.append('status', options.status);
    }
    if (options?.owned_by_me !== undefined) {
      params.append('owned_by_me', String(options.owned_by_me));
    }
    if (options?.limit !== undefined) {
      params.append('limit', options.limit.toString());
    }
    if (options?.offset !== undefined) {
      params.append('offset', options.offset.toString());
    }

    const url = `/tasks/${params.toString() ? '?' + params.toString() : ''}`;
    const response = await api.get<BackendTaskRecord[]>(url);

    // The backend now returns data matching the BackendTaskRecord interface directly.
    return response.data;
  } catch (error) {
    console.error('Failed to get tasks:', error);
    if (axios.isAxiosError(error) && error.response) {
      throw new Error(error.response.data.detail || 'Failed to get tasks');
    }
    throw error;
  }
};

export const getPublicTimelines = async (options?: {
  limit?: number;
  offset?: number;
}): Promise<BackendTaskRecord[]> => {
  try {
    const params = new URLSearchParams();
    if (options?.limit !== undefined) {
      params.append('limit', options.limit.toString());
    }
    if (options?.offset !== undefined) {
      params.append('offset', options.offset.toString());
    }

    const url = `/public/timelines${params.toString() ? '?' + params.toString() : ''}`;
    const response = await api.get<BackendTaskRecord[]>(url);

    return response.data;
  } catch (error) {
    console.error('Failed to get public timelines:', error);
    if (axios.isAxiosError(error) && error.response) {
      throw new Error(error.response.data.detail || 'Failed to get public timelines');
    }
    throw error;
  }
};

export const getTaskResult = async (taskId: string): Promise<TaskResultResponse> => {
  try {
    // Ensure the endpoint /tasks/{task_id}/result matches the backend route
    const response = await api.get<TaskResultResponse>(`/tasks/${taskId}/result`);
    return response.data;
  } catch (error) {
    console.error(`Failed to get result for task ${taskId}:`, error);
    if (axios.isAxiosError(error) && error.response) {
      throw new Error(error.response.data.detail || `Failed to get result for task ${taskId}`);
    }
    throw error;
  }
};

export const updateTaskSharing = async (
  taskId: string,
  payload: UpdateTaskSharingPayload
): Promise<TaskResultResponse> => {
  try {
    const response = await api.patch<TaskResultResponse>(`/tasks/${taskId}/sharing`, payload);
    return response.data;
  } catch (error) {
    console.error(`Failed to update sharing for task ${taskId}:`, error);
    if (axios.isAxiosError(error) && error.response) {
      throw new Error(error.response.data.detail || 'Failed to update task sharing status');
    }
    throw error;
  }
};

// --- WebSocket Communication for Timeline Generation ---

// --- START New WebSocket function for Task-Specific Updates ---
// WebSocket connection with automatic reconnection and error handling
export const getTimelineUpdatesWS = (taskId: string, callbacks: TimelineWebSocketCallbacks) => {
  const wsUrl = `${WS_BASE_URL}/ws/timeline/from_task/${taskId}`;
  console.log(`[api.ts] Connecting to Task WebSocket: ${wsUrl}`);

  let socket: WebSocket | null = null;
  // currentRequestId might not be needed here if task_id itself is the identifier in messages
  // Or, if messages still use a separate request_id, callbacks.onOpen can provide it.

  const connectWebSocket = (url: string) => {
    socket = new WebSocket(url);

    socket.onopen = () => {
      console.log(`[api.ts] Task WebSocket connection established to ${url}`);
      // No initial message to send, server knows the task_id from the URL.
      // The backend's on_connect for this specific WS route should handle associating the connection with the task.
      // If a specific request_id is generated by the server upon connection and sent back,
      // the onOpen callback could be used to capture it, if it's different from taskId.
      // For now, we assume taskId is the primary identifier or messages will carry their own request_id.
      if (callbacks.onOpen) {
        // If the server sends back a specific request_id upon opening the task-specific WS,
        // it would be part of a message. For now, let's assume task_id is sufficient context
        // or the messages themselves will contain a request_id.
        // We can pass the taskId itself if the onOpen callback expects an identifier.
        callbacks.onOpen(taskId); // Or a specific request_id if server sends one immediately.
      }
    };

    socket.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data as string) as WebSocketMessage;
        console.log('[api.ts] Task WebSocket message received:', message);

        switch (message.type) {
          case 'status':
            if (callbacks.onStatusUpdate) {
              callbacks.onStatusUpdate(message as WebSocketStatusMessage);
            }
            break;
          case 'preliminary_events':
            if (callbacks.onPreliminaryEvents) {
              callbacks.onPreliminaryEvents(message as WebSocketPreliminaryEventsMessage);
            }
            break;
          case 'error':
            if (callbacks.onError) {
              callbacks.onError(message as WebSocketErrorMessage);
            }
            break;
          case 'historical_progress': {
            console.log('[api.ts] Received historical progress:', message);
            if (callbacks.onHistoricalProgress) {
              callbacks.onHistoricalProgress(message as HistoricalProgressMessage);
            }
            break;
          }
          case 'task_completed':
            if (callbacks.onTaskCompleted) {
              callbacks.onTaskCompleted(message as TaskCompletedMessage);
            }
            break;
          case 'task_failed': {
            console.log('[api.ts] Task failed:', message);
            if (callbacks.onTaskFailed) {
              callbacks.onTaskFailed(message as TaskFailedMessage);
            }
            break;
          }
          default: {
            // This can be a type guard for exhaustiveness checking
            const _exhaustiveCheck: never = message;
            console.warn(
              '[api.ts] Received unknown Task WebSocket message type:',
              _exhaustiveCheck
            );
          }
        }
      } catch (e) {
        console.error('[api.ts] Error parsing Task WebSocket message or in callback:', e);
        if (callbacks.onError) {
          callbacks.onError({
            type: 'error',
            message: 'Failed to process message from server.',
            request_id: taskId,
          });
        }
      }
    };

    socket.onerror = (errorEvent) => {
      console.error('[api.ts] Task WebSocket error:', errorEvent);
      if (callbacks.onError) {
        callbacks.onError({
          type: 'error',
          message: 'WebSocket connection error.',
          request_id: taskId,
        });
      }
      // Attempt to reconnect if not a deliberate close? For now, no auto-reconnect.
    };

    socket.onclose = (closeEvent) => {
      console.log(
        `[api.ts] Task WebSocket connection closed. Code: ${closeEvent.code}, Reason: ${closeEvent.reason}`
      );
      if (callbacks.onClose) {
        callbacks.onClose(closeEvent);
      }
      socket = null; // Clear the socket instance
    };
  };

  connectWebSocket(wsUrl);

  return {
    close: () => {
      if (socket && socket.readyState === WebSocket.OPEN) {
        console.log('[api.ts] Closing Task WebSocket connection.');
        socket.close();
      }
      socket = null; // Ensure it's cleared on manual close too
    },
    getSocket: () => socket,
  };
};
// --- END New WebSocket function for Task-Specific Updates ---

// --- Authentication API Functions ---

export const loginUser = async (username: string, password: string) => {
  try {
    const response = await api.post('/auth/login', {
      username,
      password,
    });

    if (response.status === 200) {
      return { success: true, data: response.data };
    } else {
      return { success: false, error: response.data.detail || 'Login failed' };
    }
  } catch (error) {
    console.error('Login error:', error);
    if (axios.isAxiosError(error) && error.response) {
      return { success: false, error: error.response.data.detail || 'Login failed' };
    }
    return { success: false, error: 'Network error or server unavailable' };
  }
};

export const registerUser = async (username: string, password: string) => {
  try {
    const response = await api.post('/auth/register', {
      username,
      password,
    });

    if (response.status === 200 || response.status === 201) {
      return { success: true, data: response.data };
    } else {
      return { success: false, error: response.data.detail || 'Registration failed' };
    }
  } catch (error) {
    console.error('Registration error:', error);
    if (axios.isAxiosError(error) && error.response) {
      return { success: false, error: error.response.data.detail || 'Registration failed' };
    }
    return { success: false, error: 'Network error or server unavailable' };
  }
};

export const getCurrentUser = async (token: string) => {
  try {
    const response = await api.get('/auth/me', {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });

    if (response.status === 200) {
      return { success: true, data: response.data };
    } else {
      return { success: false, error: 'Failed to get user info' };
    }
  } catch (error) {
    console.error('Get current user error:', error);
    if (axios.isAxiosError(error) && error.response) {
      return { success: false, error: error.response.data.detail || 'Failed to get user info' };
    }
    return { success: false, error: 'Network error or server unavailable' };
  }
};
