'use client';

import { useCallback, useState } from 'react';

export function useGroupTaskBridge() {
  const [currentTaskId, setCurrentTaskId] = useState<string | null>(null);
  const [taskDockVisible, setTaskDockVisible] = useState(false);
  const [taskLogExpanded, setTaskLogExpanded] = useState(false);
  const [taskDockView, setTaskDockView] = useState<'logs' | 'tasks'>('logs');
  const [activeTab, setActiveTab] = useState('topics');

  const handleTaskCreated = useCallback((taskId: string) => {
    setCurrentTaskId(taskId);
    setTaskDockView('logs');
    setTaskDockVisible(true);
    setTaskLogExpanded(true);
  }, []);

  const selectTaskLog = useCallback((taskId: string) => {
    setCurrentTaskId(taskId);
    setTaskDockView('logs');
    setTaskDockVisible(true);
    setTaskLogExpanded(true);
  }, []);

  const collapseTaskLog = useCallback(() => {
    setTaskLogExpanded(false);
  }, []);

  const openTaskLog = useCallback(() => {
    setTaskDockView('logs');
    setTaskDockVisible(true);
    setTaskLogExpanded(true);
  }, []);

  const openTaskList = useCallback(() => {
    setTaskDockView('tasks');
    setTaskDockVisible(true);
    setTaskLogExpanded(true);
  }, []);

  const toggleTaskLog = useCallback(() => {
    setTaskDockVisible((visible) => {
      if (visible) {
        setTaskLogExpanded(false);
        return false;
      }
      setTaskLogExpanded(true);
      return true;
    });
  }, []);

  const closeTaskDock = useCallback(() => {
    setTaskDockVisible(false);
    setTaskLogExpanded(false);
  }, []);

  return {
    activeTab,
    setActiveTab,
    currentTaskId,
    taskDockVisible,
    taskLogExpanded,
    taskDockView,
    setTaskDockView,
    handleTaskCreated,
    selectTaskLog,
    openTaskLog,
    openTaskList,
    toggleTaskLog,
    collapseTaskLog,
    closeTaskDock,
  };
}
