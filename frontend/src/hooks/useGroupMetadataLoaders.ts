'use client';

import { useCallback, useEffect, useState } from 'react';

import { apiClient, Account, AccountSelf } from '@/lib/api';
import {
  EMPTY_LOCAL_FILE_STATS,
  normalizeGroupLocalFileStats,
  type GroupLocalFileStats,
} from '@/lib/group-workbench-read-model';

export function useGroupMetadataLoaders(groupId: number) {
  const [groupInfo, setGroupInfo] = useState<any>(null);
  const [localFileCount, setLocalFileCount] = useState<number>(0);
  const [localFileStats, setLocalFileStats] = useState<GroupLocalFileStats>(EMPTY_LOCAL_FILE_STATS);
  const [cacheInfo, setCacheInfo] = useState<any>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [groupAccount, setGroupAccount] = useState<Account | null>(null);
  const [selectedAccountId, setSelectedAccountId] = useState<string>('');
  const [accountSelf, setAccountSelf] = useState<AccountSelf | null>(null);
  const [hasColumns, setHasColumns] = useState<boolean>(false);
  const [columnsTitle, setColumnsTitle] = useState<string | null>(null);

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
      const normalizedStats = normalizeGroupLocalFileStats(stats);
      setLocalFileCount(normalizedStats.total);
      setLocalFileStats(normalizedStats);
    } catch (error) {
      console.error('加载本地文件数量失败:', error);
      setLocalFileCount(0);
      setLocalFileStats(EMPTY_LOCAL_FILE_STATS);
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
      const account = response.account || null;
      setGroupAccount(account);
      setSelectedAccountId(account?.id || '');
    } catch (err) {
      console.error('加载群组账号失败:', err);
    }
  }, [groupId]);

  const loadGroupAccountSelf = useCallback(async () => {
    try {
      const response = await apiClient.getGroupAccountSelf(groupId);
      setAccountSelf(response.self || null);
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
    accountSelf,
    accounts,
    cacheInfo,
    columnsTitle,
    groupAccount,
    groupInfo,
    hasColumns,
    loadCacheInfo,
    loadGroupAccount,
    loadGroupAccountSelf,
    loadLocalFileCount,
    localFileCount,
    localFileStats,
    selectedAccountId,
    setSelectedAccountId,
  };
}
