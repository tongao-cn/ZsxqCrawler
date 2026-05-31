'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import { apiClient, Task } from '@/lib/api';

interface UseTaskListOptions {
  autoRefresh?: boolean;
  errorThrottleMs?: number;
  groupId?: string | number | null;
  onError?: (error: unknown) => void;
  refreshIntervalMs?: number;
}

const DEFAULT_ERROR_THROTTLE_MS = 15000;

function normalizeGroupId(value?: string | number | null) {
  if (value === undefined || value === null) {
    return undefined;
  }
  const text = String(value).trim();
  return text || undefined;
}

export function useTaskList({
  autoRefresh = true,
  errorThrottleMs = DEFAULT_ERROR_THROTTLE_MS,
  groupId,
  onError,
  refreshIntervalMs = 3000,
}: UseTaskListOptions = {}) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(false);
  const lastErrorAtRef = useRef(0);
  const loadingRef = useRef(false);
  const onErrorRef = useRef(onError);
  const normalizedGroupId = normalizeGroupId(groupId);

  useEffect(() => {
    onErrorRef.current = onError;
  }, [onError]);

  const loadTasks = useCallback(async () => {
    if (loadingRef.current) {
      return;
    }

    try {
      loadingRef.current = true;
      setLoading(true);
      const data = await apiClient.getTasks(normalizedGroupId);
      setTasks(data);
      lastErrorAtRef.current = 0;
    } catch (error) {
      const now = Date.now();
      if (!lastErrorAtRef.current || now - lastErrorAtRef.current >= errorThrottleMs) {
        lastErrorAtRef.current = now;
        onErrorRef.current?.(error);
      }
    } finally {
      loadingRef.current = false;
      setLoading(false);
    }
  }, [errorThrottleMs, normalizedGroupId]);

  useEffect(() => {
    void loadTasks();
  }, [loadTasks]);

  useEffect(() => {
    if (!autoRefresh) {
      return;
    }

    const interval = window.setInterval(() => {
      void loadTasks();
    }, refreshIntervalMs);

    return () => window.clearInterval(interval);
  }, [autoRefresh, loadTasks, refreshIntervalMs]);

  return {
    loadTasks,
    loading,
    tasks,
  };
}
