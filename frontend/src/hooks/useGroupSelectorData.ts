'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { apiClient, type Group, type GroupStats } from '@/lib/api';

const MAX_AUTO_RETRIES = 5;
const RETRYABLE_LOAD_ERROR_MARKERS = ['未知错误', '空数据', '反爬虫'];

function isRetryableLoadError(message: string) {
  return RETRYABLE_LOAD_ERROR_MARKERS.some((marker) => message.includes(marker));
}

export function useGroupSelectorData() {
  const [groups, setGroups] = useState<Group[]>([]);
  const [groupStats, setGroupStats] = useState<Record<number, GroupStats>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retryCount, setRetryCount] = useState(0);
  const [isRetrying, setIsRetrying] = useState(false);
  const [deletingGroups, setDeletingGroups] = useState<Set<number>>(new Set());
  const hasLoadedGroupsRef = useRef(false);
  const retryTimerRef = useRef<number | null>(null);
  const loadRequestRef = useRef(0);
  const statsRequestRef = useRef(0);

  const loadGroups = useCallback(async (currentRetryCount = 0) => {
    const loadRequestId = loadRequestRef.current + 1;
    loadRequestRef.current = loadRequestId;
    try {
      if (currentRetryCount === 0) {
        if (retryTimerRef.current) {
          window.clearTimeout(retryTimerRef.current);
          retryTimerRef.current = null;
        }
        statsRequestRef.current += 1;
        if (!hasLoadedGroupsRef.current) {
          setLoading(true);
        }
        setError(null);
        setRetryCount(0);
        setIsRetrying(false);
      } else {
        setIsRetrying(true);
        setRetryCount(currentRetryCount);
      }

      const data = await apiClient.getGroups();
      if (loadRequestRef.current !== loadRequestId) {
        return;
      }

      setGroups(data.groups);
      hasLoadedGroupsRef.current = true;
      setGroupStats({});
      const statsRequestId = statsRequestRef.current + 1;
      statsRequestRef.current = statsRequestId;

      setError(null);
      setRetryCount(0);
      setIsRetrying(false);
      setLoading(false);

      void (async () => {
        const statsPromises = data.groups.map(async (group: Group) => {
          try {
            const stats = await apiClient.getGroupStats(group.group_id);
            return { groupId: group.group_id, stats };
          } catch (error) {
            console.warn(`获取群组 ${group.group_id} 统计信息失败:`, error);
            return { groupId: group.group_id, stats: null };
          }
        });

        const statsResults = await Promise.all(statsPromises);
        const statsMap: Record<number, GroupStats> = {};
        statsResults.forEach(({ groupId, stats }) => {
          if (stats) {
            statsMap[groupId] = stats;
          }
        });
        if (statsRequestRef.current === statsRequestId) {
          setGroupStats(statsMap);
        }
      })();
    } catch (err) {
      if (loadRequestRef.current !== loadRequestId) {
        return;
      }
      const errorMessage = err instanceof Error ? err.message : '加载群组列表失败';

      if (isRetryableLoadError(errorMessage) && currentRetryCount < MAX_AUTO_RETRIES) {
        const nextRetryCount = currentRetryCount + 1;
        const delay = Math.min(1000 + (nextRetryCount * 500), 5000);

        if (retryTimerRef.current) {
          window.clearTimeout(retryTimerRef.current);
        }
        retryTimerRef.current = window.setTimeout(() => {
          retryTimerRef.current = null;
          void loadGroups(nextRetryCount);
        }, delay);
        return;
      }

      setError(isRetryableLoadError(errorMessage) ? `${errorMessage}，自动重试已达上限` : errorMessage);
      setIsRetrying(false);
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadGroups();
  }, [loadGroups]);

  useEffect(() => {
    return () => {
      if (retryTimerRef.current) {
        window.clearTimeout(retryTimerRef.current);
        retryTimerRef.current = null;
      }
      loadRequestRef.current += 1;
      statsRequestRef.current += 1;
    };
  }, []);

  useEffect(() => {
    let lastRefresh = 0;
    const refreshInterval = 5000;

    const maybeRefresh = () => {
      const now = Date.now();
      if (now - lastRefresh > refreshInterval) {
        lastRefresh = now;
        void loadGroups(0);
      }
    };

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        maybeRefresh();
      }
    };
    const handleFocus = () => {
      maybeRefresh();
    };
    document.addEventListener('visibilitychange', handleVisibilityChange);
    window.addEventListener('focus', handleFocus);
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.removeEventListener('focus', handleFocus);
    };
  }, [loadGroups]);

  const refreshLocalGroups = useCallback(async () => {
    try {
      await apiClient.refreshLocalGroups();
      await loadGroups(0);
      toast.success('已刷新本地群目录');
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      toast.error(`刷新失败: ${msg}`);
    }
  }, [loadGroups]);

  const deleteGroup = useCallback(async (groupId: number) => {
    if (deletingGroups.has(groupId)) return;
    setDeletingGroups((prev) => new Set(prev).add(groupId));
    try {
      const res = await apiClient.deleteGroup(groupId);
      const msg = res.message || '已删除';
      toast.success(msg);
      await loadGroups(0);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      toast.error(`删除失败: ${msg}`);
    } finally {
      setDeletingGroups((prev) => {
        const next = new Set(prev);
        next.delete(groupId);
        return next;
      });
    }
  }, [deletingGroups, loadGroups]);

  return {
    deleteGroup,
    deletingGroups,
    error,
    groupStats,
    groups,
    isRetrying,
    loadGroups,
    loading,
    refreshLocalGroups,
    retryCount,
  };
}
