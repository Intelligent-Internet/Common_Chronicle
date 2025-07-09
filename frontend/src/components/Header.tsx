import React from 'react';
import { Link, NavLink } from 'react-router-dom';
import { useAuth } from '../contexts/auth';
import WavyLine from './WavyLine';
import InkBlotButton from './InkBlotButton_alt';

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
    <header className="bg-parchment-100/80 backdrop-blur-sm sticky top-0 z-40 relative">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-20">
          {/* Left side: Logo and Public Timelines */}
          <div className="flex items-center space-x-8">
            <Link
              to="/"
              className="text-2xl font-serif font-bold text-scholar-800 hover:text-scholar-900 transition-colors"
            >
              Common Chronicle
            </Link>
            <NavLinkWithInkBlot to="/public">Public Chronicles</NavLinkWithInkBlot>
          </div>

          {/* Right side: Task-related links and Auth Section */}
          <div className="flex items-center space-x-4">
            <NavLinkWithInkBlot to="/new">New Chronicle</NavLinkWithInkBlot>

            {/* Auth Section */}
            {isLoading ? (
              <div className="text-sm text-scholar-500 ml-4">Loading...</div>
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
                <span className="text-sm text-scholar-700">
                  <span className="font-medium">{user.username}</span>
                </span>
                <button
                  onClick={logout}
                  className="px-3 py-1.5 text-sm text-scholar-600 hover:text-scholar-800 border-2 border-parchment-300 rounded-lg hover:bg-parchment-200 hover:border-parchment-400 transition-colors"
                >
                  Logout
                </button>
              </div>
            ) : (
              <div className="flex items-center space-x-2 ml-4">
                <button
                  onClick={onShowLogin}
                  className="px-4 py-2 text-sm font-medium text-scholar-700 hover:text-scholar-900 hover:bg-parchment-200/60 rounded-lg transition-colors"
                >
                  Login
                </button>
                <button
                  onClick={onShowRegister}
                  className="px-4 py-2 text-sm font-medium text-parchment-50 bg-parchment-500 hover:bg-parchment-600 rounded-lg transition-colors border border-transparent hover:border-parchment-400"
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
        <div className="absolute inset-0 bg-gradient-to-b from-parchment-100/60 via-parchment-100/30 to-transparent h-8 blur-sm"></div>
        <WavyLine className="text-parchment-300/70 relative z-10" />
        <div className="absolute inset-x-0 bottom-0 h-4 bg-gradient-to-b from-parchment-200/20 to-transparent blur-md"></div>
      </div>
    </header>
  );
};

export default Header;
