'use client';

import { useCallback } from 'react';
import { toast } from 'sonner';

import { getTaskConflictDetail } from '@/lib/api';

interface UseTaskLauncherOptions {
  onTaskCreated?: (taskId: string) => void;
  onTaskConflict?: (taskId: string) => void;
}

export function useTaskLauncher({
  onTaskCreated,
  onTaskConflict,
}: UseTaskLauncherOptions) {
  const notifyTaskCreated = useCallback((taskId: string, message?: string) => {
    toast.success(message ?? `任务已创建: ${taskId}`);
    onTaskCreated?.(taskId);
  }, [onTaskCreated]);

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
    notifyTaskCreated,
  };
}
