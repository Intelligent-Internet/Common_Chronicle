import React, { useState, useEffect } from 'react';
import type { ReactNode } from 'react';
import { AuthContext } from './auth';
import type { AuthContextType, User } from './auth';
import { loginUser, registerUser, getCurrentUser } from '../services/api';

// Auth provider component
interface AuthProviderProps {
  children: ReactNode;
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const isLoggedIn = !!user && !!token;

  // Check authentication status on app startup
  const checkAuthStatus = async () => {
    setIsLoading(true);
    try {
      const storedToken = localStorage.getItem('authToken');
      if (!storedToken) {
        setIsLoading(false);
        return;
      }

      // Verify token with backend using api service
      const result = await getCurrentUser(storedToken);

      if (result.success) {
        setUser(result.data);
        setToken(storedToken);
      } else {
        // Token is invalid, remove it
        localStorage.removeItem('authToken');
        setUser(null);
        setToken(null);
      }
    } catch (error) {
      console.error('Error checking auth status:', error);
      localStorage.removeItem('authToken');
      setUser(null);
      setToken(null);
    } finally {
      setIsLoading(false);
    }
  };

  // Login function
  const login = async (username: string, password: string) => {
    try {
      const result = await loginUser(username, password);

      if (result.success) {
        const { access_token } = result.data;

        // Store token
        localStorage.setItem('authToken', access_token);
        setToken(access_token);

        // Get user info
        const userResult = await getCurrentUser(access_token);

        if (userResult.success) {
          setUser(userResult.data);
          return { success: true };
        } else {
          return { success: false, error: 'Failed to get user info' };
        }
      } else {
        return { success: false, error: result.error };
      }
    } catch (error) {
      console.error('Login error:', error);
      return { success: false, error: 'Network error or server unavailable' };
    }
  };

  // Register function
  const register = async (username: string, password: string) => {
    try {
      const result = await registerUser(username, password);
      return result;
    } catch (error) {
      console.error('Registration error:', error);
      return { success: false, error: 'Network error or server unavailable' };
    }
  };

  // Logout function
  const logout = () => {
    localStorage.removeItem('authToken');
    setUser(null);
    setToken(null);
  };

  // Check auth status on component mount
  useEffect(() => {
    checkAuthStatus();
  }, []);

  const value: AuthContextType = {
    user,
    token,
    isLoggedIn,
    isLoading,
    login,
    register,
    logout,
    checkAuthStatus,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};
