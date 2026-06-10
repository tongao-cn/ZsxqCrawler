'use client';

import { useEffect, useRef, useState } from 'react';

import { API_BASE_URL, apiClient, Task } from '@/lib/api';

type TerminalTask = Task & { result?: unknown };
const TERMINAL_STATUSES: Task['status'][] = ['completed', 'failed', 'cancelled'];
const FALLBACK_POLL_INTERVAL_MS = 3000;

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
      setError(null);
      setTask(null);
      terminalHandledRef.current = false;
      return;
    }

    let cancelled = false;
    let fallbackPollTimer: number | null = null;
    let fallbackPollInFlight = false;
    terminalHandledRef.current = false;
    const eventSource = new EventSource(`${API_BASE_URL}/api/tasks/${taskId}/stream`);

    const stopFallbackPolling = () => {
      if (fallbackPollTimer !== null) {
        window.clearInterval(fallbackPollTimer);
        fallbackPollTimer = null;
      }
    };

    const handleTerminalTask = async (statusTask: TerminalTask, fetchFinalTask: boolean) => {
      if (terminalHandledRef.current) {
        return;
      }
      terminalHandledRef.current = true;
      stopFallbackPolling();
      eventSource.close();
      setConnected(false);

      if (!fetchFinalTask) {
        if (!cancelled) {
          setTask(statusTask);
          await onTerminalRef.current?.(statusTask);
        }
        return;
      }

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
    };

    const handleTaskStatus = (statusTask: Task) => {
      setTask((prev) => ({
        task_id: statusTask.task_id || prev?.task_id || taskId,
        type: statusTask.type || prev?.type || '',
        status: statusTask.status,
        message: statusTask.message || prev?.message || '',
        result: statusTask.result ?? prev?.result,
        created_at: statusTask.created_at || prev?.created_at || '',
        updated_at: statusTask.updated_at || prev?.updated_at || '',
        group_id: statusTask.group_id ?? prev?.group_id,
        ingestion_lock_key: statusTask.ingestion_lock_key ?? prev?.ingestion_lock_key,
      }));
      onStatusRef.current?.({ status: statusTask.status, message: statusTask.message || '' });
    };

    const pollTaskStatus = async () => {
      if (cancelled || terminalHandledRef.current || fallbackPollInFlight) {
        return;
      }
      try {
        fallbackPollInFlight = true;
        const polledTask = await apiClient.getTask(taskId);
        if (cancelled || terminalHandledRef.current) {
          return;
        }
        setError(null);
        if (TERMINAL_STATUSES.includes(polledTask.status)) {
          await handleTerminalTask(polledTask, false);
          return;
        }
        handleTaskStatus(polledTask);
      } catch {
        if (!cancelled && !terminalHandledRef.current) {
          setError('任务状态连接中断，正在轮询恢复');
        }
      } finally {
        fallbackPollInFlight = false;
      }
    };

    const startFallbackPolling = () => {
      if (fallbackPollTimer !== null || terminalHandledRef.current) {
        return;
      }
      void pollTaskStatus();
      fallbackPollTimer = window.setInterval(() => {
        void pollTaskStatus();
      }, FALLBACK_POLL_INTERVAL_MS);
    };

    eventSource.onopen = () => {
      if (!cancelled) {
        stopFallbackPolling();
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

        const statusTask: Task = {
          task_id: taskId,
          type: '',
          status: data.status,
          message: data.message || '',
          created_at: '',
          updated_at: '',
        };

        if (TERMINAL_STATUSES.includes(data.status)) {
          void handleTerminalTask(statusTask, true);
          return;
        }
        handleTaskStatus(statusTask);
      } catch {
        // Ignore malformed SSE payloads and wait for the next status update.
      }
    };

    eventSource.onerror = () => {
      if (!cancelled) {
        setConnected(false);
        setError('任务状态连接中断，正在轮询恢复');
        startFallbackPolling();
      }
    };

    return () => {
      cancelled = true;
      stopFallbackPolling();
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
