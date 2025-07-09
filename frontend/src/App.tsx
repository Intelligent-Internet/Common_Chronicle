import { useState, useCallback, useEffect } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from './contexts/auth';
import NewTaskPage from './pages/NewTaskPage';
import PublicTimelinesPage from './pages/PublicTimelinesPage';
import TaskPage from './pages/TaskPage';
import Header from './components/Header';
import TaskListPanel from './components/TaskListPanel';
import LoginModal from './components/Auth/LoginModal';
import RegisterModal from './components/Auth/RegisterModal';
import { getTasks } from './services/api';
import { getLocalUserTasks, syncUserTasks } from './services/indexedDB.service';
import type { ExtendedUserTaskRecord } from './services/indexedDB.service';

function App() {
  // Auth modal states
  const [isLoginModalOpen, setIsLoginModalOpen] = useState(false);
  const [isRegisterModalOpen, setIsRegisterModalOpen] = useState(false);

  // My Tasks panel states
  const [isMyTasksPanelOpen, setIsMyTasksPanelOpen] = useState(false);
  const [userTasks, setUserTasks] = useState<ExtendedUserTaskRecord[]>([]);
  const [isLoadingUserTasks, setIsLoadingUserTasks] = useState(false);

  const { isLoggedIn, isLoading: isAuthLoading } = useAuth();

  // Auth modal handlers
  const handleShowLogin = useCallback(() => {
    setIsRegisterModalOpen(false);
    setIsLoginModalOpen(true);
  }, []);

  const handleShowRegister = useCallback(() => {
    setIsLoginModalOpen(false);
    setIsRegisterModalOpen(true);
  }, []);

  const handleCloseAuthModals = useCallback(() => {
    setIsLoginModalOpen(false);
    setIsRegisterModalOpen(false);
  }, []);

  const handleSwitchToRegister = useCallback(() => {
    setIsLoginModalOpen(false);
    setIsRegisterModalOpen(true);
  }, []);

  const handleSwitchToLogin = useCallback(() => {
    setIsRegisterModalOpen(false);
    setIsLoginModalOpen(true);
  }, []);

  // My Tasks handlers
  const handleToggleMyTasks = useCallback(() => {
    setIsMyTasksPanelOpen((prev) => !prev);
  }, []);

  const handleRefreshUserTasks = useCallback(async () => {
    if (!isLoggedIn) {
      setUserTasks([]);
      return;
    }

    console.log('[App.tsx] Refreshing user tasks...');
    setIsLoadingUserTasks(true);
    try {
      const tasksFromApi = await getTasks({ owned_by_me: true, limit: 20 });
      const completedTasks = tasksFromApi.filter((task) => task.status === 'completed');
      console.log(`[App.tsx] Syncing ${completedTasks.length} completed tasks from API to cache.`);
      await syncUserTasks(tasksFromApi);
      const freshTasks = await getLocalUserTasks();
      setUserTasks(freshTasks);
    } catch (err) {
      console.error('[App.tsx] Error refreshing user tasks:', err);
      // If refresh fails, we still have stale data in the panel.
      // We could show a toast notification here.
    } finally {
      setIsLoadingUserTasks(false);
    }
  }, [isLoggedIn]);

  // Stale-While-Revalidate: Show cached data immediately, then update with fresh data
  useEffect(() => {
    if (isMyTasksPanelOpen && isLoggedIn) {
      let isMounted = true;

      const fetchAndSyncTasks = async () => {
        // Stale: Load from cache immediately for perceived performance
        const cachedTasks = await getLocalUserTasks();
        if (isMounted && cachedTasks.length > 0) {
          setUserTasks(cachedTasks);
        } else if (isMounted) {
          // Only show loader if no cache exists
          setIsLoadingUserTasks(true);
        }

        // While-Revalidate: Fetch fresh data in background
        try {
          console.log('[App.tsx] Revalidating user tasks in background...');
          const apiTasks = await getTasks({ owned_by_me: true, limit: 20 });
          const completedApiTasks = apiTasks.filter((task) => task.status === 'completed');
          console.log(
            `[App.tsx] Syncing ${completedApiTasks.length} tasks from API to user's cache.`
          );
          await syncUserTasks(apiTasks);
          const freshTasks = await getLocalUserTasks();
          if (isMounted) {
            setUserTasks(freshTasks);
          }
        } catch (err) {
          console.error('[App.tsx] Error revalidating user tasks:', err);
          // Keep showing stale data on network failure - better UX than empty state
        } finally {
          if (isMounted) {
            setIsLoadingUserTasks(false);
          }
        }
      };

      fetchAndSyncTasks();

      return () => {
        isMounted = false;
      };
    } else if (!isLoggedIn) {
      setUserTasks([]);
    }
  }, [isMyTasksPanelOpen, isLoggedIn]);

  // Close My Tasks panel when user logs out
  useEffect(() => {
    if (!isLoggedIn && isMyTasksPanelOpen) {
      setIsMyTasksPanelOpen(false);
    }
  }, [isLoggedIn, isMyTasksPanelOpen]);

  // Show loading screen while checking auth status
  if (isAuthLoading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-gray-600">Initializing...</p>
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="flex flex-col min-h-screen font-sans">
        <Header
          onShowLogin={handleShowLogin}
          onShowRegister={handleShowRegister}
          onToggleMyTasks={handleToggleMyTasks}
          isMyTasksPanelOpen={isMyTasksPanelOpen}
        />

        <Routes>
          <Route path="/" element={<Navigate to="/new" replace />} />
          <Route path="/new" element={<NewTaskPage />} />
          <Route path="/public" element={<PublicTimelinesPage />} />
          <Route path="/task/:taskId" element={<TaskPage />} />
        </Routes>

        {/* Auth Modals */}
        <LoginModal
          isOpen={isLoginModalOpen}
          onClose={handleCloseAuthModals}
          onSwitchToRegister={handleSwitchToRegister}
        />
        <RegisterModal
          isOpen={isRegisterModalOpen}
          onClose={handleCloseAuthModals}
          onSwitchToLogin={handleSwitchToLogin}
        />

        {/* Global My Tasks Panel */}
        <TaskListPanel
          isOpen={isMyTasksPanelOpen}
          isLoading={isLoadingUserTasks}
          tasks={userTasks}
          viewingTaskId={null}
          onClose={handleToggleMyTasks}
          onRefreshTasks={handleRefreshUserTasks}
          title="My Chronicles"
        />
      </div>
    </>
  );
}

export default App;
