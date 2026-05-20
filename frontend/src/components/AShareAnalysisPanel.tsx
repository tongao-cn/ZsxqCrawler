'use client';

import { ReactNode, useCallback, useEffect, useMemo, useState } from 'react';
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { ArrowDown, ArrowUp, Minus, RefreshCw, Play, Eraser, TrendingUp, Database, Activity, Upload } from 'lucide-react';

import {
  apiClient,
  AShareAnalysisChart,
  AShareAnalysisCoverageItem,
  AShareAnalysisExportTdxResponse,
  AShareAnalysisLatestTdxExport,
  AShareAnalysisRankingItem,
  AShareAnalysisSeries,
  AShareAnalysisStatus,
  AShareAnalysisStorageStatus,
  AShareAnalysisSummary,
  Group,
  Task,
} from '@/lib/api';
import { useTaskStatus } from '@/hooks/useTaskStatus';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { DatePickerButton } from '@/components/ui/date-picker-button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { toast } from 'sonner';

const DEFAULT_TOP_N = 12;
const MAIN_RANKING_WINDOW = 30;
const COVERAGE_FILTERS = [
  { key: 'all', label: '全部' },
  { key: 'core', label: '核心1-50' },
  { key: 'main', label: '主池51-100' },
  { key: 'extended', label: '扩展101-200' },
  { key: 'long_tail', label: '长尾201-300' },
  { key: 'short_active', label: '短周期补充' },
  { key: 'short_tags', label: '7/14日活跃' },
];

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

function formatInputDate(value?: string | null) {
  if (!value) {
    return '';
  }
  return value.slice(0, 10);
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
          <CoveragePoolTable
            rows={coverageRows}
            activeFilter={activeFilter}
            onFilterChange={setActiveFilter}
          />
        ) : rankingRows.length === 0 ? (
          <div className="text-sm text-muted-foreground">暂无数据</div>
        ) : (
          <RankingRows rows={rankingRows} windowDays={windowDays} />
        )}
      </CardContent>
    </Card>
  );
}

function CoveragePoolTable({
  rows,
  activeFilter,
  onFilterChange,
}: {
  rows: AShareAnalysisCoverageItem[];
  activeFilter: string;
  onFilterChange: (value: string) => void;
}) {
  const filteredRows = rows.filter((item) => {
    if (activeFilter === 'all') {
      return true;
    }
    if (activeFilter === 'short_tags') {
      return Boolean(item.rank_7 || item.rank_14);
    }
    return item.layer === activeFilter;
  });

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {COVERAGE_FILTERS.map((filter) => (
          <Button
            key={filter.key}
            type="button"
            size="sm"
            variant={activeFilter === filter.key ? 'default' : 'outline'}
            onClick={() => onFilterChange(filter.key)}
          >
            {filter.label}
          </Button>
        ))}
      </div>
      <div className="text-xs text-muted-foreground">
        当前显示 {filteredRows.length} / {rows.length} 只
      </div>
      <div className="overflow-x-auto">
        <div className="max-h-[760px] min-w-[860px] overflow-y-auto pr-1">
          <div className="grid grid-cols-[90px_minmax(0,1fr)_70px_70px_70px_92px_minmax(120px,1.2fr)] gap-3 border-b border-green-100 pb-2 text-xs font-medium text-muted-foreground">
            <span>层级</span>
            <span>股票</span>
            <span className="text-right">30日</span>
            <span className="text-right">7日</span>
            <span className="text-right">14日</span>
            <span className="text-right">变化</span>
            <span>标签</span>
          </div>
          {filteredRows.map((item) => (
            <div
              key={item.company}
              className="grid grid-cols-[90px_minmax(0,1fr)_70px_70px_70px_92px_minmax(120px,1.2fr)] items-center gap-3 border-b border-dashed py-2 text-sm last:border-b-0"
            >
              <span>
                <CoverageLayerBadge item={item} />
              </span>
              <span className="truncate font-medium" title={item.company}>
                {item.company}
              </span>
              <span className="text-right tabular-nums">{formatRank(item.rank_30)}</span>
              <span className="text-right tabular-nums">{formatRank(item.rank_7)}</span>
              <span className="text-right tabular-nums">{formatRank(item.rank_14)}</span>
              <span className="flex justify-end">
                <CoverageTrendBadge item={item} />
              </span>
              <span className="flex flex-wrap gap-1">
                {item.tags.length > 0 ? (
                  item.tags.map((tag) => (
                    <Badge key={`${item.company}-${tag}`} variant="outline" className="bg-white text-gray-700">
                      {tag}
                    </Badge>
                  ))
                ) : (
                  <span className="text-xs text-muted-foreground">-</span>
                )}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function formatRank(value?: number | null) {
  return value ? `#${value}` : '-';
}

function CoverageLayerBadge({ item }: { item: AShareAnalysisCoverageItem }) {
  const styles: Record<string, string> = {
    core: 'bg-red-100 text-red-800',
    main: 'bg-orange-100 text-orange-800',
    extended: 'bg-blue-100 text-blue-800',
    long_tail: 'bg-gray-100 text-gray-700',
    short_active: 'bg-emerald-100 text-emerald-800',
  };
  return <Badge className={styles[item.layer] || 'bg-gray-100 text-gray-700'}>{item.layer_label}</Badge>;
}

function CoverageTrendBadge({ item }: { item: AShareAnalysisCoverageItem }) {
  if (item.trend_30 === 'new') {
    return <Badge className="bg-blue-100 text-blue-800">新进</Badge>;
  }
  if (item.trend_30 === 'up') {
    return (
      <Badge className="gap-1 bg-red-100 text-red-800">
        <ArrowUp className="h-3 w-3" />
        {Math.abs(item.rank_change_30 ?? 0)}
      </Badge>
    );
  }
  if (item.trend_30 === 'down') {
    return (
      <Badge className="gap-1 bg-green-100 text-green-800">
        <ArrowDown className="h-3 w-3" />
        {Math.abs(item.rank_change_30 ?? 0)}
      </Badge>
    );
  }
  if (item.trend_30 === 'flat') {
    return (
      <Badge variant="outline" className="gap-1 bg-white text-gray-600">
        <Minus className="h-3 w-3" />
        持平
      </Badge>
    );
  }
  return <Badge className="bg-emerald-100 text-emerald-800">短期</Badge>;
}

function RankTrendBadge({ item }: { item: AShareAnalysisRankingItem }) {
  if (item.trend === 'new') {
    return <Badge className="bg-blue-100 text-blue-800">新进</Badge>;
  }
  if (item.trend === 'up') {
    return (
      <Badge className="gap-1 bg-red-100 text-red-800">
        <ArrowUp className="h-3 w-3" />
        {Math.abs(item.rank_change ?? 0)}
      </Badge>
    );
  }
  if (item.trend === 'down') {
    return (
      <Badge className="gap-1 bg-green-100 text-green-800">
        <ArrowDown className="h-3 w-3" />
        {Math.abs(item.rank_change ?? 0)}
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className="gap-1 bg-white text-gray-600">
      <Minus className="h-3 w-3" />
      持平
    </Badge>
  );
}

function RankingRows({
  rows,
  windowDays,
}: {
  rows: AShareAnalysisRankingItem[];
  windowDays: number;
}) {
  return (
    <div className="max-h-[760px] overflow-y-auto pr-1">
      <div className="grid grid-cols-[52px_minmax(0,1fr)_80px_84px] gap-3 border-b border-green-100 pb-2 text-xs font-medium text-muted-foreground">
        <span>排名</span>
        <span>股票</span>
        <span className="text-right">提及</span>
        <span className="text-right">变化</span>
      </div>
      {rows.map((item, index) => (
        <div
          key={`${windowDays}-${item.company}`}
          className="grid grid-cols-[52px_minmax(0,1fr)_80px_84px] items-center gap-3 border-b border-dashed py-2 text-sm last:border-b-0"
        >
          <span className="font-medium tabular-nums text-gray-900">{item.rank ?? index + 1}</span>
          <span className="truncate" title={item.company}>
            {item.company}
          </span>
          <span className="text-right font-medium tabular-nums">{item.count}</span>
          <span className="flex justify-end">
            <RankTrendBadge item={item} />
          </span>
        </div>
      ))}
    </div>
  );
}

interface AShareActionPanelProps {
  advancedOpen: boolean;
  concurrency: number;
  exportingTdx: boolean;
  latestExport?: AShareAnalysisLatestTdxExport | null;
  onExportToTdx: () => void;
  onResetOnly: () => void;
  onRunAnalysis: () => void;
  resetEndDate: string;
  resetStartDate: string;
  runEndDate: string;
  runStartDate: string;
  resetting: boolean;
  runDays: number;
  running: boolean;
  scopeName: string;
  setAdvancedOpen: (open: boolean) => void;
  setConcurrency: (value: number) => void;
  setResetEndDate: (value: string) => void;
  setResetStartDate: (value: string) => void;
  setRunEndDate: (value: string) => void;
  setRunDays: (value: number) => void;
  setRunStartDate: (value: string) => void;
  summary?: AShareAnalysisSummary;
}

function AShareActionPanel({
  advancedOpen,
  concurrency,
  exportingTdx,
  latestExport,
  onExportToTdx,
  onResetOnly,
  onRunAnalysis,
  resetEndDate,
  resetStartDate,
  runEndDate,
  runStartDate,
  resetting,
  runDays,
  running,
  scopeName,
  setAdvancedOpen,
  setConcurrency,
  setResetEndDate,
  setResetStartDate,
  setRunEndDate,
  setRunDays,
  setRunStartDate,
  summary,
}: AShareActionPanelProps) {
  return (
    <aside className="w-full 2xl:w-80 flex-shrink-0 2xl:sticky 2xl:top-0 h-fit 2xl:max-h-screen">
      <Card className="border border-gray-200 shadow-none">
        <CardContent className="flex flex-col gap-4 p-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2 text-sm font-medium text-gray-900">
              <TrendingUp className="h-4 w-4" />
              股票推荐池策略栏
            </div>
            <p className="text-xs text-muted-foreground">
              生成推荐池、发布到通达信和维护数据。
            </p>
          </div>

          <div className="space-y-3">
            <div className="text-sm font-medium text-gray-900">生成结果</div>
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-2">
                <Label htmlFor="a-share-run-start">开始日期</Label>
                <DatePickerButton
                  value={runStartDate}
                  min={summary?.source_oldest_topic_time ? formatInputDate(summary.source_oldest_topic_time) : undefined}
                  max={summary?.source_latest_topic_time ? formatInputDate(summary.source_latest_topic_time) : undefined}
                  onChange={setRunStartDate}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="a-share-run-end">结束日期</Label>
                <DatePickerButton
                  value={runEndDate}
                  min={summary?.source_oldest_topic_time ? formatInputDate(summary.source_oldest_topic_time) : undefined}
                  max={summary?.source_latest_topic_time ? formatInputDate(summary.source_latest_topic_time) : undefined}
                  onChange={setRunEndDate}
                  align="end"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-2">
                <Label htmlFor="a-share-run-days">扫描</Label>
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
                <Label htmlFor="a-share-concurrency">并发</Label>
                <Input
                  id="a-share-concurrency"
                  type="number"
                  min={1}
                  max={128}
                  value={concurrency}
                  onChange={(e) => setConcurrency(Number(e.target.value) || 1)}
                />
              </div>
            </div>
            <Button className="w-full bg-green-600 hover:bg-green-700" onClick={onRunAnalysis} disabled={running}>
              <Play className="h-4 w-4" />
              {running ? '创建任务中...' : '生成/更新推荐池'}
            </Button>
            <div className="rounded-lg border border-gray-200 bg-gray-50 p-3 text-xs text-muted-foreground">
              当前只处理 {scopeName} 的数据；填写开始和结束日期时按日期区间运行，否则按最近 N 天运行。
            </div>
          </div>

          <LatestExportSummary
            exportingTdx={exportingTdx}
            latestExport={latestExport}
            onExportToTdx={onExportToTdx}
          />

          <div className="space-y-3 border-t border-gray-200 pt-4">
            <button
              type="button"
              className="flex w-full items-center justify-between text-sm font-medium text-gray-900"
              onClick={() => setAdvancedOpen(!advancedOpen)}
              aria-expanded={advancedOpen}
            >
              <span>高级维护</span>
              <span className="text-xs text-muted-foreground">{advancedOpen ? '收起' : '展开'}</span>
            </button>
            {advancedOpen ? (
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-2">
                  <div className="space-y-2">
                    <Label htmlFor="a-share-reset-start">删除开始</Label>
                    <DatePickerButton
                      value={resetStartDate}
                      min={summary?.available_start_date || undefined}
                      max={summary?.available_end_date || undefined}
                      onChange={setResetStartDate}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="a-share-reset-end">删除结束</Label>
                    <DatePickerButton
                      value={resetEndDate}
                      min={summary?.available_start_date || undefined}
                      max={summary?.available_end_date || undefined}
                      onChange={setResetEndDate}
                      align="end"
                    />
                  </div>
                </div>
                <Button variant="outline" className="w-full" onClick={onResetOnly} disabled={resetting}>
                  <Eraser className="h-4 w-4" />
                  {resetting ? '删除中...' : '仅删除区间数据'}
                </Button>
              </div>
            ) : (
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
                删除区间数据默认折叠，避免误触。
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    </aside>
  );
}

interface LatestExportSummaryProps {
  exportingTdx: boolean;
  latestExport?: AShareAnalysisLatestTdxExport | null;
  onExportToTdx: () => void;
}

function LatestExportSummary({
  exportingTdx,
  latestExport,
  onExportToTdx,
}: LatestExportSummaryProps) {
  return (
    <div className="space-y-3 border-t border-gray-200 pt-4">
      <div className="text-sm font-medium text-gray-900">发布到通达信</div>
      <Button variant="outline" className="w-full" onClick={onExportToTdx} disabled={exportingTdx}>
        <Upload className={`h-4 w-4 ${exportingTdx ? 'animate-pulse' : ''}`} />
        {exportingTdx ? '导入中...' : '导入30日Top100'}
      </Button>
      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="rounded border border-gray-200 bg-white p-2">
          <div className="text-muted-foreground">写入总数</div>
          <div className="font-semibold">{latestExport?.total_written ?? 0}</div>
        </div>
        <div className="rounded border border-gray-200 bg-white p-2">
          <div className="text-muted-foreground">未匹配</div>
          <div className="font-semibold">{latestExport?.unresolved_count ?? 0}</div>
        </div>
      </div>
      {latestExport ? (
        <details className="rounded-lg border border-gray-200 bg-gray-50 p-3 text-xs">
          <summary className="cursor-pointer font-medium text-gray-900">最近导入记录</summary>
          <div className="mt-3 space-y-2 text-muted-foreground">
            <div>导入时间：{formatDateTime(latestExport.exported_at)}</div>
            <div>范围：{formatDateRange(latestExport.start_date, latestExport.end_date)}</div>
            <div>股票主数据：{latestExport.stock_basic_source || '未知'}</div>
            <div className="grid grid-cols-1 gap-2">
              {latestExport.blocks.map((block) => (
                <div key={`latest-export-${block.window_days}`} className="rounded border border-gray-200 bg-white p-2">
                  <div className="font-medium text-gray-900">{block.block_name}</div>
                  <div>写入 {block.written_count}，跳过 {block.skipped_count}</div>
                </div>
              ))}
            </div>
            {latestExport.unresolved_companies.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {latestExport.unresolved_companies.slice(0, 8).map((company) => (
                  <Badge key={company} variant="outline" className="bg-white">
                    {company}
                  </Badge>
                ))}
                {latestExport.unresolved_companies.length > 8 ? (
                  <Badge variant="outline" className="bg-white">
                    +{latestExport.unresolved_companies.length - 8}
                  </Badge>
                ) : null}
              </div>
            ) : null}
          </div>
        </details>
      ) : (
        <div className="rounded-lg border border-gray-200 bg-gray-50 p-3 text-xs text-muted-foreground">
          还没有导入记录。
        </div>
      )}
    </div>
  );
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
  const [concurrency, setConcurrency] = useState(10);
  const [runStartDate, setRunStartDate] = useState('');
  const [runEndDate, setRunEndDate] = useState('');
  const [resetStartDate, setResetStartDate] = useState('');
  const [resetEndDate, setResetEndDate] = useState('');
  const [initialized, setInitialized] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [activeRunTaskId, setActiveRunTaskId] = useState<string | null>(null);

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
        setConcurrency(statusData.defaults.concurrency);
        setSelectedStartDate(statusData.summary.available_start_date || '');
        setSelectedEndDate(statusData.summary.available_end_date || '');
        setRunStartDate('');
        setRunEndDate('');
        setResetStartDate('');
        setResetEndDate('');
        setInitialized(true);
      } catch (error) {
        if (!cancelled) {
          toast.error(`加载股票推荐池状态失败: ${error instanceof Error ? error.message : '未知错误'}`);
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
          toast.error(`加载股票推荐池图表失败: ${error instanceof Error ? error.message : '未知错误'}`);
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
          setConcurrency(data.defaults.concurrency);
          setSelectedStartDate(data.summary.available_start_date || '');
          setSelectedEndDate(data.summary.available_end_date || '');
          setRunStartDate('');
          setRunEndDate('');
          setResetStartDate('');
          setResetEndDate('');
          setInitialized(true);
        }
      } catch (error) {
        toast.error(`加载股票推荐池状态失败: ${error instanceof Error ? error.message : '未知错误'}`);
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
        toast.error(`加载股票推荐池图表失败: ${error instanceof Error ? error.message : '未知错误'}`);
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
        concurrency: concurrency,
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
      toast.success('股票推荐池任务已创建，结果会在完成后自动刷新');
      const taskId = (response as { task_id?: string })?.task_id;
      if (taskId) {
        setActiveRunTaskId(taskId);
        onTaskCreated?.(taskId);
      }
      await loadStatus(false, selectedGroup.group_id);
    } catch (error) {
      toast.error(`创建股票推荐池任务失败: ${error instanceof Error ? error.message : '未知错误'}`);
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
