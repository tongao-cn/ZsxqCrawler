'use client';

import { useCallback, useState } from 'react';
import { toast } from 'sonner';

import { apiClient } from '@/lib/api';
import type {
  DownloadSettingsValue,
  GroupDownloadOption,
  GroupFileLoading,
} from '@/components/GroupActionPanel';

interface UseDownloadActionsOptions {
  groupId: number;
  localFileCount: number;
  onTaskCreated: (taskId: string) => void;
  loadLocalFileCount: () => void | Promise<void>;
}

export function useDownloadActions({
  groupId,
  localFileCount,
  onTaskCreated,
  loadLocalFileCount,
}: UseDownloadActionsOptions) {
  const [fileLoading, setFileLoading] = useState<GroupFileLoading>(null);
  const [selectedDownloadOption, setSelectedDownloadOption] = useState<GroupDownloadOption>('time');
  const [downloadInterval, setDownloadInterval] = useState<number>(1.0);
  const [longSleepInterval, setLongSleepInterval] = useState<number>(60.0);
  const [filesPerBatch, setFilesPerBatch] = useState<number>(10);
  const [showSettingsDialog, setShowSettingsDialog] = useState<boolean>(false);
  const [downloadIntervalMin, setDownloadIntervalMin] = useState<number>(15);
  const [downloadIntervalMax, setDownloadIntervalMax] = useState<number>(30);
  const [longSleepIntervalMin, setLongSleepIntervalMin] = useState<number>(30);
  const [longSleepIntervalMax, setLongSleepIntervalMax] = useState<number>(60);
  const [useRandomInterval, setUseRandomInterval] = useState<boolean>(true);
  const [downloadDialogOpen, setDownloadDialogOpen] = useState<boolean>(false);
  const [downloadQuickLastDays, setDownloadQuickLastDays] = useState<number>(30);
  const [downloadRangeStartDate, setDownloadRangeStartDate] = useState<string>('');
  const [downloadRangeEndDate, setDownloadRangeEndDate] = useState<string>('');

  const canDownloadFiles = useCallback(() => {
    if (localFileCount === 0) {
      toast.error('当前没有可下载的文件记录，请先采集包含附件的话题');
      return false;
    }
    return true;
  }, [localFileCount]);

  const handleDownloadByTime = useCallback(async () => {
    if (!canDownloadFiles()) {
      return;
    }

    try {
      setFileLoading('download-time');
      const params: any = {
        downloadInterval,
        longSleepInterval,
        filesPerBatch,
        downloadIntervalMin: useRandomInterval ? downloadIntervalMin : undefined,
        downloadIntervalMax: useRandomInterval ? downloadIntervalMax : undefined,
        longSleepIntervalMin: useRandomInterval ? longSleepIntervalMin : undefined,
        longSleepIntervalMax: useRandomInterval ? longSleepIntervalMax : undefined,
      };

      if (downloadRangeStartDate || downloadRangeEndDate) {
        if (downloadRangeStartDate) params.startTime = downloadRangeStartDate;
        if (downloadRangeEndDate) params.endTime = downloadRangeEndDate;
      } else {
        params.lastDays = Math.max(1, downloadQuickLastDays || 1);
      }

      const response = await apiClient.downloadFilesByTimeRange(groupId, params);
      const taskId = (response as any).task_id;
      toast.success(`文件下载任务已创建: ${taskId}`);
      onTaskCreated(taskId);
      setDownloadDialogOpen(false);
    } catch (error) {
      toast.error(`文件下载失败: ${error instanceof Error ? error.message : '未知错误'}`);
    } finally {
      setFileLoading(null);
    }
  }, [
    canDownloadFiles,
    downloadInterval,
    downloadIntervalMax,
    downloadIntervalMin,
    downloadQuickLastDays,
    downloadRangeEndDate,
    downloadRangeStartDate,
    filesPerBatch,
    groupId,
    longSleepInterval,
    longSleepIntervalMax,
    longSleepIntervalMin,
    onTaskCreated,
    useRandomInterval,
  ]);

  const handleDownloadByCount = useCallback(async () => {
    if (!canDownloadFiles()) {
      return;
    }

    try {
      setFileLoading('download-count');
      const response = await apiClient.downloadFiles(
        groupId,
        undefined,
        'download_count',
        downloadInterval,
        longSleepInterval,
        filesPerBatch,
        useRandomInterval ? downloadIntervalMin : undefined,
        useRandomInterval ? downloadIntervalMax : undefined,
        useRandomInterval ? longSleepIntervalMin : undefined,
        useRandomInterval ? longSleepIntervalMax : undefined,
      );
      const taskId = (response as any).task_id;
      toast.success(`文件下载任务已创建: ${taskId}`);
      onTaskCreated(taskId);
    } catch (error) {
      toast.error(`文件下载失败: ${error instanceof Error ? error.message : '未知错误'}`);
    } finally {
      setFileLoading(null);
    }
  }, [
    canDownloadFiles,
    downloadInterval,
    downloadIntervalMax,
    downloadIntervalMin,
    filesPerBatch,
    groupId,
    longSleepInterval,
    longSleepIntervalMax,
    longSleepIntervalMin,
    onTaskCreated,
    useRandomInterval,
  ]);

  const handleClearFileDatabase = useCallback(async () => {
    try {
      setFileLoading('clear');
      await apiClient.clearFileDatabase(groupId);
      toast.success('文件数据库已删除');
      void loadLocalFileCount();
    } catch (error) {
      toast.error(`删除文件数据库失败: ${error instanceof Error ? error.message : '未知错误'}`);
    } finally {
      setFileLoading(null);
    }
  }, [groupId, loadLocalFileCount]);

  const handleSettingsChange = useCallback((settings: DownloadSettingsValue) => {
    setDownloadInterval(settings.downloadInterval);
    setLongSleepInterval(settings.longSleepInterval);
    setFilesPerBatch(settings.filesPerBatch);

    if (settings.downloadIntervalMin !== undefined) {
      setDownloadIntervalMin(settings.downloadIntervalMin);
      setDownloadIntervalMax(settings.downloadIntervalMax || 30);
      setLongSleepIntervalMin(settings.longSleepIntervalMin || 30);
      setLongSleepIntervalMax(settings.longSleepIntervalMax || 60);
      setUseRandomInterval(true);
    } else {
      setUseRandomInterval(false);
    }

    toast.success('下载设置已更新');
  }, []);

  return {
    fileLoading,
    selectedDownloadOption,
    setSelectedDownloadOption,
    downloadInterval,
    longSleepInterval,
    filesPerBatch,
    showSettingsDialog,
    setShowSettingsDialog,
    downloadIntervalMin,
    downloadIntervalMax,
    longSleepIntervalMin,
    longSleepIntervalMax,
    useRandomInterval,
    downloadDialogOpen,
    setDownloadDialogOpen,
    downloadQuickLastDays,
    setDownloadQuickLastDays,
    downloadRangeStartDate,
    setDownloadRangeStartDate,
    downloadRangeEndDate,
    setDownloadRangeEndDate,
    handleDownloadByTime,
    handleDownloadByCount,
    handleClearFileDatabase,
    handleSettingsChange,
  };
}
