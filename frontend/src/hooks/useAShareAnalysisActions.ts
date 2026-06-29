'use client';

import { useState } from 'react';
import { toast } from 'sonner';

import { apiClient, AShareAnalysisStatus, Group } from '@/lib/api';
import { useTaskLauncher } from '@/hooks/useTaskLauncher';
import {
  planAShareAnalysisReset,
  planAShareAnalysisRun,
  planAShareTdxExport,
  summarizeAShareTdxExport,
} from '@/lib/a-share-workbench-model';

interface UseAShareAnalysisActionsOptions {
  concurrency: number;
  loadStatus: (bootstrap?: boolean, groupId?: number) => Promise<AShareAnalysisStatus | null>;
  onTaskCreated?: (taskId: string) => void;
  refreshAll: (bootstrap?: boolean, groupId?: number) => Promise<void>;
  resetEndDate: string;
  resetStartDate: string;
  runDays: number;
  runEndDate: string;
  runStartDate: string;
  selectedEndDate: string;
  selectedGroup?: Group | null;
  selectedStartDate: string;
  setActiveRunTaskId: (taskId: string | null) => void;
}

export function useAShareAnalysisActions({
  concurrency,
  loadStatus,
  onTaskCreated,
  refreshAll,
  resetEndDate,
  resetStartDate,
  runDays,
  runEndDate,
  runStartDate,
  selectedEndDate,
  selectedGroup,
  selectedStartDate,
  setActiveRunTaskId,
}: UseAShareAnalysisActionsOptions) {
  const [running, setRunning] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [exportingTdx, setExportingTdx] = useState(false);
  const { handleTaskCreateError, notifyTaskLaunch } = useTaskLauncher({
    onTaskCreated,
  });

  const handleRunAnalysis = async () => {
    const runPlan = planAShareAnalysisRun({
      concurrency,
      groupId: selectedGroup?.group_id,
      resetEndDate,
      resetStartDate,
      runDays,
      runEndDate,
      runStartDate,
    });
    if (!runPlan.ok) {
      toast.error(runPlan.message);
      return;
    }

    try {
      setRunning(true);
      const response = await apiClient.runAShareAnalysis(runPlan.payload);
      const taskId = notifyTaskLaunch(response, '股票推荐池任务已创建，结果会在完成后自动刷新');
      setActiveRunTaskId(taskId);
      await loadStatus(false, selectedGroup?.group_id);
    } catch (error) {
      handleTaskCreateError(error, '创建股票推荐池任务失败');
    } finally {
      setRunning(false);
    }
  };

  const handleResetOnly = async () => {
    const resetPlan = planAShareAnalysisReset({
      groupId: selectedGroup?.group_id,
      resetEndDate,
      resetStartDate,
    });
    if (!resetPlan.ok) {
      toast.error(resetPlan.message);
      return;
    }

    try {
      setResetting(true);
      await apiClient.resetAShareAnalysisRange(resetPlan.payload);
      toast.success('指定日期区间的数据已删除');
      await refreshAll(false, selectedGroup?.group_id);
    } catch (error) {
      toast.error(`删除日期区间失败: ${error instanceof Error ? error.message : '未知错误'}`);
    } finally {
      setResetting(false);
    }
  };

  const handleExportToTdx = async () => {
    const exportPlan = planAShareTdxExport({
      groupId: selectedGroup?.group_id,
      groupName: selectedGroup?.name,
      selectedEndDate,
      selectedStartDate,
    });
    if (!exportPlan.ok) {
      toast.error(exportPlan.message);
      return;
    }
    try {
      setExportingTdx(true);
      const result = await apiClient.exportAShareRankingsToTdx(exportPlan.payload);
      toast.success(summarizeAShareTdxExport(result));
      await loadStatus(false, selectedGroup?.group_id);
    } catch (error) {
      toast.error(`导入通达信失败: ${error instanceof Error ? error.message : '未知错误'}`);
    } finally {
      setExportingTdx(false);
    }
  };

  return {
    exportingTdx,
    handleExportToTdx,
    handleResetOnly,
    handleRunAnalysis,
    resetting,
    running,
  };
}
