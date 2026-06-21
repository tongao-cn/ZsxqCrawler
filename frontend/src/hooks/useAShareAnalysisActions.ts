'use client';

import { useState } from 'react';
import { toast } from 'sonner';

import { apiClient, AShareAnalysisExportTdxResponse, AShareAnalysisStatus, Group } from '@/lib/api';
import { useTaskLauncher } from '@/hooks/useTaskLauncher';

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

function summarizeTdxExport(result: AShareAnalysisExportTdxResponse) {
  const blockText = result.blocks
    .map((block) => `${block.window_days}日 ${block.written_count}只`)
    .join('，');

  if (result.unresolved_companies.length > 0) {
    toast.success(`已导入通达信：${blockText}；未匹配 ${result.unresolved_companies.length} 个公司`);
    return;
  }

  toast.success(`已导入通达信：${blockText}`);
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
  const { handleTaskCreateError, notifyTaskCreated } = useTaskLauncher({
    onTaskCreated,
  });

  const handleRunAnalysis = async () => {
    if (!selectedGroup) {
      toast.error('请先选择群组');
      return;
    }
    if (runDays <= 0) {
      toast.error('分析天数必须大于 0');
      return;
    }

    const hasResetRange = Boolean(resetStartDate && resetEndDate);
    const hasRunRange = Boolean(runStartDate && runEndDate);
    if ((runStartDate && !runEndDate) || (!runStartDate && runEndDate)) {
      toast.error('生成推荐池时，开始日期和结束日期需要同时填写');
      return;
    }
    if (hasRunRange && runStartDate > runEndDate) {
      toast.error('生成推荐池的开始日期不能晚于结束日期');
      return;
    }
    if ((resetStartDate && !resetEndDate) || (!resetStartDate && resetEndDate)) {
      toast.error('删除并重跑时，开始日期和结束日期需要同时填写');
      return;
    }

    try {
      setRunning(true);
      const response = await apiClient.runAShareAnalysis({
        group_id: selectedGroup.group_id,
        days: runDays,
        concurrency,
        ...(hasRunRange
          ? {
              start_date: runStartDate,
              end_date: runEndDate,
            }
          : {}),
        ...(hasResetRange
          ? {
              reset_start_date: resetStartDate,
              reset_end_date: resetEndDate,
            }
          : {}),
      });
      const taskId = (response as { task_id?: string })?.task_id;
      if (taskId) {
        setActiveRunTaskId(taskId);
        notifyTaskCreated(taskId, '股票推荐池任务已创建，结果会在完成后自动刷新');
      } else {
        toast.success('股票推荐池任务已创建，结果会在完成后自动刷新');
      }
      await loadStatus(false, selectedGroup.group_id);
    } catch (error) {
      handleTaskCreateError(error, '创建股票推荐池任务失败');
    } finally {
      setRunning(false);
    }
  };

  const handleResetOnly = async () => {
    if (!selectedGroup) {
      toast.error('请先选择群组');
      return;
    }
    if (!resetStartDate || !resetEndDate) {
      toast.error('请先填写要删除的开始日期和结束日期');
      return;
    }

    try {
      setResetting(true);
      await apiClient.resetAShareAnalysisRange({
        group_id: selectedGroup.group_id,
        start_date: resetStartDate,
        end_date: resetEndDate,
      });
      toast.success('指定日期区间的数据已删除');
      await refreshAll(false, selectedGroup.group_id);
    } catch (error) {
      toast.error(`删除日期区间失败: ${error instanceof Error ? error.message : '未知错误'}`);
    } finally {
      setResetting(false);
    }
  };

  const handleExportToTdx = async () => {
    if (!selectedGroup) {
      toast.error('请先选择群组');
      return;
    }
    try {
      setExportingTdx(true);
      const result = await apiClient.exportAShareRankingsToTdx({
        group_id: selectedGroup.group_id,
        group_name: selectedGroup.name,
        start_date: selectedStartDate || undefined,
        end_date: selectedEndDate || undefined,
      });
      summarizeTdxExport(result);
      await loadStatus(false, selectedGroup.group_id);
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
