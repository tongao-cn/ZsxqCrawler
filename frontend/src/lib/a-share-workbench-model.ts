import type {
  AShareAnalysisChart,
  AShareAnalysisExportTdxPayload,
  AShareAnalysisExportTdxResponse,
  AShareAnalysisLatestTdxExport,
  AShareAnalysisResetPayload,
  AShareAnalysisRunPayload,
  AShareAnalysisSeries,
  AShareAnalysisStatus,
  AShareAnalysisStorageStatus,
  AShareAnalysisSummary,
  Task,
} from '@/lib/api';
import { formatAShareDateTime, formatAShareInputDate } from '@/lib/a-share-analysis-format';

const DEFAULT_CHART_RANGE_MONTHS = 1;

export interface AShareChartDateRange {
  endDate: string;
  startDate: string;
}

interface AShareRunPlanInput {
  concurrency: number;
  groupId?: number | string | null;
  resetEndDate: string;
  resetStartDate: string;
  runDays: number;
  runEndDate: string;
  runStartDate: string;
}

interface AShareResetPlanInput {
  groupId?: number | string | null;
  resetEndDate: string;
  resetStartDate: string;
}

interface AShareTdxExportPlanInput {
  groupId?: number | string | null;
  groupName?: string;
  selectedEndDate: string;
  selectedStartDate: string;
}

type AShareActionPlan<TPayload> =
  | { ok: true; payload: TPayload }
  | { ok: false; message: string };

interface AShareTaskResultSummary {
  days?: number;
  items_discovered?: number;
}

export interface AShareWorkbenchViewModel {
  emptyStateHint: string | null;
  emptyStateMessage: string;
  hasChartData: boolean;
  latestExport?: AShareAnalysisLatestTdxExport | null;
  latestTask?: Task | null;
  nextStepMessage: string;
  rankingWindows: number[];
  renderedLineSeries: AShareAnalysisSeries[];
  storage?: AShareAnalysisStorageStatus;
  summary?: AShareAnalysisSummary;
}

interface AShareWorkbenchViewModelInput {
  chart: AShareAnalysisChart | null;
  loadingChart: boolean;
  runDays: number;
  status: AShareAnalysisStatus | null;
}

function formatLocalDate(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function subtractMonthsClamped(date: Date, months: number) {
  const targetYear = date.getFullYear();
  const targetMonth = date.getMonth() - months;
  const lastDay = new Date(targetYear, targetMonth + 1, 0).getDate();
  return new Date(targetYear, targetMonth, Math.min(date.getDate(), lastDay));
}

function hasGroupId(groupId?: number | string | null): groupId is number | string {
  return groupId !== undefined && groupId !== null && groupId !== '';
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

function sortSeriesByTotal(series?: AShareAnalysisSeries[]) {
  return [...(series || [])].sort(compareSeriesByTotal);
}

function buildEmptyStateMessage({
  latestTask,
  loadingChart,
  runDays,
  summary,
}: {
  latestTask?: Task | null;
  loadingChart: boolean;
  runDays: number;
  summary?: AShareAnalysisSummary;
}) {
  const latestTaskResult = latestTask?.result as AShareTaskResultSummary | undefined;
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
    return `当前还没有分析结果，源话题库最新话题时间为 ${formatAShareDateTime(summary.source_latest_topic_time)}`;
  }
  return '暂无可展示的分析数据';
}

function buildEmptyStateHint(summary?: AShareAnalysisSummary) {
  const sourceTopicsCount = summary?.source_topics_count;
  const latestTopicTime = summary?.source_latest_topic_time;
  if (sourceTopicsCount === null || sourceTopicsCount === undefined) {
    return null;
  }

  const parts = [`源话题数 ${sourceTopicsCount}`];
  if (latestTopicTime) {
    parts.push(`最新话题 ${formatAShareDateTime(latestTopicTime)}`);
  }
  return parts.join('，');
}

function buildNextStepMessage({
  apiKeyConfigured,
  hasChartData,
  latestTask,
  summary,
}: {
  apiKeyConfigured?: boolean;
  hasChartData: boolean;
  latestTask?: Task | null;
  summary?: AShareAnalysisSummary;
}) {
  if (!apiKeyConfigured) {
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
  return `更新于 ${formatAShareDateTime(summary?.updated_at)}`;
}

export function getDefaultAShareChartDateRange(summary?: AShareAnalysisSummary): AShareChartDateRange {
  const availableStartDate = formatAShareInputDate(summary?.available_start_date);
  const availableEndDate = formatAShareInputDate(summary?.available_end_date);
  if (!availableEndDate) {
    return { startDate: availableStartDate, endDate: '' };
  }

  const [year, month, day] = availableEndDate.split('-').map(Number);
  if (!year || !month || !day) {
    return { startDate: availableStartDate, endDate: availableEndDate };
  }

  const defaultStartDate = formatLocalDate(
    subtractMonthsClamped(new Date(year, month - 1, day), DEFAULT_CHART_RANGE_MONTHS)
  );
  return {
    startDate: availableStartDate && availableStartDate > defaultStartDate ? availableStartDate : defaultStartDate,
    endDate: availableEndDate,
  };
}

export function planAShareAnalysisRun({
  concurrency,
  groupId,
  resetEndDate,
  resetStartDate,
  runDays,
  runEndDate,
  runStartDate,
}: AShareRunPlanInput): AShareActionPlan<AShareAnalysisRunPayload> {
  if (!hasGroupId(groupId)) {
    return { ok: false, message: '请先选择群组' };
  }
  if (runDays <= 0) {
    return { ok: false, message: '分析天数必须大于 0' };
  }

  const hasResetRange = Boolean(resetStartDate && resetEndDate);
  const hasRunRange = Boolean(runStartDate && runEndDate);
  if ((runStartDate && !runEndDate) || (!runStartDate && runEndDate)) {
    return { ok: false, message: '生成推荐池时，开始日期和结束日期需要同时填写' };
  }
  if (hasRunRange && runStartDate > runEndDate) {
    return { ok: false, message: '生成推荐池的开始日期不能晚于结束日期' };
  }
  if ((resetStartDate && !resetEndDate) || (!resetStartDate && resetEndDate)) {
    return { ok: false, message: '删除并重跑时，开始日期和结束日期需要同时填写' };
  }

  return {
    ok: true,
    payload: {
      group_id: groupId,
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
    },
  };
}

export function planAShareAnalysisReset({
  groupId,
  resetEndDate,
  resetStartDate,
}: AShareResetPlanInput): AShareActionPlan<AShareAnalysisResetPayload> {
  if (!hasGroupId(groupId)) {
    return { ok: false, message: '请先选择群组' };
  }
  if (!resetStartDate || !resetEndDate) {
    return { ok: false, message: '请先填写要删除的开始日期和结束日期' };
  }
  return {
    ok: true,
    payload: {
      group_id: groupId,
      start_date: resetStartDate,
      end_date: resetEndDate,
    },
  };
}

export function planAShareTdxExport({
  groupId,
  groupName,
  selectedEndDate,
  selectedStartDate,
}: AShareTdxExportPlanInput): AShareActionPlan<AShareAnalysisExportTdxPayload> {
  if (!hasGroupId(groupId)) {
    return { ok: false, message: '请先选择群组' };
  }
  return {
    ok: true,
    payload: {
      group_id: groupId,
      group_name: groupName,
      start_date: selectedStartDate || undefined,
      end_date: selectedEndDate || undefined,
    },
  };
}

export function summarizeAShareTdxExport(result: AShareAnalysisExportTdxResponse) {
  const blockText = result.blocks
    .map((block) => `${block.window_days}日 ${block.written_count}只`)
    .join('，');

  if (result.unresolved_companies.length > 0) {
    return `已导入通达信：${blockText}；未匹配 ${result.unresolved_companies.length} 个公司`;
  }

  return `已导入通达信：${blockText}`;
}

export function buildAShareWorkbenchViewModel({
  chart,
  loadingChart,
  runDays,
  status,
}: AShareWorkbenchViewModelInput): AShareWorkbenchViewModel {
  const summary = status?.summary;
  const latestTask = status?.latest_task;
  const latestExport = status?.latest_tdx_export;
  const storage = status?.storage;
  const hasChartData = Boolean(chart && chart.chart_data.length > 0);
  const rankingWindows = status?.defaults.ranking_windows ?? [30];
  const sortedSeries = sortSeriesByTotal(chart?.series);

  return {
    emptyStateHint: buildEmptyStateHint(summary),
    emptyStateMessage: buildEmptyStateMessage({
      latestTask,
      loadingChart,
      runDays,
      summary,
    }),
    hasChartData,
    latestExport,
    latestTask,
    nextStepMessage: buildNextStepMessage({
      apiKeyConfigured: status?.api_key_configured,
      hasChartData,
      latestTask,
      summary,
    }),
    rankingWindows,
    renderedLineSeries: [...sortedSeries].reverse(),
    storage,
    summary,
  };
}
