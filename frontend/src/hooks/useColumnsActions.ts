'use client';

import { useCallback, useState } from 'react';
import { toast } from 'sonner';
import { apiClient, ColumnsFetchSettings } from '@/lib/api';

interface UseColumnsActionsParams {
  groupId: string;
  loadColumns: () => Promise<void>;
  resetColumnsData: () => void;
}

export function useColumnsActions({ groupId, loadColumns, resetColumnsData }: UseColumnsActionsParams) {
  const [fetchingColumns, setFetchingColumns] = useState(false);
  const [currentTaskId, setCurrentTaskId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  const handleFetchColumns = useCallback(async (settings: ColumnsFetchSettings) => {
    try {
      setFetchingColumns(true);
      const result = await apiClient.fetchGroupColumns(groupId, settings);
      if (result.success) {
        setCurrentTaskId(result.task_id);
        toast.success(settings.incrementalMode ? '增量采集任务已启动（跳过已存在）' : '全量采集任务已启动');
      }
    } catch (error) {
      console.error('启动专栏采集失败:', error);
      toast.error(`启动专栏采集失败: ${error instanceof Error ? error.message : '未知错误'}`);
      setFetchingColumns(false);
    }
  }, [groupId]);

  const handleDeleteAllColumns = useCallback(async () => {
    try {
      setDeleting(true);
      const result = await apiClient.deleteAllColumns(groupId);
      if (result.success) {
        toast.success(`已清空专栏数据：删除 ${result.deleted.columns_deleted} 个专栏，${result.deleted.details_deleted} 篇文章`);
        resetColumnsData();
        await loadColumns();
      }
    } catch (error) {
      console.error('删除专栏数据失败:', error);
      toast.error(`删除专栏数据失败: ${error instanceof Error ? error.message : '未知错误'}`);
    } finally {
      setDeleting(false);
    }
  }, [groupId, loadColumns, resetColumnsData]);

  const clearColumnsTask = useCallback(() => {
    setCurrentTaskId(null);
    setFetchingColumns(false);
  }, []);

  const handleTaskStop = useCallback(() => {
    clearColumnsTask();
    loadColumns();
  }, [clearColumnsTask, loadColumns]);

  return {
    fetchingColumns,
    currentTaskId,
    deleting,
    handleFetchColumns,
    handleDeleteAllColumns,
    clearColumnsTask,
    handleTaskStop,
  };
}
