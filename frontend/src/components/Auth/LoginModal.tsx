import React, { useState } from 'react';
import { useAuth } from '../../contexts/auth';
import ContentCard from '../ContentCard';
import WavyLine from '../WavyLine';

interface LoginModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSwitchToRegister: () => void;
}

const LoginModal: React.FC<LoginModalProps> = ({ isOpen, onClose, onSwitchToRegister }) => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  const { login } = useAuth();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password.trim()) {
      setError('Please provide both your scholar name and secret word.');
      return;
    }

    setIsLoading(true);
    setError('');

    try {
      const result = await login(username.trim(), password);
      if (result.success) {
        setUsername('');
        setPassword('');
        onClose();
      } else {
        setError(result.error || 'Login failed. Please check your credentials.');
      }
    } catch {
      setError('A network error occurred. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleClose = () => {
    setUsername('');
    setPassword('');
    setError('');
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center transition-opacity duration-300"
      onClick={handleClose}
    >
      <div className="w-full max-w-md mx-4" onClick={(e) => e.stopPropagation()}>
        <ContentCard padding="p-8">
          <div className="text-center mb-6">
            <h2 className="text-3xl font-sans font-semibold text-charcoal dark:text-white">
              Scholar Login
            </h2>
            <div className="mt-4 max-w-xs mx-auto">
              <WavyLine className="text-pewter dark:text-mist" />
            </div>
          </div>

          <form onSubmit={handleSubmit} className="space-y-6">
            <div>
              <label
                htmlFor="username"
                className="block text-sm font-alt font-medium text-slate dark:text-mist mb-1"
              >
                Scholar Name
              </label>
              <input
                type="text"
                id="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="input mt-1 block w-full p-3"
                placeholder="Your scholar identification"
                disabled={isLoading}
              />
            </div>

            <div>
              <label
                htmlFor="password"
                className="block text-sm font-alt font-medium text-slate dark:text-mist mb-1"
              >
                Secret Word (Password)
              </label>
              <input
                type="password"
                id="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="input mt-1 block w-full p-3"
                placeholder="Your secret passphrase"
                disabled={isLoading}
              />
            </div>

            {error && (
              <div className="bg-red-100 border-l-4 border-red-500 text-red-700 p-3 text-sm">
                <p className="font-bold">Access Denied</p>
                <p>{error}</p>
              </div>
            )}

            <div className="flex flex-col items-center space-y-4 pt-4">
              <button
                type="submit"
                disabled={isLoading}
                className="btn btn-primary w-full py-3 px-8 font-bold shadow-lg hover:shadow-xl transform hover:-translate-y-0.5 transition-all duration-200 disabled:bg-gray-400 disabled:shadow-none disabled:transform-none"
              >
                {isLoading ? 'Authenticating...' : 'Enter the Archives'}
              </button>
              <button
                type="button"
                onClick={onSwitchToRegister}
                disabled={isLoading}
                className="text-sm text-slate hover:text-charcoal hover:underline disabled:text-gray-400 dark:text-mist dark:hover:text-white dark:disabled:text-gray-500"
              >
                Need to join the order? Register as a Scholar
              </button>
            </div>
          </form>
        </ContentCard>
      </div>
    </div>
  );
};

export default LoginModal;
