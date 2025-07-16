import React from 'react';
import { Link, NavLink } from 'react-router-dom';
import { useAuth } from '../contexts/auth';
import { useTheme } from '../contexts/ThemeContext';
import WavyLine from './WavyLine';
import InkBlotButton from './InkBlotButton';

interface HeaderProps {
  onShowLogin: () => void;
  onShowRegister: () => void;
  onToggleMyTasks?: () => void;
  isMyTasksPanelOpen?: boolean;
}

const Header: React.FC<HeaderProps> = ({
  onShowLogin,
  onShowRegister,
  onToggleMyTasks,
  isMyTasksPanelOpen = false,
}) => {
  const { user, isLoggedIn, logout, isLoading } = useAuth();
  const { theme, toggleTheme } = useTheme();

  // Custom component for navigation links with ink blot effect
  const NavLinkWithInkBlot: React.FC<{
    to: string;
    children: React.ReactNode;
  }> = ({ to, children }) => (
    <NavLink to={to}>
      {({ isActive }) => (
        <InkBlotButton
          isActive={isActive}
          onClick={() => {}} // Navigation handled by NavLink
          variant="default"
          className="text-sm font-medium"
        >
          {children}
        </InkBlotButton>
      )}
    </NavLink>
  );

  // Custom component for My Chronicles button with ink blot effect
  const MyChroniclesButton: React.FC<{
    onClick: () => void;
    isActive: boolean;
    children: React.ReactNode;
  }> = ({ onClick, isActive, children }) => (
    <InkBlotButton
      isActive={isActive}
      onClick={onClick}
      variant="default"
      className="text-sm font-medium"
    >
      {children}
    </InkBlotButton>
  );

  return (
    <header className="bg-white/80 backdrop-blur-sm sticky top-0 z-40 relative dark:bg-charcoal/80">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-20">
          {/* Left side: Logo and Public Timelines */}
          <div className="flex items-center space-x-8">
            <Link
              to="/"
              className="text-2xl font-sans font-bold text-charcoal hover:text-slate transition-colors dark:text-white dark:hover:text-sky-blue"
            >
              Common Chronicle
            </Link>
            <NavLinkWithInkBlot to="/public">Public Chronicles</NavLinkWithInkBlot>
          </div>

          {/* Right side: Task-related links and Auth Section */}
          <div className="flex items-center space-x-4">
            <NavLinkWithInkBlot to="/new">New Chronicle</NavLinkWithInkBlot>

            <button
              onClick={toggleTheme}
              className="p-2 rounded-full text-slate hover:text-charcoal hover:bg-mist/60 dark:text-mist dark:hover:text-white dark:hover:bg-slate/60 transition-colors"
              aria-label="Toggle theme"
            >
              {theme === 'light' ? (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"
                  />
                </svg>
              ) : (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z"
                  />
                </svg>
              )}
            </button>

            {/* Auth Section */}
            {isLoading ? (
              <div className="text-sm text-slate dark:text-mist ml-4">Loading...</div>
            ) : isLoggedIn && user ? (
              <div className="flex items-center space-x-4 ml-4">
                {onToggleMyTasks && (
                  <MyChroniclesButton
                    onClick={onToggleMyTasks}
                    isActive={isMyTasksPanelOpen}
                    aria-label={
                      isMyTasksPanelOpen ? 'Close My Chronicles panel' : 'Open My Chronicles panel'
                    }
                  >
                    My Chronicles
                  </MyChroniclesButton>
                )}
                <span className="text-sm text-slate dark:text-mist">
                  <span className="font-medium">{user.username}</span>
                </span>
                <button
                  onClick={logout}
                  className="px-3 py-1.5 text-sm text-slate hover:text-charcoal border-2 border-pewter rounded-lg hover:bg-mist/50 transition-colors dark:text-mist dark:hover:text-white dark:hover:bg-slate/50"
                >
                  Logout
                </button>
              </div>
            ) : (
              <div className="flex items-center space-x-2 ml-4">
                <button
                  onClick={onShowLogin}
                  className="px-4 py-2 text-sm font-medium rounded-full border-2 border-transparent text-slate hover:text-slate hover:border-sky-blue dark:text-mist dark:hover:text-sky-blue dark:hover:border-sky-blue transition-colors"
                >
                  Login
                </button>
                <button
                  onClick={onShowRegister}
                  className="px-4 py-2 text-sm font-medium rounded-full border-2 border-transparent text-slate hover:text-slate hover:border-sky-blue dark:text-mist dark:hover:text-sky-blue dark:hover:border-sky-blue transition-colors"
                >
                  Register
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Enhanced wavy line with gradient blur effect */}
      <div className="relative">
        <div className="absolute inset-0 bg-gradient-to-b from-white/60 via-white/30 to-transparent dark:from-charcoal/60 dark:via-charcoal/30 h-8 blur-sm"></div>
        <WavyLine className="text-pewter/70 dark:text-slate/70 relative z-10" />
        <div className="absolute inset-x-0 bottom-0 h-4 bg-gradient-to-b from-mist/20 to-transparent dark:from-slate/20 blur-md"></div>
      </div>
    </header>
  );
};

export default Header;
