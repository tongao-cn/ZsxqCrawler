import type { Task } from './api/taskTypes';

export type TaskStatus = Task['status'];
export type TaskStatusSnapshot = Pick<Task, 'status' | 'message'>;
export type TerminalTask = Task & { result?: unknown };

export interface TaskStatusStreamMessage {
  type?: 'log' | 'status' | 'heartbeat';
  message?: string;
  status?: TaskStatus;
  task?: Task;
}

export function isActiveTaskStatus(status?: TaskStatus) {
  return status === 'pending' || status === 'running';
}

export function isTerminalTaskStatus(status?: TaskStatus) {
  return status === 'completed' || status === 'failed' || status === 'cancelled';
}

export function isFailedOrCancelledTaskStatus(status?: TaskStatus) {
  return status === 'failed' || status === 'cancelled';
}

export function isActiveTask(task?: Pick<Task, 'status'> | null) {
  return Boolean(task && isActiveTaskStatus(task.status));
}

export function canStopTask(task: Pick<Task, 'status' | 'cancellable'>) {
  return isActiveTask(task) && task.cancellable !== false;
}

export function taskFromStatusEvent(taskId: string, data: TaskStatusStreamMessage): Task {
  if (data.task) {
    return {
      ...data.task,
      status: data.task.status || data.status || 'pending',
      message: data.task.message || data.message || '',
    };
  }
  return {
    task_id: taskId,
    type: '',
    status: data.status || 'pending',
    message: data.message || '',
    created_at: '',
    updated_at: '',
  };
}

export function mergeTaskStatus(taskId: string, statusTask: Task, previous: Task | null): Task {
  return {
    task_id: statusTask.task_id || previous?.task_id || taskId,
    type: statusTask.type || previous?.type || '',
    status: statusTask.status,
    message: statusTask.message || previous?.message || '',
    result: statusTask.result ?? previous?.result,
    created_at: statusTask.created_at || previous?.created_at || '',
    updated_at: statusTask.updated_at || previous?.updated_at || '',
    display_name: statusTask.display_name ?? previous?.display_name,
    cancellable: statusTask.cancellable ?? previous?.cancellable,
    group_id: statusTask.group_id ?? previous?.group_id,
    ingestion_lock_key: statusTask.ingestion_lock_key ?? previous?.ingestion_lock_key,
  };
}
