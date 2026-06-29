'use client';

import { useState } from 'react';

import { useTaskDockSession } from '@/hooks/useTaskDockSession';

export function useGroupTaskBridge() {
  const [activeTab, setActiveTab] = useState('topics');
  const taskDockSession = useTaskDockSession();

  return {
    activeTab,
    setActiveTab,
    ...taskDockSession,
  };
}
