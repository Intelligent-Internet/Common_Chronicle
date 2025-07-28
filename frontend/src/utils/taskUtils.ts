import { createEntityCanonicalTask, createDocumentCanonicalTask } from '../services/api';
import type { CreateTaskPayload, BackendTaskRecord } from '../types';

/**
 * Creates a canonical task and opens it in a new tab
 * @param type - Task type ('entity' or 'document')
 * @param id - Entity ID or Source Document ID
 * @param options - Optional configuration including advanced config
 * @returns Promise<BackendTaskRecord>
 */
export const createAndOpenCanonicalTask = async (
  type: 'entity' | 'document',
  id: string,
  options?: {
    config?: {
      data_source_preference?: string;
      // Advanced configuration parameters
      article_limit?: number;
      timeline_relevance_threshold?: number;
      reuse_composite_viewpoint?: boolean;
      reuse_base_viewpoint?: boolean;
      search_mode?: 'semantic' | 'hybrid_title_search';
      vector_weight?: number;
      bm25_weight?: number;
    };
    is_public?: boolean;
  }
): Promise<BackendTaskRecord> => {
  // Open new tab immediately to avoid popup blockers
  const newTab = window.open('', '_blank');

  try {
    let createdTask: BackendTaskRecord;

    if (type === 'entity') {
      const payload: CreateTaskPayload = {
        config: options?.config || { data_source_preference: 'default' },
        is_public: options?.is_public || false,
      };
      createdTask = await createEntityCanonicalTask(id, payload);
    } else {
      const payload: CreateTaskPayload = {
        config: options?.config || { data_source_preference: 'default' },
        is_public: options?.is_public || false,
      };
      createdTask = await createDocumentCanonicalTask(id, payload);
    }

    // Set the URL of the new tab
    if (newTab) {
      newTab.location.href = `/task/${createdTask.id}`;
    } else {
      // Fallback if popup was blocked
      window.open(`/task/${createdTask.id}`, '_blank');
    }

    return createdTask;
  } catch (error) {
    // Close the blank tab if task creation failed
    if (newTab) {
      newTab.close();
    }
    throw error;
  }
};

/**
 * Gets a user-friendly task type display name
 * @param taskType - The task type string, can be null/undefined
 * @returns User-friendly display name
 */
export const getTaskTypeDisplayName = (taskType: string | null | undefined): string => {
  if (!taskType) return 'Unknown Type';

  switch (taskType) {
    case 'synthetic_viewpoint':
      return 'Synthetic Viewpoint';
    case 'entity_canonical':
      return 'Entity Timeline';
    case 'document_canonical':
      return 'Document Timeline';
    default:
      return 'Unknown Type';
  }
};

/**
 * Gets a user-friendly task source description
 */
export const getTaskSourceDescription = (task: BackendTaskRecord): string => {
  switch (task.task_type) {
    case 'synthetic_viewpoint':
      return task.topic_text || 'Synthetic viewpoint';
    case 'entity_canonical':
      return `Entity: ${task.entity_id || 'Unknown'}`;
    case 'document_canonical':
      return `Document: ${task.source_document_id || 'Unknown'}`;
    default:
      return 'Unknown source';
  }
};

/**
 * Gets user-friendly data source display names
 * @param dataSourcePref - Data source preference string (can be comma-separated)
 * @returns Array of user-friendly source names
 */
export const getDataSourceDisplayNames = (dataSourcePref: string | null | undefined): string[] => {
  if (!dataSourcePref || dataSourcePref === 'default') {
    return ['Default Sources'];
  }

  // Handle comma-separated multiple sources
  const sources = dataSourcePref.split(',').map((source) => source.trim());
  return sources.map((source) => {
    switch (source) {
      case 'dataset_wikipedia_en':
        return 'Dataset Wikipedia (EN)';
      case 'online_wikipedia':
        return 'Online Wikipedia';
      case 'online_wikinews':
        return 'Online Wikinews';
      default:
        return source; // Fallback to original string
    }
  });
};
