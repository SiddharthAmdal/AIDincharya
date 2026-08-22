import { apiClient } from '../client';
import type { StandardResponse, HealthUploadRequest } from '../types';

export const healthService = {
  uploadTelemetry: async (request: HealthUploadRequest): Promise<StandardResponse> => {
    return apiClient.post<StandardResponse>('/api/health/telemetry', request);
  },

  getHistory: async (): Promise<any> => {
    return apiClient.get<any>('/api/health/history');
  }
};
