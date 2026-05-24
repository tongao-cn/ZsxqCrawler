'use client';

import { useCallback, useState } from 'react';
import { toast } from 'sonner';

import { apiClient, getTaskConflictDetail } from '@/lib/api';
import type {
  CrawlSettingsValue,
  GroupCrawlLoading,
  GroupCrawlOption,
} from '@/components/GroupActionPanel';

interface UseCrawlActionsOptions {
  groupId: number;
  onTaskCreated: (taskId: string) => void;
  onTaskConflict?: (taskId: string) => void;
  loadGroupStats: () => void | Promise<void>;
  loadTopics: () => void | Promise<void>;
}

function getCurrentMonth() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
}

function buildMonthRange(month: string) {
  const matched = /^(\d{4})-(\d{2})$/.exec(month);
  if (!matched) return null;

  const year = Number(matched[1]);
  const monthNumber = Number(matched[2]);
  if (monthNumber < 1 || monthNumber > 12) return null;

  const lastDay = new Date(year, monthNumber, 0).getDate();
  return {
    startTime: `${month}-01`,
    endTime: `${month}-${String(lastDay).padStart(2, '0')}`,
  };
}

export function useCrawlActions({
  groupId,
  onTaskCreated,
  onTaskConflict,
  loadGroupStats,
  loadTopics,
}: UseCrawlActionsOptions) {
  const [crawlLoading, setCrawlLoading] = useState<GroupCrawlLoading>(null);
  const [selectedCrawlOption, setSelectedCrawlOption] = useState<GroupCrawlOption>('all');
  const [crawlSettingsOpen, setCrawlSettingsOpen] = useState(false);
  const [crawlInterval, setCrawlInterval] = useState(3.5);
  const [crawlLongSleepInterval, setCrawlLongSleepInterval] = useState(240);
  const [crawlPagesPerBatch, setCrawlPagesPerBatch] = useState(15);
  const [crawlIntervalMin, setCrawlIntervalMin] = useState<number>(2);
  const [crawlIntervalMax, setCrawlIntervalMax] = useState<number>(5);
  const [crawlLongSleepIntervalMin, setCrawlLongSleepIntervalMin] = useState<number>(180);
  const [crawlLongSleepIntervalMax, setCrawlLongSleepIntervalMax] = useState<number>(300);
  const [quickLastDays, setQuickLastDays] = useState<number>(30);
  const [crawlMonth, setCrawlMonth] = useState<string>(getCurrentMonth);
  const [topicSource, setTopicSource] = useState<'legacy' | 'official'>('official');
  const [latestDialogOpen, setLatestDialogOpen] = useState<boolean>(false);
  const [singleTopicId, setSingleTopicId] = useState<string>('');
  const [fetchingSingle, setFetchingSingle] = useState<boolean>(false);

  const reloadAfterTaskCreated = useCallback((delay: number) => {
    window.setTimeout(() => {
      void loadGroupStats();
      void loadTopics();
    }, delay);
  }, [loadGroupStats, loadTopics]);

  const buildCrawlSettings = useCallback(() => ({
    topicSource,
    crawlIntervalMin,
    crawlIntervalMax,
    longSleepIntervalMin: crawlLongSleepIntervalMin,
    longSleepIntervalMax: crawlLongSleepIntervalMax,
    pagesPerBatch: Math.max(crawlPagesPerBatch, 5),
  }), [
    crawlIntervalMax,
    crawlIntervalMin,
    crawlLongSleepIntervalMax,
    crawlLongSleepIntervalMin,
    crawlPagesPerBatch,
    topicSource,
  ]);

  const handleTaskCreateError = useCallback((error: unknown, fallback: string) => {
    const conflict = getTaskConflictDetail(error);
    if (conflict?.task_id) {
      toast.error(`已有任务 ${conflict.task_id} 正在运行`);
      onTaskConflict?.(conflict.task_id);
      return;
    }
    toast.error(`${fallback}: ${error instanceof Error ? error.message : '未知错误'}`);
  }, [onTaskConflict]);

  const handleCrawlLatest = useCallback(async () => {
    try {
      setLatestDialogOpen(false);
      setCrawlLoading('latest');

      const response = await apiClient.crawlLatestUntilComplete(groupId, buildCrawlSettings());
      const taskId = (response as any).task_id;
      toast.success(`任务已创建: ${taskId}`);
      onTaskCreated(taskId);
      reloadAfterTaskCreated(2000);
    } catch (error) {
      handleTaskCreateError(error, '创建任务失败');
    } finally {
      setCrawlLoading(null);
    }
  }, [buildCrawlSettings, groupId, handleTaskCreateError, onTaskCreated, reloadAfterTaskCreated]);

  const handleCrawlAll = useCallback(async () => {
    try {
      setCrawlLoading('all');

      const response = await apiClient.crawlAll(groupId, buildCrawlSettings());
      const taskId = (response as any).task_id;
      toast.success(`任务已创建: ${taskId}`);
      onTaskCreated(taskId);
      reloadAfterTaskCreated(2000);
    } catch (error) {
      handleTaskCreateError(error, '创建任务失败');
    } finally {
      setCrawlLoading(null);
    }
  }, [buildCrawlSettings, groupId, handleTaskCreateError, onTaskCreated, reloadAfterTaskCreated]);

  const handleIncrementalCrawl = useCallback(async () => {
    try {
      setCrawlLoading('incremental');

      const response = await apiClient.crawlIncremental(groupId, 10, 20, buildCrawlSettings());
      const taskId = (response as any).task_id;
      toast.success(`增量爬取任务已创建: ${taskId}`);
      onTaskCreated(taskId);
      reloadAfterTaskCreated(2000);
    } catch (error) {
      handleTaskCreateError(error, '增量爬取失败');
    } finally {
      setCrawlLoading(null);
    }
  }, [buildCrawlSettings, groupId, handleTaskCreateError, onTaskCreated, reloadAfterTaskCreated]);

  const handleCrawlLastDays = useCallback(async () => {
    try {
      setLatestDialogOpen(false);
      setCrawlLoading('range');

      const response = await apiClient.crawlByTimeRange(groupId, {
        lastDays: Math.max(1, quickLastDays || 1),
        ...buildCrawlSettings(),
      });
      const taskId = (response as any).task_id;
      toast.success(`任务已创建: ${taskId}`);
      onTaskCreated(taskId);
      reloadAfterTaskCreated(2000);
    } catch (error) {
      handleTaskCreateError(error, '创建任务失败');
    } finally {
      setCrawlLoading(null);
    }
  }, [buildCrawlSettings, groupId, handleTaskCreateError, onTaskCreated, quickLastDays, reloadAfterTaskCreated]);

  const handleCrawlMonth = useCallback(async () => {
    const range = buildMonthRange(crawlMonth);
    if (!range) {
      toast.error('请选择有效月份');
      return;
    }

    try {
      setLatestDialogOpen(false);
      setCrawlLoading('range');

      const response = await apiClient.crawlByTimeRange(groupId, {
        ...range,
        ...buildCrawlSettings(),
      });
      const taskId = (response as any).task_id;
      toast.success(`任务已创建: ${taskId}`);
      onTaskCreated(taskId);
      reloadAfterTaskCreated(2000);
    } catch (error) {
      handleTaskCreateError(error, '创建任务失败');
    } finally {
      setCrawlLoading(null);
    }
  }, [
    buildCrawlSettings,
    crawlMonth,
    groupId,
    handleTaskCreateError,
    onTaskCreated,
    reloadAfterTaskCreated,
  ]);

  const handleFetchSingleTopic = useCallback(async () => {
    if (!singleTopicId || Number.isNaN(parseInt(singleTopicId))) {
      toast.error('请输入有效的话题ID');
      return;
    }

    setFetchingSingle(true);
    try {
      const topicId = parseInt(singleTopicId);
      const response = await apiClient.fetchSingleTopic(groupId, topicId);
      toast.success(`已采集话题 ${topicId}（${(response as any)?.imported || 'ok'}）`);
      reloadAfterTaskCreated(800);
    } catch (error) {
      toast.error(`采集失败: ${error instanceof Error ? error.message : '未知错误'}`);
    } finally {
      setFetchingSingle(false);
    }
  }, [groupId, reloadAfterTaskCreated, singleTopicId]);

  const handleDeleteTopics = useCallback(async () => {
    try {
      await apiClient.clearTopicDatabase(groupId);
      toast.success('话题数据已删除');

      void loadGroupStats();
      void loadTopics();

      setSelectedCrawlOption('all');
    } catch (error) {
      toast.error(`删除失败: ${error instanceof Error ? error.message : '未知错误'}`);
    }
  }, [groupId, loadGroupStats, loadTopics]);

  const handleCrawlSettingsChange = useCallback((settings: CrawlSettingsValue) => {
    setCrawlInterval(settings.crawlInterval);
    setCrawlLongSleepInterval(settings.longSleepInterval);
    setCrawlPagesPerBatch(settings.pagesPerBatch);

    setCrawlIntervalMin(settings.crawlIntervalMin || 2);
    setCrawlIntervalMax(settings.crawlIntervalMax || 5);
    setCrawlLongSleepIntervalMin(settings.longSleepIntervalMin || 180);
    setCrawlLongSleepIntervalMax(settings.longSleepIntervalMax || 300);

    toast.success('话题爬取设置已更新');
  }, []);

  return {
    selectedCrawlOption,
    setSelectedCrawlOption,
    crawlLoading,
    crawlSettingsOpen,
    setCrawlSettingsOpen,
    crawlInterval,
    crawlLongSleepInterval,
    crawlPagesPerBatch,
    quickLastDays,
    setQuickLastDays,
    crawlMonth,
    setCrawlMonth,
    topicSource,
    setTopicSource,
    latestDialogOpen,
    setLatestDialogOpen,
    singleTopicId,
    setSingleTopicId,
    fetchingSingle,
    handleCrawlLatest,
    handleCrawlAll,
    handleIncrementalCrawl,
    handleCrawlLastDays,
    handleCrawlMonth,
    handleFetchSingleTopic,
    handleDeleteTopics,
    handleCrawlSettingsChange,
  };
}
