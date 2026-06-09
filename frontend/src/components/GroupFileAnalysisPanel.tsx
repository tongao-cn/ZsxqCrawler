'use client';

import { useCallback, useState } from 'react';
import { apiClient, FileAIAnalysis, FileItem, getTaskConflictDetail } from '@/lib/api';
import { toast } from 'sonner';
import {
  FileAnalysisDialog,
  GroupFileHeader,
  GroupFilePagination,
  GroupFileSummary,
  GroupFileTable,
  GroupFileToolbar,
} from '@/components/GroupFileAnalysisPanelParts';
import { GroupFileTaskWatchers, type FileTaskState } from '@/components/GroupFileTaskWatchers';
import { useGroupFileList } from '@/hooks/useGroupFileList';

interface GroupFileAnalysisPanelProps {
  groupId: number;
  onTaskCreated?: (taskId: string) => void;
  onTaskConflict?: (taskId: string) => void;
}

export default function GroupFileAnalysisPanel({
  groupId,
  onTaskCreated,
  onTaskConflict,
}: GroupFileAnalysisPanelProps) {
  const [analysisOpen, setAnalysisOpen] = useState(false);
  const [selectedFile, setSelectedFile] = useState<FileItem | null>(null);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [analysis, setAnalysis] = useState<FileAIAnalysis | null>(null);
  const [downloadingFiles, setDownloadingFiles] = useState<Set<number>>(new Set());
  const [fileTasks, setFileTasks] = useState<Map<number, FileTaskState>>(new Map());
  const [batchDownloadTaskId, setBatchDownloadTaskId] = useState<string | null>(null);
  const [batchDownloadFileIds, setBatchDownloadFileIds] = useState<number[]>([]);
  const [analyzingFileIds, setAnalyzingFileIds] = useState<Set<number>>(new Set());
  const [analysisTasks, setAnalysisTasks] = useState<Map<number, FileTaskState>>(new Map());
  const [batchAnalysisTaskId, setBatchAnalysisTaskId] = useState<string | null>(null);
  const [batchAnalysisFileIds, setBatchAnalysisFileIds] = useState<number[]>([]);
  const [batchAnalyzing, setBatchAnalyzing] = useState(false);
  const {
    analysisStatusFilter,
    analysisStatusLabel,
    clearFilters,
    downloadableFiles,
    downloadedFiles,
    downloadStatusLabel,
    failedFiles,
    files,
    handleAnalysisStatusFilterChange,
    handleSearch,
    handleStatusFilterChange,
    hasActiveFilters,
    loadFiles,
    loading,
    page,
    pendingAnalysisFiles,
    searchInput,
    searchQuery,
    setSearchInput,
    showPendingAnalysis,
    statusFilter,
    totalFiles,
    totalPages,
  } = useGroupFileList({
    downloadingFiles,
    groupId,
  });

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

  const handleFileTaskTerminal = useCallback(async (
    fileId: number,
    taskId: string,
    status: FileTaskState['status'],
    message: string,
  ) => {
    updateFileTaskStatus(fileId, taskId, status, message);
    setDownloadingFiles(prev => {
      const next = new Set(prev);
      next.delete(fileId);
      return next;
    });
    await loadFiles(page);
  }, [loadFiles, page, updateFileTaskStatus]);

  const handleBatchDownloadTerminal = useCallback(async (
    status: FileTaskState['status'],
    message: string,
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
    await loadFiles(page);
  }, [batchDownloadFileIds, loadFiles, page]);

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

  const handleAnalysisTaskTerminal = useCallback(async (
    fileId: number,
    taskId: string,
    status: FileTaskState['status'],
    message: string,
  ) => {
    updateAnalysisTaskStatus(fileId, taskId, status, message);
    setAnalyzingFileIds(prev => {
      const next = new Set(prev);
      next.delete(fileId);
      return next;
    });

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
    await loadFiles(page);
  }, [groupId, loadFiles, page, selectedFile, updateAnalysisTaskStatus]);

  const handleBatchAnalysisTerminal = useCallback(async (
    status: FileTaskState['status'],
    message: string,
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
    await loadFiles(page);
  }, [batchAnalysisFileIds, loadFiles, page]);

  const handleDownloadFile = async (file: FileItem) => {
    if (downloadingFiles.has(file.file_id)) {
      return;
    }

    try {
      setDownloadingFiles(prev => new Set(prev).add(file.file_id));
      const response = await apiClient.downloadSingleFile(
        String(groupId),
        file.file_id,
        file.name,
        file.size,
      ) as { task_id?: string };
      toast.success(response.task_id ? `文件下载任务已创建: ${response.task_id}` : '文件下载任务已创建');

      if (response.task_id) {
        onTaskCreated?.(response.task_id);
        setFileTasks(prev => {
          const next = new Map(prev);
          next.set(file.file_id, {
            taskId: response.task_id || '',
            status: 'pending',
            message: '下载任务已创建',
          });
          return next;
        });
        updateFileTaskStatus(file.file_id, response.task_id, 'pending', '下载任务已创建');
      } else {
        await loadFiles(page);
        setDownloadingFiles(prev => {
          const next = new Set(prev);
          next.delete(file.file_id);
          return next;
        });
      }
    } catch (error) {
      const conflict = getTaskConflictDetail(error);
      if (conflict?.task_id) {
        toast.error(`已有任务 ${conflict.task_id} 正在运行`);
        onTaskConflict?.(conflict.task_id);
      } else {
        toast.error(`文件下载失败: ${error instanceof Error ? error.message : '未知错误'}`);
      }
      setDownloadingFiles(prev => {
        const next = new Set(prev);
        next.delete(file.file_id);
        return next;
      });
    }
  };

  const handleBatchDownloadCurrentPage = async () => {
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
      onTaskCreated?.(response.task_id);
      setBatchDownloadTaskId(response.task_id);
      setBatchDownloadFileIds(fileIds);
      toast.success(`当前页下载任务已创建: ${response.task_id}`);
    } catch (error) {
      const conflict = getTaskConflictDetail(error);
      if (conflict?.task_id) {
        toast.error(`已有任务 ${conflict.task_id} 正在运行`);
        onTaskConflict?.(conflict.task_id);
      } else {
        toast.error(`当前页下载任务创建失败: ${error instanceof Error ? error.message : '未知错误'}`);
      }
      setDownloadingFiles(prev => {
        const next = new Set(prev);
        fileIds.forEach((fileId) => next.delete(fileId));
        return next;
      });
    }
  };

  const handleDownloadFilteredResults = async () => {
    if (batchDownloadTaskId) {
      return;
    }

    try {
      const response = await apiClient.downloadFilteredFiles(groupId, {
        status: statusFilter === 'all' ? undefined : statusFilter,
        search: searchQuery || undefined,
      });
      onTaskCreated?.(response.task_id);
      setBatchDownloadTaskId(response.task_id);
      setBatchDownloadFileIds([]);
      toast.success(`筛选结果下载任务已创建: ${response.task_id}`);
    } catch (error) {
      const conflict = getTaskConflictDetail(error);
      if (conflict?.task_id) {
        toast.error(`已有任务 ${conflict.task_id} 正在运行`);
        onTaskConflict?.(conflict.task_id);
      } else {
        toast.error(`筛选结果下载任务创建失败: ${error instanceof Error ? error.message : '未知错误'}`);
      }
    }
  };

  const handleBatchAnalyzeCurrentPage = async () => {
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
      onTaskCreated?.(response.task_id);
      setBatchAnalysisTaskId(response.task_id);
      setBatchAnalysisFileIds(fileIds);
      toast.success(`当前页分析任务已创建: ${response.task_id}`);
    } catch (error) {
      toast.error(`当前页分析任务创建失败: ${error instanceof Error ? error.message : '未知错误'}`);
      setBatchAnalyzing(false);
      setAnalyzingFileIds(prev => {
        const next = new Set(prev);
        fileIds.forEach((fileId) => next.delete(fileId));
        return next;
      });
    }
  };

  const openAnalysisDialog = async (file: FileItem, force: boolean = false) => {
    try {
      setSelectedFile(file);
      setAnalysis(null);
      setAnalysisOpen(true);
      setAnalysisLoading(true);
      setAnalyzingFileIds(prev => new Set(prev).add(file.file_id));

      if (!force && file.has_ai_analysis) {
        const cached = await apiClient.getFileAIAnalysis(groupId, file.file_id);
        if (cached.analysis) {
          setAnalysis(cached.analysis);
          setAnalysisLoading(false);
          setAnalyzingFileIds(prev => {
            const next = new Set(prev);
            next.delete(file.file_id);
            return next;
          });
          return;
        }
      }

      const activeTask = analysisTasks.get(file.file_id);
      if (activeTask && (activeTask.status === 'pending' || activeTask.status === 'running')) {
        return;
      }

      const response = await apiClient.analyzeFileTask(groupId, file.file_id, force);
      onTaskCreated?.(response.task_id);
      updateAnalysisTaskStatus(file.file_id, response.task_id, 'pending', '分析任务已创建');
      toast.success(`文件分析任务已创建: ${response.task_id}`);
    } catch (error) {
      toast.error(`文件 AI 分析失败: ${error instanceof Error ? error.message : '未知错误'}`);
      setAnalysis({
        file_id: file.file_id,
        status: 'failed',
        error_message: error instanceof Error ? error.message : '未知错误',
      });
      setAnalysisLoading(false);
      setAnalyzingFileIds(prev => {
        const next = new Set(prev);
        next.delete(file.file_id);
        return next;
      });
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col space-y-4">
      <GroupFileTaskWatchers
        fileTasks={fileTasks}
        batchDownloadTaskId={batchDownloadTaskId}
        analysisTasks={analysisTasks}
        batchAnalysisTaskId={batchAnalysisTaskId}
        onFileTaskStatus={updateFileTaskStatus}
        onFileTaskTerminal={handleFileTaskTerminal}
        onBatchDownloadTerminal={handleBatchDownloadTerminal}
        onAnalysisTaskStatus={updateAnalysisTaskStatus}
        onAnalysisTaskTerminal={handleAnalysisTaskTerminal}
        onBatchAnalysisTerminal={handleBatchAnalysisTerminal}
      />

      <GroupFileHeader
        downloadStatusLabel={downloadStatusLabel}
        analysisStatusLabel={analysisStatusLabel}
        searchQuery={searchQuery}
        page={page}
      />

      <GroupFileSummary
        filesCount={files.length}
        totalFiles={totalFiles}
        downloadedCount={downloadedFiles.length}
        failedCount={failedFiles.length}
        pendingAnalysisCount={pendingAnalysisFiles.length}
      />

      <GroupFileToolbar
        searchInput={searchInput}
        setSearchInput={setSearchInput}
        onSearch={handleSearch}
        loading={loading}
        statusFilter={statusFilter}
        onStatusFilterChange={handleStatusFilterChange}
        analysisStatusFilter={analysisStatusFilter}
        onAnalysisStatusFilterChange={handleAnalysisStatusFilterChange}
        onRefresh={() => void loadFiles(page)}
        batchAnalyzing={batchAnalyzing}
        downloadableCount={downloadableFiles.length}
        batchDownloadActive={Boolean(batchDownloadTaskId)}
        onDownloadCurrentPage={() => void handleBatchDownloadCurrentPage()}
        onDownloadFilteredResults={() => void handleDownloadFilteredResults()}
        pendingAnalysisCount={pendingAnalysisFiles.length}
        onAnalyzeCurrentPage={() => void handleBatchAnalyzeCurrentPage()}
        onShowPending={showPendingAnalysis}
        showPendingDisabled={analysisStatusFilter === 'pending' && statusFilter === 'all'}
        hasActiveFilters={hasActiveFilters}
        onClearFilters={clearFilters}
      />

      <div className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-xs text-muted-foreground">
        操作语义统一：未下载 → 下载；失败 → 重试；已下载未分析 → AI 分析；已分析 → 查看分析。
      </div>

      <GroupFileTable
        files={files}
        loading={loading}
        hasActiveFilters={hasActiveFilters}
        downloadingFiles={downloadingFiles}
        analyzingFileIds={analyzingFileIds}
        fileTasks={fileTasks}
        onOpenAnalysis={(file, force) => void openAnalysisDialog(file, force)}
        onDownloadFile={(file) => void handleDownloadFile(file)}
      />

      <GroupFilePagination
        page={page}
        totalPages={totalPages}
        loading={loading}
        onLoadPage={(targetPage) => void loadFiles(targetPage)}
      />

      <FileAnalysisDialog
        open={analysisOpen}
        onOpenChange={setAnalysisOpen}
        selectedFile={selectedFile}
        analysis={analysis}
        analysisLoading={analysisLoading}
        onReanalyze={(file) => void openAnalysisDialog(file, true)}
      />
    </div>
  );
}
