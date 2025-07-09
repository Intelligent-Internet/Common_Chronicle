import React, { useState } from 'react';
import { useAuth } from '../../contexts/auth';
import ParchmentPaper from '../ParchmentPaper';
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
        <ParchmentPaper padding="p-8">
          <div className="text-center mb-6">
            <h2 className="text-3xl font-serif text-scholar-800">Scholar Login</h2>
            <div className="mt-4 max-w-xs mx-auto">
              <WavyLine className="text-parchment-400" />
            </div>
          </div>

          <form onSubmit={handleSubmit} className="space-y-6">
            <div>
              <label
                htmlFor="username"
                className="block text-sm font-serif font-medium text-scholar-700 mb-1"
              >
                Scholar Name
              </label>
              <input
                type="text"
                id="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="mt-1 block w-full bg-parchment-50 border-2 border-parchment-300 rounded-md p-3 text-scholar-800 placeholder-scholar-400 focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition"
                placeholder="Your scholar identification"
                disabled={isLoading}
              />
            </div>

            <div>
              <label
                htmlFor="password"
                className="block text-sm font-serif font-medium text-scholar-700 mb-1"
              >
                Secret Word (Password)
              </label>
              <input
                type="password"
                id="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="mt-1 block w-full bg-parchment-50 border-2 border-parchment-300 rounded-md p-3 text-scholar-800 placeholder-scholar-400 focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition"
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
                className="w-full bg-amber-800 hover:bg-amber-900 text-parchment-50 font-bold py-3 px-8 rounded-lg shadow-lg hover:shadow-xl transform hover:-translate-y-0.5 transition-all duration-200 disabled:bg-gray-400 disabled:shadow-none disabled:transform-none"
              >
                {isLoading ? 'Authenticating...' : 'Enter the Archives'}
              </button>
              <button
                type="button"
                onClick={onSwitchToRegister}
                disabled={isLoading}
                className="text-sm text-scholar-600 hover:text-scholar-800 hover:underline disabled:text-gray-400"
              >
                Need to join the order? Register as a Scholar
              </button>
            </div>
          </form>
        </ParchmentPaper>
      </div>
    </div>
  );
};

export default LoginModal;
