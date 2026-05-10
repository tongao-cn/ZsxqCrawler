'use client';

import { useCallback, useState } from 'react';
import { toast } from 'sonner';

import { apiClient, FileStatus, getTaskConflictDetail } from '@/lib/api';
import { useSyncedRef } from '@/hooks/useSyncedRef';

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
  const downloadingFilesRef = useSyncedRef(downloadingFiles);

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
      const response = await apiClient.downloadSingleFile(String(groupId), fileId, fileName, fileSize) as any;
      toast.success(`文件下载任务已创建: ${response.task_id}`);
      onTaskCreated(response.task_id);

      const checkStatus = async () => {
        const status = await getFileStatus(fileId, fileName, fileSize);
        if (status && status.is_complete) {
          toast.success(`文件下载完成: ${fileName}`);
          setFileStatuses((prev) => new Map(prev).set(fileId, status));
          return true;
        }
        return false;
      };

      let attempts = 0;
      const statusInterval = window.setInterval(async () => {
        attempts++;
        const completed = await checkStatus();
        if (completed || attempts >= 12) {
          window.clearInterval(statusInterval);
        }
      }, 5000);
    } catch (error) {
      const conflict = getTaskConflictDetail(error);
      if (conflict?.task_id) {
        toast.error(`已有任务 ${conflict.task_id} 正在运行`);
        onTaskConflict?.(conflict.task_id);
      } else {
        toast.error(`文件下载失败: ${error instanceof Error ? error.message : '未知错误'}`);
      }
    } finally {
      const next = new Set(downloadingFilesRef.current);
      next.delete(fileId);
      downloadingFilesRef.current = next;
      setDownloadingFiles(next);
    }
  }, [downloadingFilesRef, getFileStatus, groupId, onTaskConflict, onTaskCreated]);

  return {
    fileStatuses,
    downloadingFiles,
    getFileStatus,
    downloadSingleFile,
  };
}
