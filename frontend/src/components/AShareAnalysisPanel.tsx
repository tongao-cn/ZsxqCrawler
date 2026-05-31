'use client';

import { ReactNode, useMemo, useState } from 'react';
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { RefreshCw, TrendingUp, Database, Activity } from 'lucide-react';

import {
  AShareAnalysisChart,
  AShareAnalysisSeries,
  AShareAnalysisStorageStatus,
  AShareAnalysisSummary,
  Group,
  Task,
} from '@/lib/api';
import { useAShareAnalysisActions } from '@/hooks/useAShareAnalysisActions';
import { useAShareAnalysisData } from '@/hooks/useAShareAnalysisData';
import { useTaskStatus } from '@/hooks/useTaskStatus';
import AShareActionPanel from '@/components/AShareActionPanel';
import AShareCoveragePoolTable from '@/components/AShareCoveragePoolTable';
import AShareRankingRows from '@/components/AShareRankingRows';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { DatePickerButton } from '@/components/ui/date-picker-button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { toast } from 'sonner';

const DEFAULT_TOP_N = 12;
const MAIN_RANKING_WINDOW = 30;
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

interface AnalysisResultsSectionProps {
  chart: AShareAnalysisChart | null;
  emptyStateHint: string | null;
  emptyStateMessage: string;
  hasChartData: boolean;
  loadingChart: boolean;
  loadingStatus: boolean;
  onApplyFilters: () => void;
  onRefresh: () => void;
  rankingWindows: number[];
  renderedLineSeries: AShareAnalysisSeries[];
  scopeName: string;
  selectedEndDate: string;
  selectedStartDate: string;
  setSelectedEndDate: (value: string) => void;
  setSelectedStartDate: (value: string) => void;
  setTopN: (value: number) => void;
  summary?: AShareAnalysisSummary;
  topN: number;
}

function AnalysisResultsSection({
  chart,
  emptyStateHint,
  emptyStateMessage,
  hasChartData,
  loadingChart,
  loadingStatus,
  onApplyFilters,
  onRefresh,
  rankingWindows,
  renderedLineSeries,
  scopeName,
  selectedEndDate,
  selectedStartDate,
  setSelectedEndDate,
  setSelectedStartDate,
  setTopN,
  summary,
  topN,
}: AnalysisResultsSectionProps) {
  return (
    <Card className="border border-gray-200 shadow-none">
      <CardHeader>
        <div className="space-y-1">
          <CardTitle>股票推荐池结果</CardTitle>
          <CardDescription>{scopeName} 的独立分析结果，可按当前群组同步到通达信</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        <ChartFilterControls
          loadingChart={loadingChart}
          loadingStatus={loadingStatus}
          onApplyFilters={onApplyFilters}
          onRefresh={onRefresh}
          selectedEndDate={selectedEndDate}
          selectedStartDate={selectedStartDate}
          setSelectedEndDate={setSelectedEndDate}
          setSelectedStartDate={setSelectedStartDate}
          setTopN={setTopN}
          summary={summary}
          topN={topN}
        />

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
                <Tooltip itemSorter={(item) => -Number(item?.value ?? 0)} />
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

        <RankingWindowGrid
          chart={chart}
          rankingWindows={rankingWindows}
        />
      </CardContent>
    </Card>
  );
}

interface ChartFilterControlsProps {
  loadingChart: boolean;
  loadingStatus: boolean;
  onApplyFilters: () => void;
  onRefresh: () => void;
  selectedEndDate: string;
  selectedStartDate: string;
  setSelectedEndDate: (value: string) => void;
  setSelectedStartDate: (value: string) => void;
  setTopN: (value: number) => void;
  summary?: AShareAnalysisSummary;
  topN: number;
}

function ChartFilterControls({
  loadingChart,
  loadingStatus,
  onApplyFilters,
  onRefresh,
  selectedEndDate,
  selectedStartDate,
  setSelectedEndDate,
  setSelectedStartDate,
  setTopN,
  summary,
  topN,
}: ChartFilterControlsProps) {
  return (
    <div className="rounded-lg border border-gray-200 bg-gray-50 p-3">
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-[minmax(150px,1fr)_minmax(150px,1fr)_minmax(120px,0.7fr)_auto_auto] xl:items-end">
        <div className="space-y-2">
          <Label htmlFor="a-share-start-date">开始日期</Label>
          <DatePickerButton
            value={selectedStartDate}
            min={summary?.available_start_date || undefined}
            max={summary?.available_end_date || undefined}
            onChange={setSelectedStartDate}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="a-share-end-date">结束日期</Label>
          <DatePickerButton
            value={selectedEndDate}
            min={summary?.available_start_date || undefined}
            max={summary?.available_end_date || undefined}
            onChange={setSelectedEndDate}
            align="end"
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
        <Button variant="outline" onClick={onRefresh} disabled={loadingStatus || loadingChart}>
          <RefreshCw className={`h-4 w-4 ${loadingStatus || loadingChart ? 'animate-spin' : ''}`} />
          刷新
        </Button>
        <Button onClick={onApplyFilters} disabled={loadingChart}>
          {loadingChart ? '加载中' : '更新图表'}
        </Button>
      </div>
    </div>
  );
}

interface RankingWindowGridProps {
  chart: AShareAnalysisChart | null;
  rankingWindows: number[];
}

function RankingWindowGrid({
  chart,
  rankingWindows,
}: RankingWindowGridProps) {
  const [activeFilter, setActiveFilter] = useState('all');
  const windowDays = rankingWindows.includes(MAIN_RANKING_WINDOW) ? MAIN_RANKING_WINDOW : rankingWindows[0];
  const rankingRows = chart?.rankings?.[String(windowDays)] || [];
  const coverageRows = chart?.coverage_pool || [];

  return (
    <Card className="border border-green-200 bg-green-50/40 shadow-none">
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <CardTitle className="text-base">覆盖池：30日Top300 + 7/14日补充</CardTitle>
            <CardDescription>
              以30日排名分层，短周期只作为新进和活跃标签补充
            </CardDescription>
          </div>
          <Badge className="bg-green-100 text-green-800">{coverageRows.length || rankingRows.length} 只</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {coverageRows.length > 0 ? (
          <AShareCoveragePoolTable
            rows={coverageRows}
            activeFilter={activeFilter}
            onFilterChange={setActiveFilter}
          />
        ) : rankingRows.length === 0 ? (
          <div className="text-sm text-muted-foreground">暂无数据</div>
        ) : (
          <AShareRankingRows rows={rankingRows} windowDays={windowDays} />
        )}
      </CardContent>
    </Card>
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

        <AnalysisResultsSection
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
