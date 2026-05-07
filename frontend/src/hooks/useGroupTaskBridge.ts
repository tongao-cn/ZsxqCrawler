'use client';

import { useCallback, useState } from 'react';

export function useGroupTaskBridge() {
  const [currentTaskId, setCurrentTaskId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState('topics');

  const handleTaskCreated = useCallback((taskId: string) => {
    setCurrentTaskId(taskId);
    setActiveTab('logs');
  }, []);

  const closeTaskLog = useCallback(() => {
    setCurrentTaskId(null);
  }, []);

  return {
    activeTab,
    setActiveTab,
    currentTaskId,
    handleTaskCreated,
    closeTaskLog,
  };
}
