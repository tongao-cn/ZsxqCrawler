'use client';

import { useCallback } from 'react';
import { toast } from 'sonner';

import { getTaskConflictDetail } from '@/lib/api';

interface UseTaskLauncherOptions {
  onTaskCreated?: (taskId: string) => void;
  onTaskConflict?: (taskId: string) => void;
}

interface TaskLaunchResponse {
  task_id: string;
}

type TaskLaunchMessage = string | ((taskId: string) => string);

function resolveTaskLaunchMessage(message: TaskLaunchMessage | undefined, taskId: string) {
  return typeof message === 'function' ? message(taskId) : message;
}

export function useTaskLauncher({
  onTaskCreated,
  onTaskConflict,
}: UseTaskLauncherOptions) {
  const notifyTaskCreated = useCallback((taskId: string, message?: string) => {
    toast.success(message ?? `任务已创建: ${taskId}`);
    onTaskCreated?.(taskId);
  }, [onTaskCreated]);

  const notifyTaskLaunch = useCallback((response: TaskLaunchResponse, message?: TaskLaunchMessage) => {
    const taskId = response.task_id;
    notifyTaskCreated(taskId, resolveTaskLaunchMessage(message, taskId));
    return taskId;
  }, [notifyTaskCreated]);

  const handleTaskCreateError = useCallback((error: unknown, fallback: string) => {
    const conflict = getTaskConflictDetail(error);
    if (conflict?.task_id) {
      toast.error(`已有任务 ${conflict.task_id} 正在运行`);
      onTaskConflict?.(conflict.task_id);
      return;
    }

    toast.error(`${fallback}: ${error instanceof Error ? error.message : '未知错误'}`);
  }, [onTaskConflict]);

  return {
    handleTaskCreateError,
    notifyTaskLaunch,
    notifyTaskCreated,
  };
}
