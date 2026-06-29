'use client';

import { useCallback, useState } from 'react';

import { isActiveTaskStatus, type TaskStatus } from '@/lib/taskStatus';

export interface FileTaskState {
  taskId: string;
  status: TaskStatus;
  message: string;
}

export function useFileTaskTracker() {
  const [activeFileIds, setActiveFileIds] = useState<Set<number>>(new Set());
  const [tasks, setTasks] = useState<Map<number, FileTaskState>>(new Map());

  const markFileActive = useCallback((fileId: number, active: boolean) => {
    setActiveFileIds((previousIds) => {
      const nextIds = new Set(previousIds);
      if (active) {
        nextIds.add(fileId);
      } else {
        nextIds.delete(fileId);
      }
      return nextIds;
    });
  }, []);

  const markFilesActive = useCallback((fileIds: number[], active: boolean) => {
    setActiveFileIds((previousIds) => {
      const nextIds = new Set(previousIds);
      fileIds.forEach((fileId) => {
        if (active) {
          nextIds.add(fileId);
        } else {
          nextIds.delete(fileId);
        }
      });
      return nextIds;
    });
  }, []);

  const updateTask = useCallback((
    fileId: number,
    taskId: string,
    status: FileTaskState['status'],
    message: string,
  ) => {
    setTasks((previousTasks) => {
      const nextTasks = new Map(previousTasks);
      nextTasks.set(fileId, { taskId, status, message });
      return nextTasks;
    });
  }, []);

  const trackTask = useCallback((fileId: number, taskId: string, message = '任务已创建') => {
    updateTask(fileId, taskId, 'pending', message);
  }, [updateTask]);

  const getTask = useCallback((fileId: number) => tasks.get(fileId), [tasks]);

  const clearTask = useCallback((fileId: number) => {
    setTasks((previousTasks) => {
      const nextTasks = new Map(previousTasks);
      nextTasks.delete(fileId);
      return nextTasks;
    });
  }, []);

  const isTaskActive = useCallback((task?: FileTaskState) => isActiveTaskStatus(task?.status), []);

  return {
    activeFileIds,
    tasks,
    clearTask,
    getTask,
    isTaskActive,
    markFileActive,
    markFilesActive,
    trackTask,
    updateTask,
  };
}
