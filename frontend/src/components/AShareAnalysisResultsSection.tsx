'use client';

import { useState } from 'react';
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { RefreshCw } from 'lucide-react';

import {
  AShareAnalysisChart,
  AShareAnalysisSeries,
  AShareAnalysisSummary,
} from '@/lib/api';
import AShareCoveragePoolTable from '@/components/AShareCoveragePoolTable';
import AShareRankingRows from '@/components/AShareRankingRows';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { DatePickerButton } from '@/components/ui/date-picker-button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

const DEFAULT_TOP_N = 12;
const MAIN_RANKING_WINDOW = 30;

interface AShareAnalysisResultsSectionProps {
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

export default function AShareAnalysisResultsSection({
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
}: AShareAnalysisResultsSectionProps) {
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

        <RankingWindowGrid chart={chart} rankingWindows={rankingWindows} />
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
