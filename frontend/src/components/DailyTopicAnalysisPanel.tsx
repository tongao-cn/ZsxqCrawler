'use client';

import { useCallback, useEffect, useState } from 'react';
import { CalendarDays, FileText, RefreshCw, Sparkles } from 'lucide-react';
import { toast } from 'sonner';

import { apiClient, DailyTopicReport } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ScrollArea } from '@/components/ui/scroll-area';

interface DailyTopicAnalysisPanelProps {
  groupId: number;
  onTaskCreated?: (taskId: string) => void;
}

function getTodayText() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function formatDateTime(value?: string | null) {
  if (!value) {
    return '暂无';
  }
  return new Date(value).toLocaleString('zh-CN');
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

export default function DailyTopicAnalysisPanel({
  groupId,
  onTaskCreated,
}: DailyTopicAnalysisPanelProps) {
  const [reportDate, setReportDate] = useState(getTodayText);
  const [commentsPerTopic, setCommentsPerTopic] = useState(8);
  const [submitting, setSubmitting] = useState(false);
  const [loadingReport, setLoadingReport] = useState(false);
  const [report, setReport] = useState<DailyTopicReport | null>(null);

  const loadReport = useCallback(async () => {
    try {
      setLoadingReport(true);
      const data = await apiClient.getDailyTopicReport(groupId, reportDate);
      setReport(data);
    } catch {
      setReport(null);
    } finally {
      setLoadingReport(false);
    }
  }, [groupId, reportDate]);

  useEffect(() => {
    void loadReport();
  }, [loadReport]);

  const handleRunToday = async () => {
    try {
      setSubmitting(true);
      const response = await apiClient.createDailyTopicAnalysis(groupId, {
        date: reportDate,
        commentsPerTopic,
      });
      const taskId = response.task_id;
      toast.success(`每日 AI 总结任务已创建: ${taskId}`);
      onTaskCreated?.(taskId);
    } catch (error) {
      toast.error(`创建每日 AI 总结任务失败: ${error instanceof Error ? error.message : '未知错误'}`);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex flex-col gap-4 p-1">
      <Card className="border border-gray-200 shadow-none">
        <CardHeader>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Sparkles className="h-5 w-5" />
                每日 AI 总结
              </CardTitle>
              <CardDescription>
                直接分析数据库中指定日期的话题内容，并生成可回溯的 Markdown 报告
              </CardDescription>
            </div>
            <Button onClick={handleRunToday} disabled={submitting}>
              {submitting ? (
                <RefreshCw className="h-4 w-4 animate-spin" />
              ) : (
                <Sparkles className="h-4 w-4" />
              )}
              分析当天话题
            </Button>
          </div>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="grid gap-4 md:grid-cols-3">
            <div className="flex flex-col gap-2">
              <Label htmlFor="daily-report-date">报告日期</Label>
              <Input
                id="daily-report-date"
                type="date"
                value={reportDate}
                onChange={(event) => setReportDate(event.target.value || getTodayText())}
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="daily-comments-count">每个话题纳入评论数</Label>
              <Input
                id="daily-comments-count"
                type="number"
                min={0}
                max={50}
                value={commentsPerTopic}
                onChange={(event) => {
                  const value = Number(event.target.value);
                  setCommentsPerTopic(Number.isFinite(value) ? Math.min(50, Math.max(0, value)) : 8);
                }}
              />
            </div>
            <div className="flex items-end">
              <Button
                variant="outline"
                onClick={loadReport}
                disabled={loadingReport}
                className="w-full"
              >
                <RefreshCw className={loadingReport ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} />
                刷新报告
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card className="border border-gray-200 shadow-none">
        <CardHeader>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <FileText className="h-5 w-5" />
                当前报告
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
              <ScrollArea className="h-[520px] rounded-md border border-gray-200 bg-white">
                <pre className="whitespace-pre-wrap break-words p-4 text-sm leading-6">
                  {report.summary_markdown || report.error || '报告内容为空'}
                </pre>
              </ScrollArea>
            </div>
          ) : (
            <div className="flex h-56 items-center justify-center rounded-md border border-dashed border-gray-300 text-sm text-muted-foreground">
              还没有这一天的日报，点击上方按钮创建任务
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
