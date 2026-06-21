'use client';

import type { Task } from '@/lib/api';
import type { TerminalTask } from '@/lib/taskStatus';
import { useTaskStream } from './useTaskStream';

interface UseTaskStatusOptions {
  enabled?: boolean;
  onStatus?: (task: Pick<Task, 'status' | 'message'>) => void;
  onTerminal?: (task: TerminalTask) => void | Promise<void>;
}

export function useTaskStatus(
  taskId: string | null | undefined,
  options: UseTaskStatusOptions = {},
) {
  const { connected, error, task } = useTaskStream(taskId, options);

  return {
    connected,
    error,
    task,
  };
}
