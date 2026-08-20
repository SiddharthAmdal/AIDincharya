import { apiClient } from '../client';
import type { KnowledgeSearchResponse } from '../types';

export const knowledgeService = {
  search: async (query: string, k: number = 5): Promise<KnowledgeSearchResponse> => {
    return apiClient.get<KnowledgeSearchResponse>(`/api/knowledge/search?q=${encodeURIComponent(query)}&k=${k}`);
  }
};
