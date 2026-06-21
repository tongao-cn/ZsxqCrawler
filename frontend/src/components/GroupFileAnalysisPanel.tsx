'use client';

import { useState } from 'react';
import { apiClient, FileAIAnalysis, FileItem } from '@/lib/api';
import { toast } from 'sonner';
import {
  GroupFileHeader,
  GroupFilePagination,
  GroupFileSummary,
  GroupFileToolbar,
} from '@/components/GroupFileAnalysisPanelParts';
import { FileAnalysisDialog } from '@/components/FileAnalysisDialog';
import { GroupFileTable } from '@/components/GroupFileTable';
import { GroupFileTaskWatchers } from '@/components/GroupFileTaskWatchers';
import { useGroupFileList } from '@/hooks/useGroupFileList';
import { useGroupFileTasks } from '@/hooks/useGroupFileTasks';
import { useTaskLauncher } from '@/hooks/useTaskLauncher';

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
  const { handleTaskCreateError, notifyTaskCreated } = useTaskLauncher({
    onTaskConflict,
    onTaskCreated,
  });
  const taskState = useGroupFileTasks({
    groupId,
    onTaskConflict,
    onTaskCreated,
    selectedFile,
    setAnalysis,
    setAnalysisLoading,
  });
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
    downloadingFiles: taskState.downloadingFiles,
    groupId,
  });

  const openAnalysisDialog = async (file: FileItem, force: boolean = false) => {
    try {
      setSelectedFile(file);
      setAnalysisOpen(true);

      const activeTask = taskState.getAnalysisTask(file.file_id);
      if (activeTask && taskState.isAnalysisTaskActive(activeTask)) {
        try {
          const latestTask = await apiClient.getTask(activeTask.taskId);
          if (taskState.isAnalysisTaskActive({
            taskId: activeTask.taskId,
            status: latestTask.status,
            message: latestTask.message,
          })) {
            toast.info(`文件分析任务仍在运行: ${activeTask.taskId}`);
            setAnalysisLoading(true);
            taskState.markFileAnalyzing(file.file_id, true);
            return;
          }
          taskState.clearAnalysisTask(file.file_id);
          taskState.markFileAnalyzing(file.file_id, false);
        } catch {
          taskState.clearAnalysisTask(file.file_id);
          taskState.markFileAnalyzing(file.file_id, false);
        }
      }

      setAnalysis(null);
      setAnalysisLoading(true);

      if (!force && file.has_ai_analysis) {
        const cached = await apiClient.getFileAIAnalysis(groupId, file.file_id);
        if (cached.analysis) {
          setAnalysis(cached.analysis);
          setAnalysisLoading(false);
          taskState.markFileAnalyzing(file.file_id, false);
          return;
        }
      }

      taskState.markFileAnalyzing(file.file_id, true);
      const response = await apiClient.analyzeFileTask(groupId, file.file_id, force);
      taskState.trackAnalysisTask(file.file_id, response.task_id);
      notifyTaskCreated(response.task_id, `文件分析任务已创建: ${response.task_id}`);
    } catch (error) {
      handleTaskCreateError(error, '文件 AI 分析失败');
      setAnalysis({
        file_id: file.file_id,
        status: 'failed',
        error_message: error instanceof Error ? error.message : '未知错误',
      });
      setAnalysisLoading(false);
      taskState.markFileAnalyzing(file.file_id, false);
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col space-y-4">
      <GroupFileTaskWatchers
        fileTasks={taskState.fileTasks}
        batchDownloadTaskId={taskState.batchDownloadTaskId}
        analysisTasks={taskState.analysisTasks}
        batchAnalysisTaskId={taskState.batchAnalysisTaskId}
        onFileTaskStatus={taskState.updateFileTaskStatus}
        onFileTaskTerminal={(fileId, taskId, status, message) => taskState.handleFileTaskTerminal(
          fileId,
          taskId,
          status,
          message,
          () => loadFiles(page),
        )}
        onBatchDownloadTerminal={(status, message) => taskState.handleBatchDownloadTerminal(
          status,
          message,
          () => loadFiles(page),
        )}
        onAnalysisTaskStatus={taskState.updateAnalysisTaskStatus}
        onAnalysisTaskTerminal={(fileId, taskId, status, message) => taskState.handleAnalysisTaskTerminal(
          fileId,
          taskId,
          status,
          message,
          () => loadFiles(page),
        )}
        onBatchAnalysisTerminal={(status, message) => taskState.handleBatchAnalysisTerminal(
          status,
          message,
          () => loadFiles(page),
        )}
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
        batchAnalyzing={taskState.batchAnalyzing}
        downloadableCount={downloadableFiles.length}
        batchDownloadActive={Boolean(taskState.batchDownloadTaskId)}
        onDownloadCurrentPage={() => void taskState.handleBatchDownloadCurrentPage(downloadableFiles)}
        onDownloadFilteredResults={() => void taskState.handleDownloadFilteredResults({
          searchQuery,
          statusFilter,
        })}
        pendingAnalysisCount={pendingAnalysisFiles.length}
        onAnalyzeCurrentPage={() => void taskState.handleBatchAnalyzeCurrentPage(pendingAnalysisFiles)}
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
        downloadingFiles={taskState.downloadingFiles}
        analyzingFileIds={taskState.analyzingFileIds}
        fileTasks={taskState.fileTasks}
        onOpenAnalysis={(file, force) => void openAnalysisDialog(file, force)}
        onDownloadFile={(file) => void taskState.handleDownloadFile(file, () => loadFiles(page))}
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
