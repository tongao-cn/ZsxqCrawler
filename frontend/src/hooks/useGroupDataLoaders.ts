'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';

import { apiClient, Account, AccountSelf, Group, GroupStats, Topic } from '@/lib/api';
import { useInitialLoad } from '@/hooks/useInitialLoad';

interface GroupLocalFileStats {
  total: number;
  downloaded: number;
  pending: number;
  failed: number;
}

interface UseGroupDataLoadersOptions {
  groupId: number;
  currentPage: number;
  debouncedSearchTerm: string;
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
  const [groupInfo, setGroupInfo] = useState<any>(null);
  const [localFileCount, setLocalFileCount] = useState<number>(0);
  const [localFileStats, setLocalFileStats] = useState<GroupLocalFileStats>({
    total: 0,
    downloaded: 0,
    pending: 0,
    failed: 0,
  });
  const [cacheInfo, setCacheInfo] = useState<any>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [groupAccount, setGroupAccount] = useState<Account | null>(null);
  const [selectedAccountId, setSelectedAccountId] = useState<string>('');
  const [accountSelf, setAccountSelf] = useState<AccountSelf | null>(null);
  const [hasColumns, setHasColumns] = useState<boolean>(false);
  const [columnsTitle, setColumnsTitle] = useState<string | null>(null);

  const loadGroupDetail = useCallback(async (currentRetryCount = 0) => {
    try {
      if (currentRetryCount === 0) {
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

      if (errorMessage.includes('未知错误') || errorMessage.includes('空数据') || errorMessage.includes('反爬虫')) {
        const nextRetryCount = currentRetryCount + 1;
        const delay = Math.min(1000 + (nextRetryCount * 500), 5000);

        window.setTimeout(() => {
          loadGroupDetail(nextRetryCount);
        }, delay);
        return;
      }

      setError(errorMessage);
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
        setTopicsLoading(true);
      }

      const data = await apiClient.getGroupTopics(groupId, currentPage, 20, debouncedSearchTerm || undefined);

      if (!data || !data.data) {
        throw new Error('API返回空数据，可能是反爬虫机制');
      }

      setTopics(data.data);
      setTotalPages(data.pagination.pages);
      setTopicsLoading(false);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : '加载话题列表失败';

      if (errorMessage.includes('未知错误') || errorMessage.includes('空数据') || errorMessage.includes('反爬虫')) {
        const nextRetryCount = currentRetryCount + 1;
        const delay = Math.min(1000 + (nextRetryCount * 300), 3000);

        window.setTimeout(() => {
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

  const loadGroupInfo = useCallback(async () => {
    try {
      const info = await apiClient.getGroupInfo(groupId);
      setGroupInfo(info);
    } catch (error) {
      console.error('加载群组信息失败:', error);
    }
  }, [groupId]);

  const loadLocalFileCount = useCallback(async () => {
    try {
      const stats = await apiClient.getFileStats(groupId);
      const downloadStats = stats.download_stats || {};
      const total = downloadStats.total_files || 0;
      setLocalFileCount(total);
      setLocalFileStats({
        total,
        downloaded: downloadStats.downloaded || 0,
        pending: downloadStats.pending || 0,
        failed: downloadStats.failed || 0,
      });
    } catch (error) {
      console.error('加载本地文件数量失败:', error);
      setLocalFileCount(0);
      setLocalFileStats({
        total: 0,
        downloaded: 0,
        pending: 0,
        failed: 0,
      });
    }
  }, [groupId]);

  const loadAccounts = useCallback(async () => {
    try {
      const response = await apiClient.listAccounts();
      setAccounts(response.accounts || []);
    } catch (err) {
      console.error('加载账号列表失败:', err);
    }
  }, []);

  const loadGroupAccount = useCallback(async () => {
    try {
      const response = await apiClient.getGroupAccount(groupId);
      const account = (response as any)?.account || null;
      setGroupAccount(account);
      setSelectedAccountId(account?.id || '');
    } catch (err) {
      console.error('加载群组账号失败:', err);
    }
  }, [groupId]);

  const loadGroupAccountSelf = useCallback(async () => {
    try {
      const response = await apiClient.getGroupAccountSelf(groupId);
      setAccountSelf((response as any)?.self || null);
    } catch (err) {
      console.error('加载账号用户信息失败:', err);
    }
  }, [groupId]);

  const loadCacheInfo = useCallback(async () => {
    try {
      const info = await apiClient.getImageCacheInfo(groupId.toString());
      setCacheInfo(info);
    } catch (error) {
      console.error('加载缓存信息失败:', error);
    }
  }, [groupId]);

  const loadColumnsSummary = useCallback(async () => {
    try {
      const summary = await apiClient.getGroupColumnsSummary(groupId);
      setHasColumns(summary.has_columns);
      setColumnsTitle(summary.title);
    } catch (error) {
      console.error('加载专栏信息失败:', error);
      setHasColumns(false);
      setColumnsTitle(null);
    }
  }, [groupId]);

  const criticalLoaders = useMemo(() => [
    loadGroupDetail,
    loadGroupStats,
  ], [
    loadGroupDetail,
    loadGroupStats,
  ]);

  useInitialLoad({ loaders: criticalLoaders });

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      void loadGroupInfo();
      void loadLocalFileCount();
      void loadCacheInfo();
      void loadGroupAccount();
      void loadAccounts();
      void loadGroupAccountSelf();
      void loadColumnsSummary();
    }, 0);
    return () => window.clearTimeout(timeout);
  }, [
    loadAccounts,
    loadCacheInfo,
    loadColumnsSummary,
    loadGroupAccount,
    loadGroupAccountSelf,
    loadGroupInfo,
    loadLocalFileCount,
  ]);

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
    groupInfo,
    localFileCount,
    localFileStats,
    cacheInfo,
    accounts,
    groupAccount,
    selectedAccountId,
    setSelectedAccountId,
    accountSelf,
    hasColumns,
    columnsTitle,
    loadGroupDetail,
    loadGroupStats,
    loadTopics,
    loadLocalFileCount,
    loadGroupAccount,
    loadGroupAccountSelf,
    loadCacheInfo,
  };
}
