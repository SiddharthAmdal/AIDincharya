import { apiClient } from '../client';
import type { StandardResponse, UserProfileResponse, UserState, UserSettings } from '../types';

export const userService = {
  getProfile: async (): Promise<UserProfileResponse> => {
    return apiClient.get<UserProfileResponse>('/api/user/profile');
  },

  saveQuestionnaire: async (responses: Record<string, string>): Promise<StandardResponse> => {
    return apiClient.post<StandardResponse>('/api/user/questionnaire', { responses });
  },

  getState: async (): Promise<UserState> => {
    return apiClient.get<UserState>('/api/user/state');
  },

  getSettings: async (): Promise<UserSettings> => {
    return apiClient.get<UserSettings>('/api/user/settings');
  },

  updateSettings: async (settings: UserSettings): Promise<StandardResponse> => {
    return apiClient.put<StandardResponse>('/api/user/settings', settings);
  },

  getPendingNotifications: async (): Promise<{ notifications: any[] }> => {
    return apiClient.get<{ notifications: any[] }>('/api/notifications/pending');
  }
};
