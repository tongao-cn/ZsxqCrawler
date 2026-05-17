'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { RefreshCw, Square, ListFilter } from 'lucide-react';
import { toast } from 'sonner';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { apiClient, Task } from '@/lib/api';

interface TaskListCompactProps {
  groupId?: number | string | null;
  selectedTaskId?: string | null;
  onSelectTask?: (taskId: string) => void;
  onTaskStop?: () => void;
}

function isActiveTask(task: Task) {
  return task.status === 'pending' || task.status === 'running';
}

function normalizeGroupId(value?: string | number | null) {
  if (value === undefined || value === null) {
    return null;
  }
  const text = String(value).trim();
  return text || null;
}

function getTaskTypeLabel(type: string) {
  switch (type) {
    case 'crawl_latest':
    case 'crawl_latest_until_complete':
      return '获取最新';
    case 'crawl_historical':
      return '历史采集';
    case 'crawl_incremental':
      return '增量采集';
    case 'crawl_all':
      return '全量采集';
    case 'crawl_time_range':
      return '时间区间';
    case 'collect_files':
      return '收集文件';
    case 'download_files':
      return '下载文件';
    case 'download_single_file':
      return '单文件下载';
    case 'sync_files_from_topics':
      return '同步文件';
    case 'columns_fetch':
      return '专栏采集';
    case 'a_share_analysis':
      return '股票推荐池';
    case 'stock_topic_analysis':
      return '个股分析';
    case 'stock_topic_analysis_batch':
      return '批量个股分析';
    case 'stock_question_analysis':
      return 'A股问答';
    default:
      return type;
  }
}

function getStatusBadge(task: Task) {
  switch (task.status) {
    case 'pending':
      return <Badge className="bg-amber-100 text-amber-800">等待中</Badge>;
    case 'running':
      return <Badge className="bg-blue-100 text-blue-800">运行中</Badge>;
    case 'completed':
      return <Badge className="bg-green-100 text-green-800">已完成</Badge>;
    case 'failed':
      return <Badge className="bg-red-100 text-red-800">失败</Badge>;
    case 'cancelled':
      return <Badge className="bg-gray-100 text-gray-700">已停止</Badge>;
    default:
      return <Badge variant="secondary">{task.status}</Badge>;
  }
}

function formatTime(value?: string) {
  if (!value) {
    return '-';
  }
  try {
    return new Date(value).toLocaleString('zh-CN');
  } catch {
    return value;
  }
}

function formatDuration(startValue?: string, endValue?: string) {
  if (!startValue) {
    return '-';
  }
  const start = new Date(startValue).getTime();
  const end = endValue ? new Date(endValue).getTime() : Date.now();
  if (!Number.isFinite(start) || !Number.isFinite(end)) {
    return '-';
  }
  const seconds = Math.max(0, Math.floor((end - start) / 1000));
  if (seconds < 60) {
    return `${seconds}秒`;
  }
  if (seconds < 3600) {
    return `${Math.floor(seconds / 60)}分${seconds % 60}秒`;
  }
  return `${Math.floor(seconds / 3600)}小时${Math.floor((seconds % 3600) / 60)}分`;
}

export default function TaskListCompact({
  groupId,
  selectedTaskId,
  onSelectTask,
  onTaskStop,
}: TaskListCompactProps) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(false);
  const [showAllTasks, setShowAllTasks] = useState(false);
  const [stoppingTaskId, setStoppingTaskId] = useState<string | null>(null);
  const loadingRef = useRef(false);
  const normalizedGroupId = normalizeGroupId(groupId);

  const loadTasks = useCallback(async () => {
    if (loadingRef.current) {
      return;
    }
    try {
      loadingRef.current = true;
      setLoading(true);
      const data = await apiClient.getTasks();
      setTasks(data);
    } catch (error) {
      toast.error(`加载任务列表失败: ${error instanceof Error ? error.message : '未知错误'}`);
    } finally {
      loadingRef.current = false;
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadTasks();
  }, [loadTasks]);

  useEffect(() => {
    const interval = window.setInterval(() => {
      void loadTasks();
    }, 3000);
    return () => window.clearInterval(interval);
  }, [loadTasks]);

  const visibleTasks = useMemo(() => {
    const filtered = showAllTasks || !normalizedGroupId
      ? tasks
      : tasks.filter((task) => normalizeGroupId(task.group_id) === normalizedGroupId);
    return [...filtered].sort((a, b) => {
      if (isActiveTask(a) !== isActiveTask(b)) {
        return isActiveTask(a) ? -1 : 1;
      }
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
    });
  }, [normalizedGroupId, showAllTasks, tasks]);

  const activeCount = visibleTasks.filter(isActiveTask).length;

  const handleStopTask = async (task: Task) => {
    if (!isActiveTask(task) || stoppingTaskId) {
      return;
    }
    try {
      setStoppingTaskId(task.task_id);
      await apiClient.stopTask(task.task_id);
      toast.success(`已发送停止请求: ${task.task_id}`);
      await loadTasks();
      onTaskStop?.();
    } catch (error) {
      toast.error(`停止任务失败: ${error instanceof Error ? error.message : '未知错误'}`);
    } finally {
      setStoppingTaskId(null);
    }
  };

  return (
    <div className="flex h-full flex-col p-3">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-gray-200 bg-white p-3">
        <div className="min-w-0">
          <div className="text-sm font-medium text-gray-900">任务列表</div>
          <div className="text-xs text-gray-500">
            {showAllTasks || !normalizedGroupId ? '全部任务' : `当前群组 ${normalizedGroupId}`} · 运行中 {activeCount}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            className="h-8 gap-1 text-xs"
            onClick={() => setShowAllTasks((value) => !value)}
          >
            <ListFilter className="h-3.5 w-3.5" />
            {showAllTasks ? '当前群组' : '全部任务'}
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="h-8 gap-1 text-xs"
            onClick={() => void loadTasks()}
            disabled={loading}
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
            刷新
          </Button>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-hidden rounded-lg border border-gray-200 bg-white">
        <ScrollArea className="h-full">
          {visibleTasks.length === 0 ? (
            <div className="flex h-48 items-center justify-center text-sm text-muted-foreground">
              暂无任务记录
            </div>
          ) : (
            <div className="divide-y divide-gray-100">
              {visibleTasks.map((task) => (
                <div
                  key={task.task_id}
                  className={`grid gap-3 p-3 text-sm md:grid-cols-[minmax(0,1.2fr)_96px_minmax(0,1.5fr)_180px_90px] ${
                    task.task_id === selectedTaskId ? 'bg-blue-50' : 'bg-white'
                  }`}
                >
                  <button
                    type="button"
                    className="min-w-0 text-left"
                    onClick={() => onSelectTask?.(task.task_id)}
                  >
                    <div className="truncate font-medium text-gray-900">{getTaskTypeLabel(task.type)}</div>
                    <div className="truncate font-mono text-xs text-gray-500">{task.task_id}</div>
                    <div className="truncate text-xs text-gray-500">群组: {normalizeGroupId(task.group_id) || '-'}</div>
                  </button>
                  <div>{getStatusBadge(task)}</div>
                  <div className="min-w-0">
                    <div className="truncate text-gray-700" title={task.message}>{task.message}</div>
                    <div className="text-xs text-gray-500">耗时 {formatDuration(task.created_at, isActiveTask(task) ? undefined : task.updated_at)}</div>
                  </div>
                  <div className="text-xs text-gray-500">
                    <div>创建 {formatTime(task.created_at)}</div>
                    <div>更新 {formatTime(task.updated_at)}</div>
                  </div>
                  <div className="flex items-start justify-end">
                    {isActiveTask(task) ? (
                      <Button
                        variant="destructive"
                        size="sm"
                        className="h-8 gap-1 text-xs"
                        onClick={() => void handleStopTask(task)}
                        disabled={Boolean(stoppingTaskId)}
                      >
                        <Square className="h-3.5 w-3.5" />
                        {stoppingTaskId === task.task_id ? '停止中' : '停止'}
                      </Button>
                    ) : (
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-8 text-xs"
                        onClick={() => onSelectTask?.(task.task_id)}
                      >
                        日志
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </ScrollArea>
      </div>
    </div>
  );
}
