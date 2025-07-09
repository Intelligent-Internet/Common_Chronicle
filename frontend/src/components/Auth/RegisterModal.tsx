import React, { useState } from 'react';
import { useAuth } from '../../contexts/auth';
import ParchmentPaper from '../ParchmentPaper';
import WavyLine from '../WavyLine';

interface RegisterModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSwitchToLogin: () => void;
}

const RegisterModal: React.FC<RegisterModalProps> = ({ isOpen, onClose, onSwitchToLogin }) => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);

  const { register } = useAuth();

  const validateForm = () => {
    if (!username.trim() || !password.trim() || !confirmPassword.trim()) {
      setError('Please fill in all fields');
      return false;
    }

    if (username.trim().length < 3) {
      setError('Username must be at least 3 characters');
      return false;
    }

    if (password.length < 6) {
      setError('Password must be at least 6 characters');
      return false;
    }

    if (password !== confirmPassword) {
      setError('Passwords do not match');
      return false;
    }

    return true;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!validateForm()) {
      return;
    }

    setIsLoading(true);
    setError('');

    try {
      const result = await register(username.trim(), password);
      if (result.success) {
        setSuccess(true);
        setUsername('');
        setPassword('');
        setConfirmPassword('');
        // Auto-switch to login after a short delay
        setTimeout(() => {
          setSuccess(false);
          onSwitchToLogin();
        }, 2000);
      } else {
        setError(result.error || 'Registration failed');
      }
    } catch {
      setError('Network error. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleClose = () => {
    setUsername('');
    setPassword('');
    setConfirmPassword('');
    setError('');
    setSuccess(false);
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
            <h2 className="text-3xl font-serif text-scholar-800">Join the Order</h2>
            <div className="mt-4 max-w-xs mx-auto">
              <WavyLine className="text-parchment-400" />
            </div>
          </div>

          {success ? (
            <div className="text-center py-8">
              <div className="text-sage-600 text-lg font-semibold mb-2">
                ✓ Inscription Complete!
              </div>
              <p className="text-scholar-600">
                You may now enter the archives. Redirecting to login...
              </p>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label
                  htmlFor="register-username"
                  className="block text-sm font-serif font-medium text-scholar-700 mb-1"
                >
                  Scholar Name
                </label>
                <input
                  type="text"
                  id="register-username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="mt-1 block w-full bg-parchment-50 border-2 border-parchment-300 rounded-md p-3 text-scholar-800 placeholder-scholar-400 focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition"
                  placeholder="Choose your scholar name (min. 3 chars)"
                  disabled={isLoading}
                />
              </div>

              <div>
                <label
                  htmlFor="register-password"
                  className="block text-sm font-serif font-medium text-scholar-700 mb-1"
                >
                  Secret Word (Password)
                </label>
                <input
                  type="password"
                  id="register-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="mt-1 block w-full bg-parchment-50 border-2 border-parchment-300 rounded-md p-3 text-scholar-800 placeholder-scholar-400 focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition"
                  placeholder="Create a secret passphrase (min. 6 chars)"
                  disabled={isLoading}
                />
              </div>

              <div>
                <label
                  htmlFor="confirm-password"
                  className="block text-sm font-serif font-medium text-scholar-700 mb-1"
                >
                  Confirm Secret Word
                </label>
                <input
                  type="password"
                  id="confirm-password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="mt-1 block w-full bg-parchment-50 border-2 border-parchment-300 rounded-md p-3 text-scholar-800 placeholder-scholar-400 focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition"
                  placeholder="Confirm your passphrase"
                  disabled={isLoading}
                />
              </div>

              {error && (
                <div className="bg-red-100 border-l-4 border-red-500 text-red-700 p-3 text-sm">
                  <p className="font-bold">Registration Error</p>
                  <p>{error}</p>
                </div>
              )}

              <div className="flex flex-col items-center space-y-4 pt-4">
                <button
                  type="submit"
                  disabled={isLoading}
                  className="w-full bg-amber-800 hover:bg-amber-900 text-parchment-50 font-bold py-3 px-8 rounded-lg shadow-lg hover:shadow-xl transform hover:-translate-y-0.5 transition-all duration-200 disabled:bg-gray-400 disabled:shadow-none disabled:transform-none"
                >
                  {isLoading ? 'Inscribing...' : 'Take the Oath'}
                </button>
                <button
                  type="button"
                  onClick={onSwitchToLogin}
                  disabled={isLoading}
                  className="text-sm text-scholar-600 hover:text-scholar-800 hover:underline disabled:text-gray-400"
                >
                  Already a scholar? Login to the Archives
                </button>
              </div>
            </form>
          )}
        </ParchmentPaper>
      </div>
    </div>
  );
};

export default RegisterModal;
