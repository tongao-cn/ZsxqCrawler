'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { apiClient, Group, GroupStats, Topic } from '@/lib/api';
import { useInitialLoad } from '@/hooks/useInitialLoad';
import { useGroupMetadataLoaders } from '@/hooks/useGroupMetadataLoaders';

interface UseGroupDataLoadersOptions {
  groupId: number;
  currentPage: number;
  debouncedSearchTerm: string;
}

const MAX_AUTO_RETRIES = 5;
const RETRYABLE_LOAD_ERROR_MARKERS = ['未知错误', '空数据', '反爬虫'];

function isRetryableLoadError(message: string) {
  return RETRYABLE_LOAD_ERROR_MARKERS.some((marker) => message.includes(marker));
}

export function useGroupDataLoaders({
  groupId,
  currentPage,
  debouncedSearchTerm,
}: UseGroupDataLoadersOptions) {
  const [group, setGroup] = useState<Group | null>(null);
  const [groupStats, setGroupStats] = useState<GroupStats | null>(null);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [loading, setLoading] = useState(true);
  const [topicsLoading, setTopicsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retryCount, setRetryCount] = useState(0);
  const [isRetrying, setIsRetrying] = useState(false);
  const [totalPages, setTotalPages] = useState(1);
  const groupDetailRetryTimerRef = useRef<number | null>(null);
  const topicsRetryTimerRef = useRef<number | null>(null);
  const metadata = useGroupMetadataLoaders(groupId);

  const loadGroupDetail = useCallback(async (currentRetryCount = 0) => {
    try {
      if (currentRetryCount === 0) {
        if (groupDetailRetryTimerRef.current) {
          window.clearTimeout(groupDetailRetryTimerRef.current);
          groupDetailRetryTimerRef.current = null;
        }
        setLoading(true);
        setError(null);
        setRetryCount(0);
        setIsRetrying(false);
      } else {
        setIsRetrying(true);
        setRetryCount(currentRetryCount);
      }

      const data = await apiClient.getGroups();

      if (!data || !data.groups || data.groups.length === 0) {
        throw new Error('API返回空数据，可能是反爬虫机制');
      }

      const foundGroup = data.groups.find((item) => item.group_id === groupId);

      if (foundGroup) {
        if (groupDetailRetryTimerRef.current) {
          window.clearTimeout(groupDetailRetryTimerRef.current);
          groupDetailRetryTimerRef.current = null;
        }
        setGroup(foundGroup);
        setError(null);
        setRetryCount(0);
        setIsRetrying(false);
        setLoading(false);
      } else {
        setError('未找到指定的群组');
        setIsRetrying(false);
        setLoading(false);
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : '加载群组详情失败';

      if (isRetryableLoadError(errorMessage) && currentRetryCount < MAX_AUTO_RETRIES) {
        const nextRetryCount = currentRetryCount + 1;
        const delay = Math.min(1000 + (nextRetryCount * 500), 5000);

        if (groupDetailRetryTimerRef.current) {
          window.clearTimeout(groupDetailRetryTimerRef.current);
        }
        groupDetailRetryTimerRef.current = window.setTimeout(() => {
          groupDetailRetryTimerRef.current = null;
          loadGroupDetail(nextRetryCount);
        }, delay);
        return;
      }

      setError(isRetryableLoadError(errorMessage) ? `${errorMessage}，自动重试已达上限` : errorMessage);
      setIsRetrying(false);
      setLoading(false);
    }
  }, [groupId]);

  const loadGroupStats = useCallback(async () => {
    try {
      const stats = await apiClient.getGroupStats(groupId);
      setGroupStats(stats);
    } catch (err) {
      console.error('加载群组统计失败:', err);
    }
  }, [groupId]);

  const loadTopics = useCallback(async (currentRetryCount = 0) => {
    try {
      if (currentRetryCount === 0) {
        if (topicsRetryTimerRef.current) {
          window.clearTimeout(topicsRetryTimerRef.current);
          topicsRetryTimerRef.current = null;
        }
        setTopicsLoading(true);
      }

      const data = await apiClient.getGroupTopics(groupId, currentPage, 20, debouncedSearchTerm || undefined);

      if (!data || !data.data) {
        throw new Error('API返回空数据，可能是反爬虫机制');
      }

      setTopics(data.data);
      setTotalPages(data.pagination.pages);
      setTopicsLoading(false);
      if (topicsRetryTimerRef.current) {
        window.clearTimeout(topicsRetryTimerRef.current);
        topicsRetryTimerRef.current = null;
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : '加载话题列表失败';

      if (isRetryableLoadError(errorMessage) && currentRetryCount < MAX_AUTO_RETRIES) {
        const nextRetryCount = currentRetryCount + 1;
        const delay = Math.min(1000 + (nextRetryCount * 300), 3000);

        if (topicsRetryTimerRef.current) {
          window.clearTimeout(topicsRetryTimerRef.current);
        }
        topicsRetryTimerRef.current = window.setTimeout(() => {
          topicsRetryTimerRef.current = null;
          loadTopics(nextRetryCount);
        }, delay);
        return;
      }

      console.error('加载话题列表失败:', err);
      setTopicsLoading(false);
    }
  }, [currentPage, debouncedSearchTerm, groupId]);

  useEffect(() => {
    loadTopics();
  }, [loadTopics]);

  useEffect(() => {
    return () => {
      if (groupDetailRetryTimerRef.current) {
        window.clearTimeout(groupDetailRetryTimerRef.current);
        groupDetailRetryTimerRef.current = null;
      }
    };
  }, [loadGroupDetail]);

  useEffect(() => {
    return () => {
      if (topicsRetryTimerRef.current) {
        window.clearTimeout(topicsRetryTimerRef.current);
        topicsRetryTimerRef.current = null;
      }
    };
  }, [loadTopics]);

  const criticalLoaders = useMemo(() => [
    loadGroupDetail,
    loadGroupStats,
  ], [
    loadGroupDetail,
    loadGroupStats,
  ]);

  useInitialLoad({ loaders: criticalLoaders });

  return {
    group,
    groupStats,
    topics,
    setTopics,
    loading,
    topicsLoading,
    error,
    retryCount,
    isRetrying,
    totalPages,
    groupInfo: metadata.groupInfo,
    localFileCount: metadata.localFileCount,
    localFileStats: metadata.localFileStats,
    cacheInfo: metadata.cacheInfo,
    accounts: metadata.accounts,
    groupAccount: metadata.groupAccount,
    selectedAccountId: metadata.selectedAccountId,
    setSelectedAccountId: metadata.setSelectedAccountId,
    accountSelf: metadata.accountSelf,
    hasColumns: metadata.hasColumns,
    columnsTitle: metadata.columnsTitle,
    loadGroupDetail,
    loadGroupStats,
    loadTopics,
    loadLocalFileCount: metadata.loadLocalFileCount,
    loadGroupAccount: metadata.loadGroupAccount,
    loadGroupAccountSelf: metadata.loadGroupAccountSelf,
    loadCacheInfo: metadata.loadCacheInfo,
  };
}
