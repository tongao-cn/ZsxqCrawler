'use client';

import { useEffect, useRef, useState } from 'react';

import { API_BASE_URL, apiClient, Task } from '@/lib/api';

type TerminalTask = Task & { result?: unknown };

interface UseTaskStatusOptions {
  enabled?: boolean;
  onStatus?: (task: Pick<Task, 'status' | 'message'>) => void;
  onTerminal?: (task: TerminalTask) => void | Promise<void>;
}

export function useTaskStatus(
  taskId: string | null | undefined,
  {
    enabled = true,
    onStatus,
    onTerminal,
  }: UseTaskStatusOptions = {},
) {
  const [task, setTask] = useState<Task | null>(null);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const onStatusRef = useRef(onStatus);
  const onTerminalRef = useRef(onTerminal);
  const terminalHandledRef = useRef(false);

  useEffect(() => {
    onStatusRef.current = onStatus;
  }, [onStatus]);

  useEffect(() => {
    onTerminalRef.current = onTerminal;
  }, [onTerminal]);

  useEffect(() => {
    if (!taskId || !enabled) {
      setConnected(false);
      terminalHandledRef.current = false;
      return;
    }

    let cancelled = false;
    terminalHandledRef.current = false;
    const eventSource = new EventSource(`${API_BASE_URL}/api/tasks/${taskId}/stream`);

    eventSource.onopen = () => {
      if (!cancelled) {
        setConnected(true);
        setError(null);
      }
    };

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as { type?: string; status?: Task['status']; message?: string };
        if (data.type !== 'status' || !data.status) {
          return;
        }

        const statusTask = {
          task_id: taskId,
          type: '',
          status: data.status,
          message: data.message || '',
          created_at: '',
          updated_at: '',
        };
        setTask((prev) => ({ ...statusTask, ...prev, status: data.status!, message: data.message || prev?.message || '' }));
        onStatusRef.current?.({ status: data.status, message: data.message || '' });

        if (['completed', 'failed', 'cancelled'].includes(data.status) && !terminalHandledRef.current) {
          terminalHandledRef.current = true;
          eventSource.close();
          setConnected(false);
          void (async () => {
            try {
              const finalTask = await apiClient.getTask(taskId);
              if (!cancelled) {
                setTask(finalTask);
                await onTerminalRef.current?.(finalTask);
              }
            } catch {
              if (!cancelled) {
                await onTerminalRef.current?.(statusTask);
              }
            }
          })();
        }
      } catch {
        // Ignore malformed SSE payloads and wait for the next status update.
      }
    };

    eventSource.onerror = () => {
      if (!cancelled) {
        setConnected(false);
        setError('任务状态连接中断');
      }
    };

    return () => {
      cancelled = true;
      eventSource.close();
      setConnected(false);
    };
  }, [enabled, taskId]);

  return {
    connected,
    error,
    task,
  };
}
