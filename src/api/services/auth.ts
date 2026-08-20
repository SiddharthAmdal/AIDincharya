import { apiClient } from '../client';
import type { AuthResponse, StandardResponse } from '../types';

export const authService = {
  register: async (username: string, password: string): Promise<AuthResponse> => {
    return apiClient.post<AuthResponse>('/api/auth/register', { username, password });
  },

  login: async (username: string, password: string): Promise<AuthResponse> => {
    return apiClient.post<AuthResponse>('/api/auth/login', { username, password });
  },

  logout: async (): Promise<StandardResponse> => {
    return apiClient.post<StandardResponse>('/api/auth/logout');
  }
};
