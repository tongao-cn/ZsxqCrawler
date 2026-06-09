'use client';

import { CalendarDays, FileText, RefreshCw, Sparkles } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

import { DailyTopicReport } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { DatePickerButton } from '@/components/ui/date-picker-button';
import { Label } from '@/components/ui/label';
import { formatDateTime, getTodayText, normalizeReportMarkdown } from '@/components/DailyTopicAnalysisPanelUtils';

interface DailyTopicReportViewProps {
  loadingReport: boolean;
  onGenerate: () => void;
  onRefresh: () => void;
  onReportDateChange: (date: string) => void;
  report: DailyTopicReport | null;
  reportDate: string;
  submitting: boolean;
}

function getReportStatusBadge(status?: string) {
  if (status === 'completed') {
    return <Badge className="bg-green-100 text-green-800">已完成</Badge>;
  }
  if (status === 'failed') {
    return <Badge className="bg-red-100 text-red-800">失败</Badge>;
  }
  return <Badge variant="secondary">{status || '暂无报告'}</Badge>;
}

export default function DailyTopicReportView({
  loadingReport,
  onGenerate,
  onRefresh,
  onReportDateChange,
  report,
  reportDate,
  submitting,
}: DailyTopicReportViewProps) {
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px] xl:items-start">
      <Card className="border border-gray-200 shadow-none">
        <CardHeader>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <FileText className="h-5 w-5" />
                A股每日报告总结
              </CardTitle>
              <CardDescription>
                {report ? `更新时间：${formatDateTime(report.updated_at)}` : '暂无已生成报告'}
              </CardDescription>
            </div>
            {getReportStatusBadge(report?.status)}
          </div>
        </CardHeader>
        <CardContent>
          {report ? (
            <div className="flex flex-col gap-3">
              <div className="grid gap-3 md:grid-cols-3">
                <div className="rounded-md border border-gray-200 p-3">
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <CalendarDays className="h-4 w-4" />
                    日期
                  </div>
                  <div className="mt-1 font-medium">{report.report_date}</div>
                </div>
                <div className="rounded-md border border-gray-200 p-3">
                  <div className="text-sm text-muted-foreground">话题数</div>
                  <div className="mt-1 font-medium">{report.topic_count}</div>
                </div>
                <div className="rounded-md border border-gray-200 p-3">
                  <div className="text-sm text-muted-foreground">模型</div>
                  <div className="mt-1 truncate font-medium" title={report.model || ''}>
                    {report.model || '暂无'}
                  </div>
                </div>
              </div>
              {report.raw_json?.report_path && (
                <div className="text-sm text-muted-foreground">
                  文件：{report.raw_json.report_path}
                </div>
              )}
              <div className="rounded-md border border-gray-200 bg-white">
                <div className="markdown-body p-5">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {normalizeReportMarkdown(report.summary_markdown || report.error)}
                  </ReactMarkdown>
                </div>
              </div>
            </div>
          ) : (
            <div className="flex h-56 items-center justify-center rounded-md border border-dashed border-gray-300 text-sm text-muted-foreground">
              还没有这一天的日报，点击右侧按钮创建任务
            </div>
          )}
        </CardContent>
      </Card>
      <aside className="xl:sticky xl:top-4">
        <Card className="border border-gray-200 shadow-none">
          <CardHeader>
            <CardTitle className="text-base">每日报告操作</CardTitle>
            <CardDescription>选择日期，刷新或生成当天报告</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="daily-topic-report-date">报告日期</Label>
              <DatePickerButton
                value={reportDate}
                onChange={(value) => onReportDateChange(value || getTodayText())}
              />
            </div>

            <div className="grid grid-cols-2 gap-2">
              <Button variant="outline" onClick={onRefresh} disabled={loadingReport}>
                <RefreshCw className={loadingReport ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} />
                刷新
              </Button>
              <Button onClick={onGenerate} disabled={submitting}>
                {submitting ? (
                  <RefreshCw className="h-4 w-4 animate-spin" />
                ) : (
                  <Sparkles className="h-4 w-4" />
                )}
                生成
              </Button>
            </div>

            <div className="flex flex-col gap-3 border-t border-gray-200 pt-4">
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm text-muted-foreground">状态</span>
                {getReportStatusBadge(report?.status)}
              </div>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
                  <div className="text-xs text-muted-foreground">话题数</div>
                  <div className="mt-1 font-semibold">{report?.topic_count ?? '-'}</div>
                </div>
                <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
                  <div className="text-xs text-muted-foreground">日期</div>
                  <div className="mt-1 font-semibold">{report?.report_date || reportDate}</div>
                </div>
              </div>
              <div className="rounded-md bg-gray-50 p-3 text-xs leading-5 text-muted-foreground">
                模型：{report?.model || '暂无'}
                <br />
                更新时间：{formatDateTime(report?.updated_at)}
              </div>
            </div>
          </CardContent>
        </Card>
      </aside>
    </div>
  );
}
