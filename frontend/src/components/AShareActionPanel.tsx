'use client';

import { Eraser, Play, TrendingUp } from 'lucide-react';

import AShareLatestExportSummary from '@/components/AShareLatestExportSummary';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { DatePickerButton } from '@/components/ui/date-picker-button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { formatAShareInputDate } from '@/lib/a-share-analysis-format';
import type { AShareAnalysisLatestTdxExport, AShareAnalysisSummary } from '@/lib/api';

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
  resetting: boolean;
  runDays: number;
  runEndDate: string;
  running: boolean;
  runStartDate: string;
  scopeName: string;
  setAdvancedOpen: (open: boolean) => void;
  setConcurrency: (value: number) => void;
  setResetEndDate: (value: string) => void;
  setResetStartDate: (value: string) => void;
  setRunDays: (value: number) => void;
  setRunEndDate: (value: string) => void;
  setRunStartDate: (value: string) => void;
  summary?: AShareAnalysisSummary;
}

export default function AShareActionPanel({
  advancedOpen,
  concurrency,
  exportingTdx,
  latestExport,
  onExportToTdx,
  onResetOnly,
  onRunAnalysis,
  resetEndDate,
  resetStartDate,
  resetting,
  runDays,
  runEndDate,
  running,
  runStartDate,
  scopeName,
  setAdvancedOpen,
  setConcurrency,
  setResetEndDate,
  setResetStartDate,
  setRunDays,
  setRunEndDate,
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
                  min={
                    summary?.source_oldest_topic_time
                      ? formatAShareInputDate(summary.source_oldest_topic_time)
                      : undefined
                  }
                  max={
                    summary?.source_latest_topic_time
                      ? formatAShareInputDate(summary.source_latest_topic_time)
                      : undefined
                  }
                  onChange={setRunStartDate}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="a-share-run-end">结束日期</Label>
                <DatePickerButton
                  value={runEndDate}
                  min={
                    summary?.source_oldest_topic_time
                      ? formatAShareInputDate(summary.source_oldest_topic_time)
                      : undefined
                  }
                  max={
                    summary?.source_latest_topic_time
                      ? formatAShareInputDate(summary.source_latest_topic_time)
                      : undefined
                  }
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

          <AShareLatestExportSummary
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
