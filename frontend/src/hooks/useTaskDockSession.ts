'use client';

import { useCallback, useState } from 'react';

export type TaskDockView = 'logs' | 'tasks';

export function useTaskDockSession() {
  const [currentTaskId, setCurrentTaskId] = useState<string | null>(null);
  const [taskDockVisible, setTaskDockVisible] = useState(false);
  const [taskLogExpanded, setTaskLogExpanded] = useState(false);
  const [taskDockView, setTaskDockView] = useState<TaskDockView>('logs');

  const openTaskDock = useCallback((view: TaskDockView) => {
    setTaskDockView(view);
    setTaskDockVisible(true);
    setTaskLogExpanded(true);
  }, []);

  const handleTaskCreated = useCallback((taskId: string) => {
    setCurrentTaskId(taskId);
    openTaskDock('logs');
  }, [openTaskDock]);

  const selectTaskLog = useCallback((taskId: string) => {
    setCurrentTaskId(taskId);
    openTaskDock('logs');
  }, [openTaskDock]);

  const collapseTaskLog = useCallback(() => {
    setTaskLogExpanded(false);
  }, []);

  const openTaskLog = useCallback(() => {
    openTaskDock('logs');
  }, [openTaskDock]);

  const openTaskList = useCallback(() => {
    openTaskDock('tasks');
  }, [openTaskDock]);

  const toggleTaskLog = useCallback(() => {
    setTaskDockVisible((visible) => {
      if (visible) {
        setTaskLogExpanded(false);
        return false;
      }
      setTaskDockView('logs');
      setTaskLogExpanded(true);
      return true;
    });
  }, []);

  const closeTaskDock = useCallback(() => {
    setTaskDockVisible(false);
    setTaskLogExpanded(false);
  }, []);

  return {
    currentTaskId,
    taskDockVisible,
    taskLogExpanded,
    taskDockView,
    handleTaskCreated,
    selectTaskLog,
    openTaskLog,
    openTaskList,
    toggleTaskLog,
    collapseTaskLog,
    closeTaskDock,
  };
}
