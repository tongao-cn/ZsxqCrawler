'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { RefreshCw, Play, Eraser, TrendingUp, Database, Activity, Upload } from 'lucide-react';

import {
  apiClient,
  AShareAnalysisChart,
  AShareAnalysisExportTdxResponse,
  AShareAnalysisStatus,
  Group,
  Task,
} from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { toast } from 'sonner';

const DEFAULT_TOP_N = 12;

interface AShareAnalysisPanelProps {
  onTaskCreated?: (taskId: string) => void;
  selectedGroup?: Group | null;
}

function compareSeriesByTotal(
  a: { total: number; label: string },
  b: { total: number; label: string }
) {
  if (b.total !== a.total) {
    return b.total - a.total;
  }
  return a.label.localeCompare(b.label, 'zh-CN');
}

function formatDateTime(value?: string | null) {
  if (!value) {
    return '暂无';
  }
  return new Date(value).toLocaleString('zh-CN');
}

function formatDateRange(start?: string | null, end?: string | null) {
  if (start && end) {
    return `${start} 至 ${end}`;
  }
  if (start) {
    return start;
  }
  if (end) {
    return end;
  }
  return '全范围';
}

function getTaskStatusBadge(task?: Task | null) {
  const status = task?.status;
  if (status === 'running') {
    return <Badge className="bg-blue-100 text-blue-800">运行中</Badge>;
  }
  if (status === 'completed') {
    return <Badge className="bg-green-100 text-green-800">已完成</Badge>;
  }
  if (status === 'failed') {
    return <Badge className="bg-red-100 text-red-800">失败</Badge>;
  }
  if (status === 'pending') {
    return <Badge className="bg-amber-100 text-amber-800">等待中</Badge>;
  }
  return <Badge variant="secondary">暂无任务</Badge>;
}

export default function AShareAnalysisPanel({
  onTaskCreated,
  selectedGroup,
}: AShareAnalysisPanelProps) {
  const selectedGroupId = selectedGroup?.group_id;
  const [status, setStatus] = useState<AShareAnalysisStatus | null>(null);
  const [chart, setChart] = useState<AShareAnalysisChart | null>(null);
  const [loadingStatus, setLoadingStatus] = useState(false);
  const [loadingChart, setLoadingChart] = useState(false);
  const [running, setRunning] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [exportingTdx, setExportingTdx] = useState(false);

  const [topN, setTopN] = useState<number>(DEFAULT_TOP_N);
  const [selectedStartDate, setSelectedStartDate] = useState('');
  const [selectedEndDate, setSelectedEndDate] = useState('');
  const [runDays, setRunDays] = useState(21);
  const [retentionDays, setRetentionDays] = useState(30);
  const [concurrency, setConcurrency] = useState(10);
  const [resetStartDate, setResetStartDate] = useState('');
  const [resetEndDate, setResetEndDate] = useState('');
  const [initialized, setInitialized] = useState(false);

  const rankingWindows = useMemo(
    () => status?.defaults.ranking_windows ?? [3, 7, 14, 21],
    [status]
  );
  const sortedSeries = useMemo(
    () => [...(chart?.series || [])].sort(compareSeriesByTotal),
    [chart]
  );
  const renderedLineSeries = useMemo(
    () => [...sortedSeries].reverse(),
    [sortedSeries]
  );

  useEffect(() => {
    if (!selectedGroupId) {
      setStatus(null);
      setChart(null);
      setInitialized(false);
      return;
    }

    let cancelled = false;
    setInitialized(false);
    setTopN(DEFAULT_TOP_N);
    void (async () => {
      try {
        setLoadingStatus(true);
        const statusData = await apiClient.getAShareAnalysisStatus(selectedGroupId);
        if (cancelled) {
          return;
        }

        setStatus(statusData);
        setRunDays(statusData.defaults.days);
        setRetentionDays(statusData.defaults.retention_days);
        setConcurrency(statusData.defaults.concurrency);
        setSelectedStartDate(statusData.summary.available_start_date || '');
        setSelectedEndDate(statusData.summary.available_end_date || '');
        setResetStartDate('');
        setResetEndDate('');
        setInitialized(true);
      } catch (error) {
        if (!cancelled) {
          toast.error(`加载A股分析状态失败: ${error instanceof Error ? error.message : '未知错误'}`);
        }
      } finally {
        if (!cancelled) {
          setLoadingStatus(false);
        }
      }

      try {
        setLoadingChart(true);
        const chartData = await apiClient.getAShareAnalysisChart({
          groupId: selectedGroupId,
          topN: DEFAULT_TOP_N,
        });
        if (!cancelled) {
          setChart(chartData);
        }
      } catch (error) {
        if (!cancelled) {
          toast.error(`加载A股分析图表失败: ${error instanceof Error ? error.message : '未知错误'}`);
        }
      } finally {
        if (!cancelled) {
          setLoadingChart(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [selectedGroupId]);

  const loadStatus = useCallback(
    async (bootstrap: boolean = false, groupId?: number) => {
      if (!groupId) {
        return;
      }
      try {
        setLoadingStatus(true);
        const data = await apiClient.getAShareAnalysisStatus(groupId);
        setStatus(data);

        if (!initialized || bootstrap) {
          setRunDays(data.defaults.days);
          setRetentionDays(data.defaults.retention_days);
          setConcurrency(data.defaults.concurrency);
          setSelectedStartDate(data.summary.available_start_date || '');
          setSelectedEndDate(data.summary.available_end_date || '');
          setResetStartDate('');
          setResetEndDate('');
          setInitialized(true);
        }
      } catch (error) {
        toast.error(`加载A股分析状态失败: ${error instanceof Error ? error.message : '未知错误'}`);
      } finally {
        setLoadingStatus(false);
      }
    },
    [initialized]
  );

  const loadChart = useCallback(
    async (options?: {
      groupId?: number;
      startDate?: string;
      endDate?: string;
      topN?: number;
      bootstrap?: boolean;
    }) => {
      if (!options?.groupId) {
        return;
      }
      try {
        setLoadingChart(true);
        const data = await apiClient.getAShareAnalysisChart({
          groupId: options.groupId,
          startDate: options?.startDate,
          endDate: options?.endDate,
          topN: options?.topN ?? topN,
        });
        setChart(data);
      } catch (error) {
        toast.error(`加载A股分析图表失败: ${error instanceof Error ? error.message : '未知错误'}`);
      } finally {
        setLoadingChart(false);
      }
    },
    [topN]
  );

  const refreshAll = useCallback(
    async (bootstrap: boolean = false, groupId?: number) => {
      const activeGroupId = groupId ?? selectedGroupId;
      if (!activeGroupId) {
        return;
      }
      await loadStatus(bootstrap, activeGroupId);
      await loadChart({
        groupId: activeGroupId,
        startDate: bootstrap ? undefined : selectedStartDate || undefined,
        endDate: bootstrap ? undefined : selectedEndDate || undefined,
        topN,
        bootstrap,
      });
    },
    [loadChart, loadStatus, selectedEndDate, selectedGroupId, selectedStartDate, topN]
  );

  useEffect(() => {
    if (!selectedGroupId) {
      return;
    }
    const isTaskRunning =
      status?.running_task?.status === 'running' || status?.latest_task?.status === 'running';
    if (!isTaskRunning) {
      return;
    }

    const timer = window.setInterval(() => {
      void refreshAll(false, selectedGroupId);
    }, 5000);

    return () => {
      window.clearInterval(timer);
    };
  }, [refreshAll, selectedGroupId, status?.latest_task?.status, status?.running_task?.status]);

  const handleApplyFilters = async () => {
    if (!selectedGroup) {
      toast.error('请先选择群组');
      return;
    }
    await loadChart({
      groupId: selectedGroup.group_id,
      startDate: selectedStartDate || undefined,
      endDate: selectedEndDate || undefined,
      topN,
    });
  };

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
    if ((resetStartDate && !resetEndDate) || (!resetStartDate && resetEndDate)) {
      toast.error('删除并重跑时，开始日期和结束日期需要同时填写');
      return;
    }

    try {
      setRunning(true);
      const response = await apiClient.runAShareAnalysis({
        group_id: selectedGroup.group_id,
        days: runDays,
        retention_days: retentionDays,
        concurrency: concurrency,
        ...(hasResetRange
          ? {
              reset_start_date: resetStartDate,
              reset_end_date: resetEndDate,
            }
          : {}),
      });
      toast.success('A股分析任务已创建，结果会在完成后自动刷新');
      if ((response as { task_id?: string })?.task_id && onTaskCreated) {
        onTaskCreated((response as { task_id: string }).task_id);
      }
      await loadStatus(false, selectedGroup.group_id);
    } catch (error) {
      toast.error(`创建A股分析任务失败: ${error instanceof Error ? error.message : '未知错误'}`);
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

  const summarizeTdxExport = (result: AShareAnalysisExportTdxResponse) => {
    const blockText = result.blocks
      .map((block) => `${block.window_days}日 ${block.written_count}只`)
      .join('，');

    if (result.unresolved_companies.length > 0) {
      toast.success(`已导入通达信：${blockText}；未匹配 ${result.unresolved_companies.length} 个公司`);
      return;
    }

    toast.success(`已导入通达信：${blockText}`);
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

  const summary = status?.summary;
  const latestTask = status?.latest_task;
  const latestExport = status?.latest_tdx_export;
  const storage = status?.storage;
  const latestTaskResult = latestTask?.result as
    | { days?: number; items_discovered?: number; items_processed?: number }
    | undefined;
  const hasChartData = Boolean(chart && chart.chart_data.length > 0);
  const scopeName = selectedGroup?.name || '当前群组';
  const emptyStateMessage = useMemo(() => {
    if (loadingChart) {
      return '图表加载中...';
    }
    if (latestTask?.status === 'running') {
      return '分析任务运行中，结果会在完成后自动刷新';
    }
    if (latestTask?.status === 'failed') {
      return latestTask.message || '最近一次分析失败，请到任务状态查看日志';
    }
    if (!summary?.output_exists && (summary?.source_topics_count ?? 0) > 0) {
      return '当前群已有源话题数据，但还没有生成推荐池结果';
    }
    if ((summary?.source_topics_count ?? 0) === 0) {
      return '当前群话题库为空，请先到“话题采集”抓取或同步话题数据';
    }
    if (latestTask?.status === 'completed' && (latestTaskResult?.items_discovered ?? 0) === 0) {
      return `最近 ${latestTaskResult?.days ?? runDays} 天没有可分析的话题，结果为空`;
    }
    if (summary?.source_latest_topic_time) {
      return `当前还没有分析结果，源话题库最新话题时间为 ${formatDateTime(summary.source_latest_topic_time)}`;
    }
    return '暂无可展示的分析数据';
  }, [latestTask, latestTaskResult, loadingChart, runDays, summary]);
  const emptyStateHint = useMemo(() => {
    const sourceTopicsCount = summary?.source_topics_count;
    const latestTopicTime = summary?.source_latest_topic_time;
    if (sourceTopicsCount === null || sourceTopicsCount === undefined) {
      return null;
    }

    const parts = [`源话题数 ${sourceTopicsCount}`];
    if (latestTopicTime) {
      parts.push(`最新话题 ${formatDateTime(latestTopicTime)}`);
    }
    return parts.join('，');
  }, [summary]);

  if (!selectedGroup) {
    return (
      <Card className="border border-gray-200 shadow-none">
        <CardHeader>
          <CardTitle>A股分析</CardTitle>
          <CardDescription>请先选择群组，再查看该群的推荐池分析和排序。</CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        <Card className="border border-gray-200 shadow-none">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Database className="h-4 w-4" />
              数据覆盖
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-xl font-semibold">{summary?.date_count || 0} 天</div>
            <p className="text-xs text-muted-foreground mt-1">
              {summary?.available_start_date || '暂无'} 至 {summary?.available_end_date || '暂无'}
            </p>
          </CardContent>
        </Card>

        <Card className="border border-gray-200 shadow-none">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <TrendingUp className="h-4 w-4" />
              公司数
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-xl font-semibold">{summary?.unique_companies || 0}</div>
            <p className="text-xs text-muted-foreground mt-1">当前分析结果中的累计去重公司数</p>
          </CardContent>
        </Card>

        <Card className="border border-gray-200 shadow-none">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Activity className="h-4 w-4" />
              提及总数
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-xl font-semibold">{summary?.total_mentions || 0}</div>
            <p className="text-xs text-muted-foreground mt-1">累计文章提及次数</p>
          </CardContent>
        </Card>

        <Card className="border border-gray-200 shadow-none">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">最新任务</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between gap-2">
              {getTaskStatusBadge(latestTask)}
              <Badge variant={status?.api_key_configured ? 'secondary' : 'destructive'}>
                {status?.api_key_configured ? 'API Key 已配置' : '缺少 API Key'}
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground mt-2">
              更新于 {formatDateTime(summary?.updated_at)}
            </p>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <Card className="border border-gray-200 shadow-none">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">存储状态</CardTitle>
            <CardDescription>当前分析结果的主存储位置</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center justify-between gap-3">
              <div className="font-medium">{storage?.label || '本地文件镜像'}</div>
              <Badge variant={storage?.enabled ? 'secondary' : 'outline'}>
                {storage?.enabled ? 'PostgreSQL 已启用' : '文件模式'}
              </Badge>
            </div>
            <div className="grid grid-cols-2 gap-3 text-sm text-muted-foreground">
              <div className="rounded-lg border border-gray-200 bg-gray-50 p-3">
                <div>提及行数</div>
                <div className="mt-1 text-lg font-semibold text-foreground">
                  {storage?.daily_rows ?? summary?.rows_count ?? 0}
                </div>
              </div>
              <div className="rounded-lg border border-gray-200 bg-gray-50 p-3">
                <div>增量状态</div>
                <div className="mt-1 text-lg font-semibold text-foreground">
                  {storage?.processed_rows ?? summary?.processed_items ?? 0}
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border border-gray-200 shadow-none">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">最近一次通达信导入</CardTitle>
            <CardDescription>展示最近一次覆盖导入的结果摘要</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {!latestExport ? (
              <div className="text-sm text-muted-foreground">还没有导入记录</div>
            ) : (
              <>
                <div className="flex items-center justify-between gap-3">
                  <div className="font-medium">{formatDateTime(latestExport.exported_at)}</div>
                  <Badge variant="secondary">导入ID {latestExport.export_id}</Badge>
                </div>
                <div className="text-sm text-muted-foreground">
                  范围：{formatDateRange(latestExport.start_date, latestExport.end_date)}
                </div>
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div className="rounded-lg border border-gray-200 bg-gray-50 p-3">
                    <div className="text-muted-foreground">写入总数</div>
                    <div className="mt-1 text-lg font-semibold">{latestExport.total_written}</div>
                  </div>
                  <div className="rounded-lg border border-gray-200 bg-gray-50 p-3">
                    <div className="text-muted-foreground">未匹配公司</div>
                    <div className="mt-1 text-lg font-semibold">{latestExport.unresolved_count}</div>
                  </div>
                </div>
                <div className="text-sm text-muted-foreground">
                  股票主数据：{latestExport.stock_basic_source || '未知'}
                </div>
                <div className="grid grid-cols-2 gap-2">
                  {latestExport.blocks.map((block) => (
                    <div
                      key={`latest-export-${block.window_days}`}
                      className="rounded-lg border border-gray-200 bg-gray-50 p-3 text-sm"
                    >
                      <div className="font-medium">{block.block_name}</div>
                      <div className="mt-1 text-muted-foreground">
                        写入 {block.written_count}，跳过 {block.skipped_count}
                      </div>
                    </div>
                  ))}
                </div>
                {latestExport.unresolved_companies.length > 0 && (
                  <div className="rounded-lg border border-amber-200 bg-amber-50 p-3">
                    <div className="text-sm font-medium text-amber-900">未匹配公司</div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {latestExport.unresolved_companies.slice(0, 16).map((company) => (
                        <Badge key={company} variant="outline" className="bg-white">
                          {company}
                        </Badge>
                      ))}
                      {latestExport.unresolved_companies.length > 16 && (
                        <Badge variant="outline" className="bg-white">
                          +{latestExport.unresolved_companies.length - 16}
                        </Badge>
                      )}
                    </div>
                  </div>
                )}
              </>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <Card className="border border-gray-200 shadow-none xl:col-span-2">
          <CardHeader>
            <div className="flex items-center justify-between gap-3">
              <div>
                <CardTitle>A股分析图表</CardTitle>
                <CardDescription>{scopeName} 的独立分析结果，可按当前群组同步到通达信</CardDescription>
              </div>
              <div className="flex items-center gap-2">
                <Button variant="outline" size="sm" onClick={() => void refreshAll(false, selectedGroup.group_id)} disabled={loadingStatus || loadingChart}>
                  <RefreshCw className={`h-4 w-4 mr-2 ${loadingStatus || loadingChart ? 'animate-spin' : ''}`} />
                  刷新
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => void handleExportToTdx()}
                  disabled={exportingTdx}
                >
                  <Upload className={`h-4 w-4 mr-2 ${exportingTdx ? 'animate-pulse' : ''}`} />
                  {exportingTdx ? '导入中...' : '导入到通达信'}
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
              <div className="space-y-2">
                <Label htmlFor="a-share-start-date">开始日期</Label>
                <Input
                  id="a-share-start-date"
                  type="date"
                  value={selectedStartDate}
                  min={summary?.available_start_date || undefined}
                  max={summary?.available_end_date || undefined}
                  onChange={(e) => setSelectedStartDate(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="a-share-end-date">结束日期</Label>
                <Input
                  id="a-share-end-date"
                  type="date"
                  value={selectedEndDate}
                  min={summary?.available_start_date || undefined}
                  max={summary?.available_end_date || undefined}
                  onChange={(e) => setSelectedEndDate(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="a-share-top-n">图表公司数</Label>
                <Input
                  id="a-share-top-n"
                  type="number"
                  min={1}
                  max={100}
                  value={topN}
                  onChange={(e) => setTopN(Number(e.target.value) || DEFAULT_TOP_N)}
                />
              </div>
              <div className="space-y-2">
                <Label className="opacity-0">操作</Label>
                <Button className="w-full" onClick={() => void handleApplyFilters()} disabled={loadingChart}>
                  {loadingChart ? '加载中...' : '更新图表'}
                </Button>
              </div>
            </div>

            <div className="text-sm text-muted-foreground">
              当前范围内公司数: {chart?.total_companies_in_range || 0}，折线展示 Top {chart?.company_count || 0}
            </div>

            <div className="h-[440px]">
              {hasChartData ? (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chart?.chart_data} margin={{ top: 16, right: 24, left: 8, bottom: 16 }}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" minTickGap={24} />
                    <YAxis allowDecimals={false} />
                    <Tooltip
                      itemSorter={(item) => -Number(item?.value ?? 0)}
                    />
                    {renderedLineSeries.map((series) => (
                      <Line
                        key={series.key}
                        type="monotone"
                        dataKey={series.key}
                        name={`${series.label} (${series.total})`}
                        stroke={series.color}
                        strokeWidth={2}
                        dot={false}
                        activeDot={{ r: 4 }}
                      />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full flex flex-col items-center justify-center gap-2 border border-dashed rounded-lg px-6 text-center text-muted-foreground">
                  <div>{emptyStateMessage}</div>
                  {emptyStateHint ? <div className="text-xs">{emptyStateHint}</div> : null}
                </div>
              )}
            </div>

            {sortedSeries.length > 0 && (
              <div className="rounded-lg border border-gray-200 bg-gray-50 p-3">
                <div className="text-sm font-medium mb-3">图表公司排序</div>
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-x-4 gap-y-2">
                  {sortedSeries.map((series, index) => (
                    <div
                      key={`legend-${series.key}`}
                      className="flex items-center gap-2 text-sm min-w-0"
                    >
                      <span className="text-muted-foreground tabular-nums w-6">{index + 1}</span>
                      <span
                        className="h-2.5 w-2.5 rounded-full shrink-0"
                        style={{ backgroundColor: series.color }}
                      />
                      <span className="truncate" title={series.label}>
                        {series.label}
                      </span>
                      <span className="ml-auto font-medium tabular-nums">{series.total}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="border border-gray-200 shadow-none">
          <CardHeader>
            <CardTitle>运行控制</CardTitle>
            <CardDescription>当前只处理 {scopeName} 的数据；可以直接重跑，也可以先删除一段结果再补跑</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="a-share-run-days">扫描最近天数</Label>
              <Input
                id="a-share-run-days"
                type="number"
                min={1}
                max={365}
                value={runDays}
                onChange={(e) => setRunDays(Number(e.target.value) || 21)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="a-share-retention">保留天数</Label>
              <Input
                id="a-share-retention"
                type="number"
                min={1}
                max={3650}
                value={retentionDays}
                onChange={(e) => setRetentionDays(Number(e.target.value) || 30)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="a-share-concurrency">并发数</Label>
              <Input
                id="a-share-concurrency"
                type="number"
                min={1}
                max={128}
                value={concurrency}
                onChange={(e) => setConcurrency(Number(e.target.value) || 1)}
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <Label htmlFor="a-share-reset-start">删除开始日期</Label>
                <Input
                  id="a-share-reset-start"
                  type="date"
                  value={resetStartDate}
                  min={summary?.available_start_date || undefined}
                  max={summary?.available_end_date || undefined}
                  onChange={(e) => setResetStartDate(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="a-share-reset-end">删除结束日期</Label>
                <Input
                  id="a-share-reset-end"
                  type="date"
                  value={resetEndDate}
                  min={summary?.available_start_date || undefined}
                  max={summary?.available_end_date || undefined}
                  onChange={(e) => setResetEndDate(e.target.value)}
                />
              </div>
            </div>

            <div className="grid grid-cols-1 gap-2">
              <Button onClick={() => void handleRunAnalysis()} disabled={running}>
                <Play className="h-4 w-4 mr-2" />
                {running ? '创建任务中...' : '开始分析 / 删除并重跑'}
              </Button>
              <Button variant="outline" onClick={() => void handleResetOnly()} disabled={resetting}>
                <Eraser className="h-4 w-4 mr-2" />
                {resetting ? '删除中...' : '仅删除区间数据'}
              </Button>
            </div>

            <div className="rounded-lg bg-gray-50 border border-gray-200 p-3 text-sm text-muted-foreground space-y-1">
              <p>1. 不填删除日期时，点击上方按钮会直接重跑最近 N 天。</p>
              <p>2. 填写删除日期后，再点击上方按钮，会先删这段结果再补跑。</p>
              <p>3. 当前分析和推荐池排序仅针对已选中的群组，不再混合其他群组数据。</p>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        {rankingWindows.map((windowDays) => {
          const rankingRows = chart?.rankings?.[String(windowDays)] || [];
          return (
            <Card key={windowDays} className="border border-gray-200 shadow-none">
              <CardHeader className="pb-3">
                <CardTitle className="text-base">{windowDays} 日推荐池排序</CardTitle>
                <CardDescription>Top {chart?.ranking_top_n || 35}</CardDescription>
              </CardHeader>
              <CardContent>
                {rankingRows.length === 0 ? (
                  <div className="text-sm text-muted-foreground">暂无数据</div>
                ) : (
                  <div className="space-y-2">
                    {rankingRows.map((item, index) => (
                      <div
                        key={`${windowDays}-${item.company}`}
                        className="grid grid-cols-[28px_minmax(0,1fr)_auto] gap-2 text-sm items-center border-b border-dashed pb-2 last:border-b-0"
                      >
                        <span className="text-muted-foreground">{index + 1}</span>
                        <span className="truncate" title={item.company}>
                          {item.company}
                        </span>
                        <span className="font-medium tabular-nums">{item.count}</span>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
