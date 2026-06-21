'use client';

import { useCallback, useState } from 'react';
import { toast } from 'sonner';

import { apiClient, FileAIAnalysis, FileItem } from '@/lib/api';
import type { FileTaskState } from '@/components/GroupFileTaskWatchers';
import { useTaskLauncher } from '@/hooks/useTaskLauncher';

interface UseGroupFileTasksOptions {
  groupId: number;
  onTaskConflict?: (taskId: string) => void;
  onTaskCreated?: (taskId: string) => void;
  selectedFile: FileItem | null;
  setAnalysis: (analysis: FileAIAnalysis | null) => void;
  setAnalysisLoading: (loading: boolean) => void;
}

type RefreshFiles = () => Promise<void>;

function isTaskActive(task?: FileTaskState) {
  return task?.status === 'pending' || task?.status === 'running';
}

export function useGroupFileTasks({
  groupId,
  onTaskConflict,
  onTaskCreated,
  selectedFile,
  setAnalysis,
  setAnalysisLoading,
}: UseGroupFileTasksOptions) {
  const [downloadingFiles, setDownloadingFiles] = useState<Set<number>>(new Set());
  const [fileTasks, setFileTasks] = useState<Map<number, FileTaskState>>(new Map());
  const [batchDownloadTaskId, setBatchDownloadTaskId] = useState<string | null>(null);
  const [batchDownloadFileIds, setBatchDownloadFileIds] = useState<number[]>([]);
  const [analyzingFileIds, setAnalyzingFileIds] = useState<Set<number>>(new Set());
  const [analysisTasks, setAnalysisTasks] = useState<Map<number, FileTaskState>>(new Map());
  const [batchAnalysisTaskId, setBatchAnalysisTaskId] = useState<string | null>(null);
  const [batchAnalysisFileIds, setBatchAnalysisFileIds] = useState<number[]>([]);
  const [batchAnalyzing, setBatchAnalyzing] = useState(false);
  const { handleTaskCreateError, notifyTaskCreated } = useTaskLauncher({
    onTaskConflict,
    onTaskCreated,
  });

  const markFileDownloading = useCallback((fileId: number, downloading: boolean) => {
    setDownloadingFiles(prev => {
      const next = new Set(prev);
      if (downloading) {
        next.add(fileId);
      } else {
        next.delete(fileId);
      }
      return next;
    });
  }, []);

  const markFileAnalyzing = useCallback((fileId: number, analyzing: boolean) => {
    setAnalyzingFileIds(prev => {
      const next = new Set(prev);
      if (analyzing) {
        next.add(fileId);
      } else {
        next.delete(fileId);
      }
      return next;
    });
  }, []);

  const updateFileTaskStatus = useCallback((
    fileId: number,
    taskId: string,
    status: FileTaskState['status'],
    message: string,
  ) => {
    setFileTasks(prev => {
      const next = new Map(prev);
      next.set(fileId, { taskId, status, message });
      return next;
    });
  }, []);

  const updateAnalysisTaskStatus = useCallback((
    fileId: number,
    taskId: string,
    status: FileTaskState['status'],
    message: string,
  ) => {
    setAnalysisTasks(prev => {
      const next = new Map(prev);
      next.set(fileId, { taskId, status, message });
      return next;
    });
  }, []);

  const trackAnalysisTask = useCallback((fileId: number, taskId: string, message = '分析任务已创建') => {
    updateAnalysisTaskStatus(fileId, taskId, 'pending', message);
  }, [updateAnalysisTaskStatus]);

  const getAnalysisTask = useCallback((fileId: number) => analysisTasks.get(fileId), [analysisTasks]);

  const clearAnalysisTask = useCallback((fileId: number) => {
    setAnalysisTasks(prev => {
      const next = new Map(prev);
      next.delete(fileId);
      return next;
    });
  }, []);

  const handleFileTaskTerminal = useCallback(async (
    fileId: number,
    taskId: string,
    status: FileTaskState['status'],
    message: string,
    refreshFiles: RefreshFiles,
  ) => {
    updateFileTaskStatus(fileId, taskId, status, message);
    markFileDownloading(fileId, false);
    await refreshFiles();
  }, [markFileDownloading, updateFileTaskStatus]);

  const handleBatchDownloadTerminal = useCallback(async (
    status: FileTaskState['status'],
    message: string,
    refreshFiles: RefreshFiles,
  ) => {
    const completedFileIds = batchDownloadFileIds.slice();
    setDownloadingFiles(prev => {
      const next = new Set(prev);
      completedFileIds.forEach((fileId) => next.delete(fileId));
      return next;
    });
    setBatchDownloadTaskId(null);
    setBatchDownloadFileIds([]);
    if (status === 'completed') {
      toast.success(message || '当前页文件下载任务完成');
    } else if (status === 'failed' || status === 'cancelled') {
      toast.error(message || '当前页文件下载任务未完成');
    }
    await refreshFiles();
  }, [batchDownloadFileIds]);

  const handleAnalysisTaskTerminal = useCallback(async (
    fileId: number,
    taskId: string,
    status: FileTaskState['status'],
    message: string,
    refreshFiles: RefreshFiles,
  ) => {
    updateAnalysisTaskStatus(fileId, taskId, status, message);
    markFileAnalyzing(fileId, false);

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
    } else if (status === 'failed' || status === 'cancelled') {
      toast.error(message || '文件分析未完成');
    }
    await refreshFiles();
  }, [
    groupId,
    markFileAnalyzing,
    selectedFile,
    setAnalysis,
    setAnalysisLoading,
    updateAnalysisTaskStatus,
  ]);

  const handleBatchAnalysisTerminal = useCallback(async (
    status: FileTaskState['status'],
    message: string,
    refreshFiles: RefreshFiles,
  ) => {
    const completedFileIds = batchAnalysisFileIds.slice();
    setAnalyzingFileIds(prev => {
      const next = new Set(prev);
      completedFileIds.forEach((fileId) => next.delete(fileId));
      return next;
    });
    setBatchAnalyzing(false);
    setBatchAnalysisTaskId(null);
    setBatchAnalysisFileIds([]);
    if (status === 'completed') {
      toast.success(message || '当前页文件分析完成');
    } else if (status === 'failed' || status === 'cancelled') {
      toast.error(message || '当前页文件分析未完成');
    }
    await refreshFiles();
  }, [batchAnalysisFileIds]);

  const handleDownloadFile = useCallback(async (file: FileItem, refreshFiles: RefreshFiles) => {
    if (downloadingFiles.has(file.file_id)) {
      return;
    }

    try {
      markFileDownloading(file.file_id, true);
      const response = await apiClient.downloadSingleFile(
        String(groupId),
        file.file_id,
        file.name,
        file.size,
      ) as { task_id?: string };

      if (response.task_id) {
        notifyTaskCreated(response.task_id, `文件下载任务已创建: ${response.task_id}`);
        updateFileTaskStatus(file.file_id, response.task_id, 'pending', '下载任务已创建');
      } else {
        toast.success('文件下载任务已创建');
        await refreshFiles();
        markFileDownloading(file.file_id, false);
      }
    } catch (error) {
      handleTaskCreateError(error, '文件下载失败');
      markFileDownloading(file.file_id, false);
    }
  }, [
    downloadingFiles,
    groupId,
    handleTaskCreateError,
    markFileDownloading,
    notifyTaskCreated,
    updateFileTaskStatus,
  ]);

  const handleBatchDownloadCurrentPage = useCallback(async (downloadableFiles: FileItem[]) => {
    if (downloadableFiles.length === 0) {
      return;
    }

    const filesToDownload = downloadableFiles.slice();
    const fileIds = filesToDownload.map((file) => file.file_id);
    setDownloadingFiles(prev => {
      const next = new Set(prev);
      fileIds.forEach((fileId) => next.add(fileId));
      return next;
    });

    try {
      const response = await apiClient.downloadSelectedFiles(groupId, fileIds);
      notifyTaskCreated(response.task_id, `当前页下载任务已创建: ${response.task_id}`);
      setBatchDownloadTaskId(response.task_id);
      setBatchDownloadFileIds(fileIds);
    } catch (error) {
      handleTaskCreateError(error, '当前页下载任务创建失败');
      setDownloadingFiles(prev => {
        const next = new Set(prev);
        fileIds.forEach((fileId) => next.delete(fileId));
        return next;
      });
    }
  }, [groupId, handleTaskCreateError, notifyTaskCreated]);

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
      notifyTaskCreated(response.task_id, `筛选结果下载任务已创建: ${response.task_id}`);
      setBatchDownloadTaskId(response.task_id);
      setBatchDownloadFileIds([]);
    } catch (error) {
      handleTaskCreateError(error, '筛选结果下载任务创建失败');
    }
  }, [batchDownloadTaskId, groupId, handleTaskCreateError, notifyTaskCreated]);

  const handleBatchAnalyzeCurrentPage = useCallback(async (pendingAnalysisFiles: FileItem[]) => {
    if (pendingAnalysisFiles.length === 0 || batchAnalyzing) {
      return;
    }

    const fileIds = pendingAnalysisFiles.map((file) => file.file_id);
    setBatchAnalyzing(true);
    setAnalyzingFileIds(prev => {
      const next = new Set(prev);
      fileIds.forEach((fileId) => next.add(fileId));
      return next;
    });

    try {
      const response = await apiClient.analyzeSelectedFiles(groupId, fileIds, false);
      notifyTaskCreated(response.task_id, `当前页分析任务已创建: ${response.task_id}`);
      setBatchAnalysisTaskId(response.task_id);
      setBatchAnalysisFileIds(fileIds);
    } catch (error) {
      handleTaskCreateError(error, '当前页分析任务创建失败');
      setBatchAnalyzing(false);
      setAnalyzingFileIds(prev => {
        const next = new Set(prev);
        fileIds.forEach((fileId) => next.delete(fileId));
        return next;
      });
    }
  }, [batchAnalyzing, groupId, handleTaskCreateError, notifyTaskCreated]);

  return {
    analysisTasks,
    analyzingFileIds,
    batchAnalysisTaskId,
    batchAnalyzing,
    batchDownloadTaskId,
    downloadingFiles,
    fileTasks,
    clearAnalysisTask,
    getAnalysisTask,
    handleAnalysisTaskTerminal,
    handleBatchAnalysisTerminal,
    handleBatchAnalyzeCurrentPage,
    handleBatchDownloadCurrentPage,
    handleBatchDownloadTerminal,
    handleDownloadFile,
    handleDownloadFilteredResults,
    handleFileTaskTerminal,
    isAnalysisTaskActive: isTaskActive,
    markFileAnalyzing,
    trackAnalysisTask,
    updateAnalysisTaskStatus,
    updateFileTaskStatus,
  };
}
