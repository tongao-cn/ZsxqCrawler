'use client';

import { useCallback, useState } from 'react';
import { toast } from 'sonner';

import { apiClient, FileAIAnalysis, FileItem } from '@/lib/api';
import type { FileTaskState } from '@/hooks/useFileTaskTracker';
import { useFileTaskTracker } from '@/hooks/useFileTaskTracker';
import { useTaskLauncher } from '@/hooks/useTaskLauncher';
import { isFailedOrCancelledTaskStatus } from '@/lib/taskStatus';

interface UseGroupFileTasksOptions {
  groupId: number;
  onTaskConflict?: (taskId: string) => void;
  onTaskCreated?: (taskId: string) => void;
  selectedFile: FileItem | null;
  setAnalysis: (analysis: FileAIAnalysis | null) => void;
  setAnalysisLoading: (loading: boolean) => void;
}

type RefreshFiles = () => Promise<void>;

export function useGroupFileTasks({
  groupId,
  onTaskConflict,
  onTaskCreated,
  selectedFile,
  setAnalysis,
  setAnalysisLoading,
}: UseGroupFileTasksOptions) {
  const downloadTasks = useFileTaskTracker();
  const analysisFileTasks = useFileTaskTracker();
  const [batchDownloadTaskId, setBatchDownloadTaskId] = useState<string | null>(null);
  const [batchDownloadFileIds, setBatchDownloadFileIds] = useState<number[]>([]);
  const [batchAnalysisTaskId, setBatchAnalysisTaskId] = useState<string | null>(null);
  const [batchAnalysisFileIds, setBatchAnalysisFileIds] = useState<number[]>([]);
  const [batchAnalyzing, setBatchAnalyzing] = useState(false);
  const { handleTaskCreateError, notifyTaskLaunch } = useTaskLauncher({
    onTaskConflict,
    onTaskCreated,
  });

  const trackAnalysisTask = useCallback((fileId: number, taskId: string, message = '分析任务已创建') => {
    analysisFileTasks.trackTask(fileId, taskId, message);
  }, [analysisFileTasks]);

  const handleFileTaskTerminal = useCallback(async (
    fileId: number,
    taskId: string,
    status: FileTaskState['status'],
    message: string,
    refreshFiles: RefreshFiles,
  ) => {
    downloadTasks.updateTask(fileId, taskId, status, message);
    downloadTasks.markFileActive(fileId, false);
    await refreshFiles();
  }, [downloadTasks]);

  const handleBatchDownloadTerminal = useCallback(async (
    status: FileTaskState['status'],
    message: string,
    refreshFiles: RefreshFiles,
  ) => {
    const completedFileIds = batchDownloadFileIds.slice();
    downloadTasks.markFilesActive(completedFileIds, false);
    setBatchDownloadTaskId(null);
    setBatchDownloadFileIds([]);
    if (status === 'completed') {
      toast.success(message || '当前页文件下载任务完成');
    } else if (isFailedOrCancelledTaskStatus(status)) {
      toast.error(message || '当前页文件下载任务未完成');
    }
    await refreshFiles();
  }, [batchDownloadFileIds, downloadTasks]);

  const handleAnalysisTaskTerminal = useCallback(async (
    fileId: number,
    taskId: string,
    status: FileTaskState['status'],
    message: string,
    refreshFiles: RefreshFiles,
  ) => {
    analysisFileTasks.updateTask(fileId, taskId, status, message);
    analysisFileTasks.markFileActive(fileId, false);

    if (selectedFile?.file_id === fileId) {
      setAnalysisLoading(false);
      try {
        const cached = await apiClient.getFileAIAnalysis(groupId, fileId);
        setAnalysis(cached.analysis || {
          file_id: fileId,
          status,
          error_message: status === 'completed' ? '分析结果尚未写入，请稍后刷新' : message,
        });
      } catch (error) {
        setAnalysis({
          file_id: fileId,
          status: 'failed',
          error_message: error instanceof Error ? error.message : '读取分析结果失败',
        });
      }
    }

    if (status === 'completed') {
      toast.success('文件分析完成');
    } else if (isFailedOrCancelledTaskStatus(status)) {
      toast.error(message || '文件分析未完成');
    }
    await refreshFiles();
  }, [
    analysisFileTasks,
    groupId,
    selectedFile,
    setAnalysis,
    setAnalysisLoading,
  ]);

  const handleBatchAnalysisTerminal = useCallback(async (
    status: FileTaskState['status'],
    message: string,
    refreshFiles: RefreshFiles,
  ) => {
    const completedFileIds = batchAnalysisFileIds.slice();
    analysisFileTasks.markFilesActive(completedFileIds, false);
    setBatchAnalyzing(false);
    setBatchAnalysisTaskId(null);
    setBatchAnalysisFileIds([]);
    if (status === 'completed') {
      toast.success(message || '当前页文件分析完成');
    } else if (isFailedOrCancelledTaskStatus(status)) {
      toast.error(message || '当前页文件分析未完成');
    }
    await refreshFiles();
  }, [analysisFileTasks, batchAnalysisFileIds]);

  const handleDownloadFile = useCallback(async (file: FileItem) => {
    if (downloadTasks.activeFileIds.has(file.file_id)) {
      return;
    }

    try {
      downloadTasks.markFileActive(file.file_id, true);
      const response = await apiClient.downloadSingleFile(
        String(groupId),
        file.file_id,
        file.name,
        file.size,
      );
      const taskId = notifyTaskLaunch(response, (createdTaskId) => `文件下载任务已创建: ${createdTaskId}`);
      downloadTasks.updateTask(file.file_id, taskId, 'pending', '下载任务已创建');
    } catch (error) {
      handleTaskCreateError(error, '文件下载失败');
      downloadTasks.markFileActive(file.file_id, false);
    }
  }, [
    downloadTasks,
    groupId,
    handleTaskCreateError,
    notifyTaskLaunch,
  ]);

  const handleBatchDownloadCurrentPage = useCallback(async (downloadableFiles: FileItem[]) => {
    if (downloadableFiles.length === 0) {
      return;
    }

    const filesToDownload = downloadableFiles.slice();
    const fileIds = filesToDownload.map((file) => file.file_id);
    downloadTasks.markFilesActive(fileIds, true);

    try {
      const response = await apiClient.downloadSelectedFiles(groupId, fileIds);
      const taskId = notifyTaskLaunch(response, (createdTaskId) => `当前页下载任务已创建: ${createdTaskId}`);
      setBatchDownloadTaskId(taskId);
      setBatchDownloadFileIds(fileIds);
    } catch (error) {
      handleTaskCreateError(error, '当前页下载任务创建失败');
      downloadTasks.markFilesActive(fileIds, false);
    }
  }, [downloadTasks, groupId, handleTaskCreateError, notifyTaskLaunch]);

  const handleDownloadFilteredResults = useCallback(async (filters: {
    searchQuery: string;
    statusFilter: string;
  }) => {
    if (batchDownloadTaskId) {
      return;
    }

    try {
      const response = await apiClient.downloadFilteredFiles(groupId, {
        status: filters.statusFilter === 'all' ? undefined : filters.statusFilter,
        search: filters.searchQuery || undefined,
      });
      const taskId = notifyTaskLaunch(response, (createdTaskId) => `筛选结果下载任务已创建: ${createdTaskId}`);
      setBatchDownloadTaskId(taskId);
      setBatchDownloadFileIds([]);
    } catch (error) {
      handleTaskCreateError(error, '筛选结果下载任务创建失败');
    }
  }, [batchDownloadTaskId, groupId, handleTaskCreateError, notifyTaskLaunch]);

  const handleBatchAnalyzeCurrentPage = useCallback(async (pendingAnalysisFiles: FileItem[]) => {
    if (pendingAnalysisFiles.length === 0 || batchAnalyzing) {
      return;
    }

    const fileIds = pendingAnalysisFiles.map((file) => file.file_id);
    setBatchAnalyzing(true);
    analysisFileTasks.markFilesActive(fileIds, true);

    try {
      const response = await apiClient.analyzeSelectedFiles(groupId, fileIds, false);
      const taskId = notifyTaskLaunch(response, (createdTaskId) => `当前页分析任务已创建: ${createdTaskId}`);
      setBatchAnalysisTaskId(taskId);
      setBatchAnalysisFileIds(fileIds);
    } catch (error) {
      handleTaskCreateError(error, '当前页分析任务创建失败');
      setBatchAnalyzing(false);
      analysisFileTasks.markFilesActive(fileIds, false);
    }
  }, [analysisFileTasks, batchAnalyzing, groupId, handleTaskCreateError, notifyTaskLaunch]);

  return {
    analysisTasks: analysisFileTasks.tasks,
    analyzingFileIds: analysisFileTasks.activeFileIds,
    batchAnalysisTaskId,
    batchAnalyzing,
    batchDownloadTaskId,
    downloadingFiles: downloadTasks.activeFileIds,
    fileTasks: downloadTasks.tasks,
    clearAnalysisTask: analysisFileTasks.clearTask,
    getAnalysisTask: analysisFileTasks.getTask,
    handleAnalysisTaskTerminal,
    handleBatchAnalysisTerminal,
    handleBatchAnalyzeCurrentPage,
    handleBatchDownloadCurrentPage,
    handleBatchDownloadTerminal,
    handleDownloadFile,
    handleDownloadFilteredResults,
    handleFileTaskTerminal,
    isAnalysisTaskActive: analysisFileTasks.isTaskActive,
    markFileAnalyzing: analysisFileTasks.markFileActive,
    trackAnalysisTask,
    updateAnalysisTaskStatus: analysisFileTasks.updateTask,
    updateFileTaskStatus: downloadTasks.updateTask,
  };
}
