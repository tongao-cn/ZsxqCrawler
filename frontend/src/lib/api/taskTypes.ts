export interface Task {
  task_id: string;
  type: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  message: string;
  result?: any;
  created_at: string;
  updated_at: string;
  display_name?: string;
  cancellable?: boolean;
  group_id?: string | number | null;
  ingestion_lock_key?: string | null;
}

export interface TaskCreateResponse {
  task_id: string;
  message: string;
}

export interface TaskLogsResponse {
  task_id: string;
  logs: string[];
}

export interface ApiErrorDetail {
  message?: string;
  error?: string;
  task_id?: string;
  type?: string;
  status?: string;
  [key: string]: unknown;
}
