'use client';

import { useCallback, useState } from 'react';
import { toast } from 'sonner';

import { apiClient, FileStatus } from '@/lib/api';
import { useSyncedRef } from '@/hooks/useSyncedRef';
import { useTaskLauncher } from '@/hooks/useTaskLauncher';
import { useTaskStatus } from '@/hooks/useTaskStatus';

interface UseTopicFileActionsOptions {
  groupId: number;
  onTaskCreated: (taskId: string) => void;
  onTaskConflict?: (taskId: string) => void;
}

export function useTopicFileActions({
  groupId,
  onTaskCreated,
  onTaskConflict,
}: UseTopicFileActionsOptions) {
  const [fileStatuses, setFileStatuses] = useState<Map<number, FileStatus>>(new Map());
  const [downloadingFiles, setDownloadingFiles] = useState<Set<number>>(new Set());
  const [activeDownload, setActiveDownload] = useState<{
    fileId: number;
    fileName: string;
    fileSize?: number;
    taskId: string;
  } | null>(null);
  const downloadingFilesRef = useSyncedRef(downloadingFiles);
  const { handleTaskCreateError, notifyTaskLaunch } = useTaskLauncher({
    onTaskConflict,
    onTaskCreated,
  });

  useTaskStatus(activeDownload?.taskId, {
    enabled: Boolean(activeDownload),
    onTerminal: async (task) => {
      if (!activeDownload) {
        return;
      }
      const status = await getFileStatus(activeDownload.fileId, activeDownload.fileName, activeDownload.fileSize);
      if (task.status === 'completed' && status?.is_complete) {
        toast.success(`文件下载完成: ${activeDownload.fileName}`);
      } else if (task.status === 'failed' || task.status === 'cancelled') {
        toast.error(task.message || `文件下载未完成: ${activeDownload.fileName}`);
      }
      const next = new Set(downloadingFilesRef.current);
      next.delete(activeDownload.fileId);
      downloadingFilesRef.current = next;
      setDownloadingFiles(next);
      setActiveDownload(null);
    },
  });

  const getFileStatus = useCallback(async (fileId: number, fileName?: string, fileSize?: number) => {
    try {
      const status = await apiClient.getFileStatus(String(groupId), fileId) as FileStatus;
      setFileStatuses((prev) => new Map(prev).set(fileId, status));
      return status;
    } catch (error) {
      console.error('从数据库获取文件状态失败:', error);

      if (fileName && fileSize !== undefined) {
        try {
          const localStatus = await apiClient.checkLocalFileStatus(String(groupId), fileName, fileSize) as any;
          const status: FileStatus = {
            file_id: fileId,
            name: fileName,
            size: fileSize,
            download_status: localStatus.is_complete ? 'downloaded' : 'not_collected',
            local_exists: localStatus.local_exists,
            local_size: localStatus.local_size,
            local_path: localStatus.local_path,
            is_complete: localStatus.is_complete,
          };
          setFileStatuses((prev) => new Map(prev).set(fileId, status));
          return status;
        } catch (localError) {
          console.error('检查本地文件失败:', localError);
        }
      }

      const defaultStatus: FileStatus = {
        file_id: fileId,
        name: fileName || '',
        size: fileSize || 0,
        download_status: 'not_collected',
        local_exists: false,
        local_size: 0,
        is_complete: false,
      };
      setFileStatuses((prev) => new Map(prev).set(fileId, defaultStatus));
      return defaultStatus;
    }
  }, [groupId]);

  const downloadSingleFile = useCallback(async (fileId: number, fileName: string, fileSize?: number) => {
    if (downloadingFilesRef.current.has(fileId)) {
      return;
    }

    downloadingFilesRef.current = new Set(downloadingFilesRef.current).add(fileId);
    setDownloadingFiles(new Set(downloadingFilesRef.current));

    try {
      const response = await apiClient.downloadSingleFile(String(groupId), fileId, fileName, fileSize);
      const taskId = notifyTaskLaunch(response, (createdTaskId) => `文件下载任务已创建: ${createdTaskId}`);
      setActiveDownload({ fileId, fileName, fileSize, taskId });
    } catch (error) {
      handleTaskCreateError(error, '文件下载失败');
      const next = new Set(downloadingFilesRef.current);
      next.delete(fileId);
      downloadingFilesRef.current = next;
      setDownloadingFiles(next);
    }
  }, [downloadingFilesRef, groupId, handleTaskCreateError, notifyTaskLaunch]);

  return {
    fileStatuses,
    downloadingFiles,
    getFileStatus,
    downloadSingleFile,
  };
}
