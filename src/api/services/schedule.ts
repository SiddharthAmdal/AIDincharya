import { apiClient } from '../client';
import type { ScheduleGenerateRequest, ScheduleResponse, AdherenceLogRequest, AdherenceLogResponse } from '../types';

export const scheduleService = {
  generate: async (request: ScheduleGenerateRequest): Promise<ScheduleResponse> => {
    return apiClient.post<ScheduleResponse>('/api/schedule/generate', request);
  },

  getToday: async (): Promise<ScheduleResponse> => {
    return apiClient.get<ScheduleResponse>('/api/schedule/today');
  },

  logAdherence: async (request: AdherenceLogRequest): Promise<AdherenceLogResponse> => {
    return apiClient.post<AdherenceLogResponse>('/api/adherence/log', request);
  }
};
