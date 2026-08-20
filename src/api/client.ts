export const API_BASE_URL = '';

class ApiError extends Error {
  constructor(public status: number, public data: any) {
    super(`API Error: ${status}`);
    this.name = 'ApiError';
  }
}

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem('auth_token');
  
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...options.headers,
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers,
  });

  let data;
  try {
    data = await response.json();
  } catch (e) {
    data = null;
  }

  if (!response.ok) {
    throw new ApiError(response.status, data);
  }

  return data as T;
}

export const apiClient = {
  get: <T>(endpoint: string, options?: RequestInit) => 
    request<T>(endpoint, { ...options, method: 'GET' }),
    
  post: <T>(endpoint: string, body?: any, options?: RequestInit) => 
    request<T>(endpoint, { ...options, method: 'POST', body: body ? JSON.stringify(body) : undefined }),
    
  put: <T>(endpoint: string, body?: any, options?: RequestInit) => 
    request<T>(endpoint, { ...options, method: 'PUT', body: body ? JSON.stringify(body) : undefined }),
    
  delete: <T>(endpoint: string, options?: RequestInit) => 
    request<T>(endpoint, { ...options, method: 'DELETE' }),
};
