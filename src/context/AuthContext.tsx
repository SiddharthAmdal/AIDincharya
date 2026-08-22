import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { authService, userService } from '../api';
import type { UserProfileResponse } from '../api/types';

interface AuthContextType {
  isAuthenticated: boolean;
  token: string | null;
  profile: UserProfileResponse | null;
  login: (username: string, pass: string) => Promise<void>;
  register: (username: string, pass: string) => Promise<void>;
  logout: () => void;
  isLoading: boolean;
  refreshProfile: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(localStorage.getItem('auth_token'));
  const [profile, setProfile] = useState<UserProfileResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function loadUser() {
      if (token) {
        try {
          const data = await userService.getProfile();
          setProfile(data);
        } catch (err) {
          console.error("Failed to load user profile:", err);
          logout(); // clear invalid token
        }
      }
      setIsLoading(false);
    }
    loadUser();
  }, [token]);

  const login = async (username: string, pass: string) => {
    const res = await authService.login(username, pass);
    localStorage.setItem('auth_token', res.token);
    setToken(res.token);
  };

  const register = async (username: string, pass: string) => {
    const res = await authService.register(username, pass);
    localStorage.setItem('auth_token', res.token);
    setToken(res.token);
  };

  const logout = () => {
    localStorage.removeItem('auth_token');
    setToken(null);
    setProfile(null);
  };

  const refreshProfile = async () => {
    if (token) {
      try {
        const data = await userService.getProfile();
        setProfile(data);
      } catch (err) {
        console.error("Failed to refresh profile:", err);
      }
    }
  };

  return (
    <AuthContext.Provider value={{ isAuthenticated: !!token, token, profile, login, register, logout, isLoading, refreshProfile }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
