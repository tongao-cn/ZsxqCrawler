import type { ApiErrorDetail } from './types';

export const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL?.trim() || 'http://localhost:8508').replace(/\/$/, '');

export interface ApiRequestOptions {
  signal?: AbortSignal;
}

export function formatApiError(errorData: unknown, fallback: string): string {
  if (!errorData || typeof errorData !== 'object') {
    return fallback;
  }

  const data = errorData as {
    detail?: unknown;
    message?: unknown;
    error?: unknown;
  };
  const detail = data.detail;

  if (typeof detail === 'string' && detail.trim()) {
    return detail;
  }
  if (detail && typeof detail === 'object') {
    const detailObject = detail as { message?: unknown; error?: unknown };
    if (typeof detailObject.message === 'string' && detailObject.message.trim()) {
      return detailObject.message;
    }
    if (typeof detailObject.error === 'string' && detailObject.error.trim()) {
      return detailObject.error;
    }
  }
  if (typeof data.message === 'string' && data.message.trim()) {
    return data.message;
  }
  if (typeof data.error === 'string' && data.error.trim()) {
    return data.error;
  }

  return fallback;
}

export class ApiClientError extends Error {
  status: number;
  detail?: unknown;
  errorData: unknown;

  constructor(message: string, status: number, errorData: unknown) {
    super(message);
    this.name = 'ApiClientError';
    this.status = status;
    this.errorData = errorData;
    this.detail = errorData && typeof errorData === 'object'
      ? (errorData as { detail?: unknown }).detail
      : undefined;
  }
}

export function getTaskConflictDetail(error: unknown): ApiErrorDetail | null {
  if (!(error instanceof ApiClientError) || error.status !== 409) {
    return null;
  }
  if (!error.detail || typeof error.detail !== 'object') {
    return null;
  }
  const detail = error.detail as ApiErrorDetail;
  return detail.task_id ? detail : null;
}

export class ApiClientBase {
  protected baseUrl: string;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl;
  }

  protected async request<T = any>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    
    const response = await fetch(url, {
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
      ...options,
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new ApiClientError(
        formatApiError(errorData, `HTTP ${response.status}: ${response.statusText}`),
        response.status,
        errorData,
      );
    }

    return response.json();
  }
}
