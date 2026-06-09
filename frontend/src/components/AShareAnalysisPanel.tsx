'use client';

import { ReactNode, useMemo, useState } from 'react';
import { TrendingUp, Database, Activity } from 'lucide-react';

import {
  AShareAnalysisStorageStatus,
  AShareAnalysisSummary,
  Group,
  Task,
} from '@/lib/api';
import { useAShareAnalysisActions } from '@/hooks/useAShareAnalysisActions';
import { useAShareAnalysisData } from '@/hooks/useAShareAnalysisData';
import { useTaskStatus } from '@/hooks/useTaskStatus';
import AShareActionPanel from '@/components/AShareActionPanel';
import AShareAnalysisResultsSection from '@/components/AShareAnalysisResultsSection';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
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

interface SummaryCardsProps {
  apiKeyConfigured?: boolean;
  latestTask?: Task | null;
  nextStepMessage: string;
  storage?: AShareAnalysisStorageStatus;
  summary?: AShareAnalysisSummary;
}

function SummaryCards({
  apiKeyConfigured,
  latestTask,
  nextStepMessage,
  storage,
  summary,
}: SummaryCardsProps) {
  return (
    <Card className="border border-gray-200 shadow-none">
      <CardContent className="p-4">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-[1fr_1fr_1fr_1.4fr]">
          <CompactMetric
            icon={<Database className="h-4 w-4" />}
            label="数据覆盖"
            value={`${summary?.date_count || 0} 天`}
            detail={`${summary?.available_start_date || '暂无'} 至 ${summary?.available_end_date || '暂无'}`}
          />
          <CompactMetric
            icon={<TrendingUp className="h-4 w-4" />}
            label="公司数"
            value={String(summary?.unique_companies || 0)}
            detail="累计去重公司"
          />
          <CompactMetric
            icon={<Activity className="h-4 w-4" />}
            label="提及总数"
            value={String(summary?.total_mentions || 0)}
            detail="累计文章提及次数"
          />
          <div className="min-w-0">
            <div className="mb-2 text-sm font-medium text-gray-900">当前状态</div>
            <div className="flex flex-wrap items-center gap-2">
              {getTaskStatusBadge(latestTask)}
              <Badge variant={apiKeyConfigured ? 'secondary' : 'destructive'}>
                {apiKeyConfigured ? 'API Key 已配置' : '缺少 API Key'}
              </Badge>
            </div>
            <p className="mt-2 text-xs text-muted-foreground">{nextStepMessage}</p>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-gray-200 pt-3 text-sm">
          <span className="font-medium text-gray-900">存储：{storage?.label || '存储状态未知'}</span>
          <Badge variant={storage?.enabled ? 'secondary' : 'outline'}>
            {storage?.enabled ? 'PostgreSQL 已启用' : '本地文件降级'}
          </Badge>
          <span className="text-muted-foreground">
            提及行数 <span className="font-semibold text-foreground">{storage?.daily_rows ?? summary?.rows_count ?? 0}</span>
          </span>
          <span className="text-muted-foreground">
            增量状态 <span className="font-semibold text-foreground">{storage?.processed_rows ?? summary?.processed_items ?? 0}</span>
          </span>
        </div>
      </CardContent>
    </Card>
  );
}

interface CompactMetricProps {
  detail: string;
  icon: ReactNode;
  label: string;
  value: string;
}

function CompactMetric({ detail, icon, label, value }: CompactMetricProps) {
  return (
    <div className="min-w-0">
      <div className="flex items-center gap-2 text-sm font-medium text-gray-900">
        {icon}
        <span>{label}</span>
      </div>
      <div className="mt-2 text-2xl font-semibold">{value}</div>
      <div className="mt-1 truncate text-xs text-muted-foreground" title={detail}>
        {detail}
      </div>
    </div>
  );
}

export default function AShareAnalysisPanel({
  onTaskCreated,
  selectedGroup,
}: AShareAnalysisPanelProps) {
  const selectedGroupId = selectedGroup?.group_id;
  const {
    chart,
    concurrency,
    loadChart,
    loadStatus,
    loadingChart,
    loadingStatus,
    refreshAll,
    resetEndDate,
    resetStartDate,
    runDays,
    runEndDate,
    runStartDate,
    selectedEndDate,
    selectedStartDate,
    setConcurrency,
    setResetEndDate,
    setResetStartDate,
    setRunDays,
    setRunEndDate,
    setRunStartDate,
    setSelectedEndDate,
    setSelectedStartDate,
    setTopN,
    status,
    topN,
  } = useAShareAnalysisData({
    defaultTopN: DEFAULT_TOP_N,
    selectedGroupId,
  });

  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [activeRunTaskId, setActiveRunTaskId] = useState<string | null>(null);
  const {
    exportingTdx,
    handleExportToTdx,
    handleResetOnly,
    handleRunAnalysis,
    resetting,
    running,
  } = useAShareAnalysisActions({
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
  });

  const rankingWindows = useMemo(
    () => status?.defaults.ranking_windows ?? [30],
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

  useTaskStatus(activeRunTaskId, {
    enabled: Boolean(activeRunTaskId && selectedGroupId),
    onTerminal: async () => {
      if (selectedGroupId) {
        await refreshAll(false, selectedGroupId);
      }
      setActiveRunTaskId(null);
    },
  });

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
  const nextStepMessage = useMemo(() => {
    if (!status?.api_key_configured) {
      return '缺少 API Key，需先配置后再生成新结果';
    }
    if (latestTask?.status === 'running') {
      return '任务运行中，完成后会自动刷新结果';
    }
    if (hasChartData) {
      return '已有分析结果，可查看图表或发布到通达信';
    }
    if (!summary?.output_exists && (summary?.source_topics_count ?? 0) > 0) {
      return '已有源话题，建议先开始增量分析';
    }
    if ((summary?.source_topics_count ?? 0) === 0) {
      return '当前群话题库为空，请先采集或同步话题';
    }
    return `更新于 ${formatDateTime(summary?.updated_at)}`;
  }, [hasChartData, latestTask?.status, status?.api_key_configured, summary]);

  if (!selectedGroup) {
    return (
      <Card className="border border-gray-200 shadow-none">
        <CardHeader>
          <CardTitle>股票推荐池</CardTitle>
          <CardDescription>请先选择群组，再查看该群的推荐池分析和排序。</CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <div className="flex flex-col 2xl:flex-row gap-4">
      <div className="flex min-w-0 flex-1 flex-col gap-4">
        <SummaryCards
          apiKeyConfigured={status?.api_key_configured}
          latestTask={latestTask}
          nextStepMessage={nextStepMessage}
          storage={storage}
          summary={summary}
        />

        <AShareAnalysisResultsSection
          chart={chart}
          emptyStateHint={emptyStateHint}
          emptyStateMessage={emptyStateMessage}
          hasChartData={hasChartData}
          loadingChart={loadingChart}
          loadingStatus={loadingStatus}
          onApplyFilters={() => void handleApplyFilters()}
          onRefresh={() => void refreshAll(false, selectedGroup.group_id)}
          rankingWindows={rankingWindows}
          renderedLineSeries={renderedLineSeries}
          scopeName={scopeName}
          selectedEndDate={selectedEndDate}
          selectedStartDate={selectedStartDate}
          setSelectedEndDate={setSelectedEndDate}
          setSelectedStartDate={setSelectedStartDate}
          setTopN={setTopN}
          summary={summary}
          topN={topN}
        />
      </div>

      <AShareActionPanel
        advancedOpen={advancedOpen}
        concurrency={concurrency}
        exportingTdx={exportingTdx}
        latestExport={latestExport}
        onExportToTdx={() => void handleExportToTdx()}
        onResetOnly={() => void handleResetOnly()}
        onRunAnalysis={() => void handleRunAnalysis()}
        resetEndDate={resetEndDate}
        resetStartDate={resetStartDate}
        runEndDate={runEndDate}
        runStartDate={runStartDate}
        resetting={resetting}
        runDays={runDays}
        running={running}
        scopeName={scopeName}
        setAdvancedOpen={setAdvancedOpen}
        setConcurrency={setConcurrency}
        setResetEndDate={setResetEndDate}
        setResetStartDate={setResetStartDate}
        setRunEndDate={setRunEndDate}
        setRunDays={setRunDays}
        setRunStartDate={setRunStartDate}
        summary={summary}
      />
    </div>
  );
}
