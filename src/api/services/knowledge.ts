import { apiClient } from '../client';
import type { KnowledgeSearchResponse, ChatRequest, ChatResponse, InsightsResponse } from '../types';

export const knowledgeService = {
  search: async (query: string, k: number = 5): Promise<KnowledgeSearchResponse> => {
    return apiClient.get<KnowledgeSearchResponse>(`/api/knowledge/search?q=${encodeURIComponent(query)}&k=${k}`);
  },

  chatAssistant: async (request: ChatRequest): Promise<ChatResponse> => {
    return apiClient.post<ChatResponse>('/api/chat', request);
  },

  getInsights: async (): Promise<InsightsResponse> => {
    return apiClient.get<InsightsResponse>('/api/insights');
  }
};

