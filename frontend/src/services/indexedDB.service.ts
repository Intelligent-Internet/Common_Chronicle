// frontend/src/services/indexedDB.service.ts
import { openDB } from 'idb';
import type { DBSchema, IDBPDatabase } from 'idb';
import type { UserTaskRecord } from '../types/db.types';
import type { BackendTaskRecord, TaskResultResponse } from '../types';
import { sortEventsChronologically } from '../utils/timelineUtils';

const DB_NAME = 'CommonTimelineDB';
const DB_VERSION = 4;
const TASK_STORE_NAME = 'userTasks';
const TASK_RESULTS_STORE_NAME = 'taskResultsCache';

interface CachedTaskResult {
  taskId: string;
  taskData: TaskResultResponse;
  timestamp: Date;
}

export interface ExtendedUserTaskRecord extends UserTaskRecord {
  isPublic: number; // 0 for false, 1 for true
  taskType: 'synthetic_viewpoint' | 'entity_canonical' | 'document_canonical' | null;
}

interface TimelineDBSchema extends DBSchema {
  [TASK_STORE_NAME]: {
    key: string;
    value: ExtendedUserTaskRecord;
    indexes: {
      viewpoint: string;
      dataSourcePref: string;
      createdAt: string;
      lastAccessedAt: string;
      isComplete: string;
      completedAt: string;
      isPublic: number;
    };
  };
  [TASK_RESULTS_STORE_NAME]: {
    key: string;
    value: CachedTaskResult;
    indexes: {
      timestamp: string;
    };
  };
}

let dbPromise: Promise<IDBPDatabase<TimelineDBSchema>> | null = null;

const getDb = (): Promise<IDBPDatabase<TimelineDBSchema>> => {
  if (!dbPromise) {
    dbPromise = openDB<TimelineDBSchema>(DB_NAME, DB_VERSION, {
      upgrade(db, oldVersion, newVersion, _transaction) {
        console.log(`Upgrading DB from version ${oldVersion} to ${newVersion}`);
        if (oldVersion < 1) {
          if (!db.objectStoreNames.contains(TASK_STORE_NAME)) {
            const store = db.createObjectStore(TASK_STORE_NAME, {
              keyPath: 'id',
            });
            store.createIndex('viewpoint', 'viewpoint', { unique: false });
            store.createIndex('dataSourcePref', 'dataSourcePref', { unique: false });
            store.createIndex('createdAt', 'createdAt', { unique: false });
            store.createIndex('lastAccessedAt', 'lastAccessedAt', { unique: false });
            store.createIndex('isComplete', 'isComplete', { unique: false });
            store.createIndex('completedAt', 'completedAt', { unique: false });
            console.log(`Object store ${TASK_STORE_NAME} created.`);
          }
        }
        if (oldVersion < 2) {
          if (!db.objectStoreNames.contains(TASK_RESULTS_STORE_NAME)) {
            const resultsStore = db.createObjectStore(TASK_RESULTS_STORE_NAME, {
              keyPath: 'taskId',
            });
            resultsStore.createIndex('timestamp', 'timestamp', { unique: false });
            console.log(`Object store ${TASK_RESULTS_STORE_NAME} created.`);
          }
        }
        if (oldVersion < 3) {
          console.log('Running upgrade for version 3');
          const store = _transaction.objectStore(TASK_STORE_NAME);
          if (!store.indexNames.contains('isPublic')) {
            store.createIndex('isPublic', 'isPublic', { unique: false });
            console.log(`Index 'isPublic' created on store ${TASK_STORE_NAME}.`);
          }
        }
        if (oldVersion < 4) {
          console.log('Running upgrade for version 4 - adding taskType field');
          // No schema changes needed, taskType field will be added automatically
          // when existing records are updated through normal operations
        }
      },
    });
  }
  return dbPromise;
};

export const cacheTask = async (taskData: UserTaskRecord): Promise<string> => {
  const db = await getDb();
  if (!taskData.lastAccessedAt) {
    taskData.lastAccessedAt = taskData.createdAt;
  }
  try {
    const tx = db.transaction(TASK_STORE_NAME, 'readwrite');
    // Add isPublic flag for regular tasks
    const recordToCache: ExtendedUserTaskRecord = {
      ...taskData,
      isPublic: 0, // Default to not public
      taskType: null, // Task type not available for manually cached tasks
    };
    await tx.store.put(recordToCache);
    await tx.done;
    console.log(`[DB] Task cached/updated: ${taskData.id}`);
    return taskData.id;
  } catch (error) {
    console.error(`[DB] Error caching task ${taskData.id}:`, error);
    throw error;
  }
};

export const getTaskById = async (id: string): Promise<ExtendedUserTaskRecord | undefined> => {
  const db = await getDb();
  const task = await db.get(TASK_STORE_NAME, id);
  if (task) {
    await updateTaskAccessTime(id, db);
  }
  return task;
};

export const updateTaskAccessTime = async (
  id: string,
  dbInstance?: IDBPDatabase<TimelineDBSchema>
): Promise<void> => {
  const db = dbInstance || (await getDb());
  const tx = db.transaction(TASK_STORE_NAME, 'readwrite');
  const store = tx.objectStore(TASK_STORE_NAME);
  const task = await store.get(id);
  if (task) {
    task.lastAccessedAt = new Date().toISOString();
    await store.put(task);
    await tx.done;
    console.log(`[DB] Updated lastAccessedAt for task: ${id}`);
  } else {
    console.warn(`[DB] Task not found for updating access time: ${id}`);
  }
};

export const findTasksByViewpoint = async (
  viewpoint: string,
  dataSourcePref?: UserTaskRecord['dataSourcePref']
): Promise<UserTaskRecord[]> => {
  const db = await getDb();
  const tx = db.transaction(TASK_STORE_NAME, 'readonly');
  const store = tx.objectStore(TASK_STORE_NAME);
  const index = store.index('viewpoint');

  const allWithViewpoint = await index.getAll(viewpoint);

  let results: UserTaskRecord[];
  if (dataSourcePref) {
    results = allWithViewpoint.filter((task) => task.dataSourcePref === dataSourcePref);
  } else {
    results = allWithViewpoint;
    console.warn(
      '[DB] findTasksByViewpoint called without dataSourcePref. Returning all for viewpoint.'
    );
  }

  results.sort(
    (a, b) => new Date(b.lastAccessedAt).getTime() - new Date(a.lastAccessedAt).getTime()
  );

  console.log(
    `[DB] Found ${results.length} tasks for viewpoint: "${viewpoint}"` +
      (dataSourcePref ? ` and pref: ${dataSourcePref}` : '')
  );
  return results;
};

export const getRecentCompletedTasks = async (limit: number = 10): Promise<UserTaskRecord[]> => {
  const db = await getDb();
  const tx = db.transaction(TASK_STORE_NAME, 'readonly');
  const store = tx.objectStore(TASK_STORE_NAME);
  const index = store.index('completedAt');

  const tasks: UserTaskRecord[] = [];
  let cursor = await index.openCursor(null, 'prev');

  while (cursor && tasks.length < limit) {
    if (cursor.value.isComplete) {
      tasks.push(cursor.value);
    }
    cursor = await cursor.continue();
  }

  console.log(`[DB] Retrieved ${tasks.length} recent completed tasks.`);
  return tasks;
};

export const partialUpdateTask = async (
  taskId: string,
  updates: Partial<Omit<UserTaskRecord, 'id'>>
): Promise<void> => {
  const db = await getDb();
  const tx = db.transaction(TASK_STORE_NAME, 'readwrite');
  const store = tx.objectStore(TASK_STORE_NAME);
  const currentTask = await store.get(taskId);

  if (currentTask) {
    const updatedTask = { ...currentTask, ...updates };

    await store.put(updatedTask);
    await tx.done;
    console.log(
      `[DB] Partially updated task: ${taskId} with keys: ${Object.keys(updates).join(', ')}`
    );
  } else {
    console.warn(`[DB] Task not found for partial update: ${taskId}`);
  }
};

export const clearOldTasks = async (maxAgeDays: number): Promise<number> => {
  const db = await getDb();
  const thresholdDate = new Date();
  thresholdDate.setDate(thresholdDate.getDate() - maxAgeDays);
  const thresholdISO = thresholdDate.toISOString();

  let deleteCount = 0;
  const tx = db.transaction(TASK_STORE_NAME, 'readwrite');
  const store = tx.objectStore(TASK_STORE_NAME);
  const index = store.index('createdAt');

  let cursor = await index.openCursor(IDBKeyRange.upperBound(thresholdISO));
  while (cursor) {
    await cursor.delete();
    deleteCount++;
    cursor = await cursor.continue();
  }
  await tx.done;
  if (deleteCount > 0) {
    console.log(`[DB] Cleared ${deleteCount} tasks older than ${maxAgeDays} days.`);
  }
  return deleteCount;
};

export async function getTaskResultFromCache(taskId: string): Promise<TaskResultResponse | null> {
  const db = await getDb();
  try {
    const cachedResult = await db.get(TASK_RESULTS_STORE_NAME, taskId);
    if (cachedResult) {
      console.log(`[DB] Cache hit for task results: ${taskId}`);
      // The entire TaskResultResponse object is stored in taskData.
      return cachedResult.taskData;
    }
    console.log(`[DB] Cache miss for task results: ${taskId}`);
    return null;
  } catch (error) {
    console.error(`[DB] Error fetching cached task results for ${taskId}:`, error);
    return null;
  }
}

export async function cacheTaskResults(taskData: TaskResultResponse): Promise<void> {
  // Ensure the task data has a valid ID.
  if (!taskData.id) {
    console.error('[DB] Cannot cache task results without a valid ID.', taskData);
    return;
  }

  // Do not cache results for tasks that are still running or have no events.
  if (
    !taskData.viewpoint_details ||
    (taskData.status !== 'completed' && taskData.status !== 'failed')
  ) {
    console.log(
      `[DB] Skipping cache for task ${taskData.id} because it is not completed or has no viewpoint details.`
    );
    return;
  }

  // Ensure events are sorted before caching.
  if (taskData.viewpoint_details.timeline_events) {
    taskData.viewpoint_details.timeline_events = sortEventsChronologically(
      taskData.viewpoint_details.timeline_events
    );
  }

  const db = await getDb();
  const recordToCache: CachedTaskResult = {
    taskId: taskData.id,
    taskData: taskData,
    timestamp: new Date(),
  };

  try {
    const tx = db.transaction(TASK_RESULTS_STORE_NAME, 'readwrite');
    await tx.store.put(recordToCache);
    await tx.done;
    console.log(`[DB] Task results cached for task: ${taskData.id}`);
  } catch (error) {
    console.error(`[DB] Error caching task results for ${taskData.id}:`, error);
    throw error;
  }
}

export const convertBackendToUserTaskRecord = (
  task: BackendTaskRecord,
  isPublic: boolean
): ExtendedUserTaskRecord => {
  const now = new Date().toISOString();

  // Generate viewpoint text from topic_text
  const viewpointText = task.topic_text || 'Untitled Timeline';

  return {
    id: task.id,
    viewpoint: viewpointText,
    // Access data source preference from the config object
    dataSourcePref: task.config?.data_source_preference || 'default',
    serverRequestId: task.id, // Using task id as a server request id surrogate
    finalEvents: [], // This function only syncs task metadata, not events.
    preliminaryEvents: [],
    progressMessages: task.progress_messages,
    error: task.status === 'failed' ? { message: task.notes || 'Task failed' } : undefined,
    createdAt: task.created_at,
    lastAccessedAt: now,
    // Use processed_at for completedAt if available and status is 'completed'
    completedAt: task.status === 'completed' ? task.processed_at || task.updated_at : undefined,
    updatedAt: task.updated_at,
    isComplete: task.status === 'completed' || task.status === 'failed',
    status: task.status,
    isPublic: isPublic ? 1 : 0,
    taskType: task.task_type,
  };
};

export const syncUserTasks = async (tasks: BackendTaskRecord[]): Promise<void> => {
  const db = await getDb();
  const tx = db.transaction(TASK_STORE_NAME, 'readwrite');
  const store = tx.objectStore(TASK_STORE_NAME);

  const promises = tasks.map((task) => {
    const record = convertBackendToUserTaskRecord(task, false); // isPublic: false
    return store.put(record);
  });

  await Promise.all(promises);
  await tx.done;
  console.log(`[DB] Synced ${tasks.length} user tasks.`);
};

export const getLocalUserTasks = async (): Promise<ExtendedUserTaskRecord[]> => {
  const db = await getDb();
  const tx = db.transaction(TASK_STORE_NAME, 'readonly');
  const index = tx.store.index('isPublic');
  const tasks = await index.getAll(0); // 0 for false
  console.log(`[DB] Fetched ${tasks.length} local user tasks from cache.`);
  return tasks.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
};

export const syncPublicTasks = async (tasks: BackendTaskRecord[]): Promise<void> => {
  const db = await getDb();
  const tx = db.transaction(TASK_STORE_NAME, 'readwrite');
  const store = tx.objectStore(TASK_STORE_NAME);
  const index = store.index('isPublic');

  // Clear existing public tasks first
  let cursor = await index.openCursor(1); // 1 for true
  while (cursor) {
    await cursor.delete();
    cursor = await cursor.continue();
  }
  console.log('[DB] Cleared old public tasks.');

  // Add new public tasks
  const promises = tasks.map((task) => {
    const record = convertBackendToUserTaskRecord(task, true); // isPublic: true
    return store.put(record);
  });

  await Promise.all(promises);
  await tx.done;
  console.log(`[DB] Synced ${tasks.length} public tasks.`);
};

export const getLocalPublicTasks = async (): Promise<ExtendedUserTaskRecord[]> => {
  const db = await getDb();
  const tx = db.transaction(TASK_STORE_NAME, 'readonly');
  const index = tx.store.index('isPublic');
  const tasks = await index.getAll(1); // 1 for true
  console.log(`[DB] Fetched ${tasks.length} local public tasks from cache.`);
  return tasks.sort(
    (a, b) => new Date(b.completedAt ?? 0).getTime() - new Date(a.completedAt ?? 0).getTime()
  );
};

export async function clearOldCacheEntries(maxAgeDays: number): Promise<number> {
  const db = await getDb();
  const thresholdDate = new Date();
  thresholdDate.setDate(thresholdDate.getDate() - maxAgeDays);
  const thresholdISO = thresholdDate.toISOString();

  let deleteCount = 0;
  const tx = db.transaction(TASK_RESULTS_STORE_NAME, 'readwrite');
  const store = tx.objectStore(TASK_RESULTS_STORE_NAME);
  const index = store.index('timestamp');

  let cursor = await index.openCursor(IDBKeyRange.upperBound(thresholdISO));
  while (cursor) {
    await cursor.delete();
    deleteCount++;
    cursor = await cursor.continue();
  }
  await tx.done;
  if (deleteCount > 0) {
    console.log(`[DB] Cleared ${deleteCount} cache entries older than ${maxAgeDays} days.`);
  }
  return deleteCount;
}
