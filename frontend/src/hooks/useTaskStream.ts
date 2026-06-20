'use client';

import { useEffect, useRef, useState } from 'react';

import { API_BASE_URL, apiClient } from '@/lib/api';
import type { Task, TaskLogsResponse } from '@/lib/api';
import { useSyncedRef } from './useSyncedRef';

export type TerminalTask = Task & { result?: unknown };

type TaskStatusSnapshot = Pick<Task, 'status' | 'message'>;

interface TaskStreamMessage {
  type?: 'log' | 'status' | 'heartbeat';
  message?: string;
  status?: Task['status'];
}

interface UseTaskStreamOptions {
  enabled?: boolean;
  collectLogs?: boolean;
  maxLogs?: number;
  onLog?: (message: string) => void;
  onStatus?: (task: TaskStatusSnapshot) => void;
  onTerminal?: (task: TerminalTask) => void | Promise<void>;
}

const TERMINAL_STATUSES: Task['status'][] = ['completed', 'failed', 'cancelled'];
const FALLBACK_POLL_INTERVAL_MS = 3000;
const DEFAULT_MAX_LOGS = 2000;

function isTerminalTaskStatus(status: Task['status']) {
  return TERMINAL_STATUSES.includes(status);
}

function taskFromStatusEvent(taskId: string, data: TaskStreamMessage): Task {
  return {
    task_id: taskId,
    type: '',
    status: data.status || 'pending',
    message: data.message || '',
    created_at: '',
    updated_at: '',
  };
}

function mergeTaskStatus(taskId: string, statusTask: Task, previous: Task | null): Task {
  return {
    task_id: statusTask.task_id || previous?.task_id || taskId,
    type: statusTask.type || previous?.type || '',
    status: statusTask.status,
    message: statusTask.message || previous?.message || '',
    result: statusTask.result ?? previous?.result,
    created_at: statusTask.created_at || previous?.created_at || '',
    updated_at: statusTask.updated_at || previous?.updated_at || '',
    group_id: statusTask.group_id ?? previous?.group_id,
    ingestion_lock_key: statusTask.ingestion_lock_key ?? previous?.ingestion_lock_key,
  };
}

function trimLogs(logs: string[], maxLogs: number) {
  return logs.length > maxLogs ? logs.slice(-maxLogs) : logs;
}

export function useTaskStream(
  taskId: string | null | undefined,
  {
    enabled = true,
    collectLogs = false,
    maxLogs = DEFAULT_MAX_LOGS,
    onLog,
    onStatus,
    onTerminal,
  }: UseTaskStreamOptions = {},
) {
  const [task, setTask] = useState<Task | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const onLogRef = useSyncedRef(onLog);
  const onStatusRef = useSyncedRef(onStatus);
  const onTerminalRef = useSyncedRef(onTerminal);
  const observedLogCountRef = useRef(0);
  const terminalHandledRef = useRef(false);

  useEffect(() => {
    if (!taskId || !enabled) {
      setConnected(false);
      setError(null);
      setTask(null);
      setLogs([]);
      observedLogCountRef.current = 0;
      terminalHandledRef.current = false;
      return;
    }

    let cancelled = false;
    let fallbackPollTimer: number | null = null;
    let fallbackPollInFlight = false;
    terminalHandledRef.current = false;
    observedLogCountRef.current = 0;
    const eventSource = new EventSource(`${API_BASE_URL}/api/tasks/${taskId}/stream`);

    const stopFallbackPolling = () => {
      if (fallbackPollTimer !== null) {
        window.clearInterval(fallbackPollTimer);
        fallbackPollTimer = null;
      }
    };

    const closeStream = () => {
      eventSource.close();
      setConnected(false);
    };

    const replaceLogs = (logsResponse: TaskLogsResponse) => {
      if (!collectLogs) {
        return;
      }
      if (logsResponse.logs.length < observedLogCountRef.current) {
        observedLogCountRef.current = 0;
      }
      const newLogs = logsResponse.logs.slice(observedLogCountRef.current);
      observedLogCountRef.current = logsResponse.logs.length;
      newLogs.forEach((message) => onLogRef.current?.(message));
      setLogs(trimLogs(logsResponse.logs, maxLogs));
    };

    const appendLog = (message: string) => {
      if (!collectLogs) {
        return;
      }
      observedLogCountRef.current += 1;
      setLogs((previousLogs) => trimLogs([...previousLogs, message], maxLogs));
      onLogRef.current?.(message);
    };

    const handleTaskStatus = (statusTask: Task) => {
      setTask((previousTask) => mergeTaskStatus(taskId, statusTask, previousTask));
      onStatusRef.current?.({ status: statusTask.status, message: statusTask.message || '' });
    };

    const fetchTaskLogs = async () => {
      if (!collectLogs) {
        return;
      }
      const logsResponse = await apiClient.getTaskLogs(taskId);
      if (!cancelled) {
        replaceLogs(logsResponse);
      }
    };

    const handleTerminalTask = async (statusTask: TerminalTask, fetchFinalTask: boolean) => {
      if (terminalHandledRef.current) {
        return;
      }
      terminalHandledRef.current = true;
      stopFallbackPolling();
      closeStream();

      let terminalTask = statusTask;
      if (fetchFinalTask) {
        try {
          terminalTask = await apiClient.getTask(taskId);
        } catch {
          terminalTask = statusTask;
        }
      }

      try {
        await fetchTaskLogs();
      } catch {
        // Logs are supplemental; status completion should still be delivered.
      }

      if (!cancelled) {
        setTask(terminalTask);
        await onTerminalRef.current?.(terminalTask);
      }
    };

    const pollTaskSnapshot = async () => {
      if (cancelled || terminalHandledRef.current || fallbackPollInFlight) {
        return;
      }

      try {
        fallbackPollInFlight = true;
        const taskPromise = apiClient.getTask(taskId);
        const logsPromise = collectLogs ? apiClient.getTaskLogs(taskId) : Promise.resolve(null);
        const [polledTask, logsResponse] = await Promise.all([taskPromise, logsPromise]);

        if (cancelled || terminalHandledRef.current) {
          return;
        }

        setError(null);
        if (logsResponse) {
          replaceLogs(logsResponse);
        }
        if (isTerminalTaskStatus(polledTask.status)) {
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
      void pollTaskSnapshot();
      fallbackPollTimer = window.setInterval(() => {
        void pollTaskSnapshot();
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
        const data = JSON.parse(event.data) as TaskStreamMessage;
        if (data.type === 'log' && data.message) {
          appendLog(data.message);
          return;
        }
        if (data.type !== 'status' || !data.status) {
          return;
        }

        const statusTask = taskFromStatusEvent(taskId, data);
        if (isTerminalTaskStatus(data.status)) {
          void handleTerminalTask(statusTask, true);
          return;
        }
        handleTaskStatus(statusTask);
      } catch {
        // Ignore malformed SSE payloads and wait for the next update.
      }
    };

    eventSource.onerror = () => {
      if (!cancelled && !terminalHandledRef.current) {
        closeStream();
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
  }, [collectLogs, enabled, maxLogs, onLogRef, onStatusRef, onTerminalRef, taskId]);

  return {
    connected,
    error,
    logs,
    status: task?.status || 'pending',
    task,
  };
}
