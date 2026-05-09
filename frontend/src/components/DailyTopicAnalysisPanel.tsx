'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { CalendarDays, FileText, Plus, RefreshCw, Sparkles, TrendingUp } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { toast } from 'sonner';

import { apiClient, DailyStockConceptResponse, DailyTopicReport } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';

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

function isAbortError(error: unknown) {
  return error instanceof DOMException && error.name === 'AbortError';
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

function normalizeReportMarkdown(value?: string | null) {
  const content = value || '报告内容为空';
  const headingMap: Record<string, string> = {
    每日话题分析报告: '# 每日话题分析报告',
    一句话结论: '## 一句话结论',
    今日核心洞察: '## 今日核心洞察',
    热点话题: '## 热点话题',
    '热点话题 Top 5': '## 热点话题 Top 5',
    高价值观点与问答: '## 高价值观点与问答',
    需要跟进的机会或风险: '## 需要跟进的机会或风险',
    明日关注点: '## 明日关注点',
    话题索引: '## 话题索引',
  };

  return content
    .split('\n')
    .map((line) => {
      const trimmed = line.trim();
      if (trimmed.startsWith('#')) {
        return line;
      }
      return headingMap[trimmed] || line;
    })
    .join('\n');
}

interface ConceptStat {
  concept: string;
  stockNames: string[];
  stockCount: number;
}

const DEFAULT_VISIBLE_CONCEPT_COUNT = 20;

export default function DailyTopicAnalysisPanel({
  groupId,
  onTaskCreated,
}: DailyTopicAnalysisPanelProps) {
  const [reportDate, setReportDate] = useState(getTodayText);
  const [submitting, setSubmitting] = useState(false);
  const [extractingStocks, setExtractingStocks] = useState(false);
  const [loadingReport, setLoadingReport] = useState(false);
  const [loadingStockConcepts, setLoadingStockConcepts] = useState(false);
  const [report, setReport] = useState<DailyTopicReport | null>(null);
  const [stockConcepts, setStockConcepts] = useState<DailyStockConceptResponse | null>(null);
  const [expandedConcepts, setExpandedConcepts] = useState<Set<string>>(new Set());
  const [showAllConcepts, setShowAllConcepts] = useState(false);

  const conceptStats = useMemo<ConceptStat[]>(() => {
    const conceptMap = new Map<string, Set<string>>();
    for (const stock of stockConcepts?.stocks || []) {
      const stockName = stock.stock_name?.trim();
      if (!stockName) {
        continue;
      }
      for (const rawConcept of stock.concepts || []) {
        const concept = rawConcept.trim();
        if (!concept) {
          continue;
        }
        if (!conceptMap.has(concept)) {
          conceptMap.set(concept, new Set());
        }
        conceptMap.get(concept)?.add(stockName);
      }
    }

    return Array.from(conceptMap.entries())
      .map(([concept, stockSet]) => ({
        concept,
        stockNames: Array.from(stockSet).sort((a, b) => a.localeCompare(b, 'zh-CN')),
        stockCount: stockSet.size,
      }))
      .sort((a, b) => {
        if (b.stockCount !== a.stockCount) {
          return b.stockCount - a.stockCount;
        }
        return a.concept.localeCompare(b.concept, 'zh-CN');
      });
  }, [stockConcepts]);

  const visibleConceptStats = showAllConcepts ? conceptStats : conceptStats.slice(0, DEFAULT_VISIBLE_CONCEPT_COUNT);

  const loadReport = useCallback(async (signal?: AbortSignal) => {
    try {
      setLoadingReport(true);
      const data = await apiClient.getDailyTopicReport(groupId, reportDate, { signal });
      setReport(data);
    } catch (error) {
      if (isAbortError(error)) {
        return;
      }
      setReport(null);
    } finally {
      if (!signal?.aborted) {
        setLoadingReport(false);
      }
    }
  }, [groupId, reportDate]);

  useEffect(() => {
    const controller = new AbortController();
    void loadReport(controller.signal);
    return () => controller.abort();
  }, [loadReport]);

  const loadStockConcepts = useCallback(async (signal?: AbortSignal) => {
    try {
      setLoadingStockConcepts(true);
      const data = await apiClient.getDailyStockConcepts(groupId, reportDate, { signal });
      setStockConcepts(data);
    } catch (error) {
      if (isAbortError(error)) {
        return;
      }
      setStockConcepts(null);
    } finally {
      if (!signal?.aborted) {
        setLoadingStockConcepts(false);
      }
    }
  }, [groupId, reportDate]);

  useEffect(() => {
    const controller = new AbortController();
    void loadStockConcepts(controller.signal);
    return () => controller.abort();
  }, [loadStockConcepts]);

  const handleRunToday = async () => {
    try {
      setSubmitting(true);
      const response = await apiClient.createDailyTopicAnalysis(groupId, {
        date: reportDate,
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

  const handleExtractStockConcepts = async () => {
    try {
      setExtractingStocks(true);
      const response = await apiClient.createDailyStockConcepts(groupId, {
        date: reportDate,
      });
      toast.success(`股票概念提取任务已创建: ${response.task_id}`);
      onTaskCreated?.(response.task_id);
    } catch (error) {
      toast.error(`创建股票概念提取任务失败: ${error instanceof Error ? error.message : '未知错误'}`);
    } finally {
      setExtractingStocks(false);
    }
  };

  const toggleConcept = (concept: string) => {
    setExpandedConcepts((previous) => {
      const next = new Set(previous);
      if (next.has(concept)) {
        next.delete(concept);
      } else {
        next.add(concept);
      }
      return next;
    });
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
          <div className="grid gap-4 md:grid-cols-2">
            <div className="flex flex-col gap-2">
              <Label htmlFor="daily-report-date">报告日期</Label>
              <Input
                id="daily-report-date"
                type="date"
                value={reportDate}
                onChange={(event) => setReportDate(event.target.value || getTodayText())}
              />
            </div>
            <div className="flex items-end">
              <Button
                variant="outline"
                onClick={() => void loadReport()}
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
                <TrendingUp className="h-5 w-5" />
                股票概念
              </CardTitle>
              <CardDescription>
                提取当天话题中提到的 A 股股票、关联概念和来源话题
              </CardDescription>
            </div>
            <div className="flex flex-col gap-2 sm:flex-row">
              <Button variant="outline" onClick={() => void loadStockConcepts()} disabled={loadingStockConcepts}>
                <RefreshCw className={loadingStockConcepts ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} />
                刷新结果
              </Button>
              <Button onClick={handleExtractStockConcepts} disabled={extractingStocks}>
                {extractingStocks ? (
                  <RefreshCw className="h-4 w-4 animate-spin" />
                ) : (
                  <TrendingUp className="h-4 w-4" />
                )}
                提取当天股票概念
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {stockConcepts && stockConcepts.stocks.length > 0 ? (
            <div className="flex flex-col gap-4">
              <div className="rounded-md border border-gray-200 p-3">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <div>
                    <div className="text-sm font-medium">当天概念频率</div>
                    <div className="text-xs text-muted-foreground">
                      按包含股票数量排序，共 {conceptStats.length} 个概念
                    </div>
                  </div>
                </div>
                {conceptStats.length > 0 ? (
                  <div className="flex flex-col gap-3">
                    <div className="flex flex-wrap gap-2">
                      {visibleConceptStats.map((item) => {
                      const expanded = expandedConcepts.has(item.concept);
                      return (
                        <button
                          key={item.concept}
                          type="button"
                          onClick={() => toggleConcept(item.concept)}
                          className="inline-flex max-w-full items-center gap-2 rounded-md border border-gray-200 bg-white px-2.5 py-1.5 text-sm transition-colors hover:bg-gray-50"
                          title={`${item.concept}: ${item.stockCount} 只股票`}
                        >
                          <span className="truncate">{item.concept}</span>
                          <Badge variant="secondary">{item.stockCount}</Badge>
                          <Plus className={expanded ? 'h-3.5 w-3.5 rotate-45 transition-transform' : 'h-3.5 w-3.5 transition-transform'} />
                        </button>
                      );
                    })}
                    </div>
                    {conceptStats.length > DEFAULT_VISIBLE_CONCEPT_COUNT && (
                      <Button
                        variant="outline"
                        size="sm"
                        className="w-fit"
                        onClick={() => setShowAllConcepts((value) => !value)}
                      >
                        {showAllConcepts ? '收起概念' : `展开全部 ${conceptStats.length} 个概念`}
                      </Button>
                    )}
                    {visibleConceptStats.some((item) => expandedConcepts.has(item.concept)) && (
                      <div className="rounded-md bg-gray-50 p-3">
                        {visibleConceptStats
                          .filter((item) => expandedConcepts.has(item.concept))
                          .map((item) => (
                            <div key={item.concept} className="flex flex-col gap-2 py-1">
                              <div className="text-sm font-medium">
                                {item.concept}：{item.stockCount} 只股票
                              </div>
                              <div className="flex flex-wrap gap-1">
                                {item.stockNames.map((stockName) => (
                                  <Badge key={stockName} variant="outline">
                                    {stockName}
                                  </Badge>
                                ))}
                              </div>
                            </div>
                          ))}
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="text-sm text-muted-foreground">暂无概念统计</div>
                )}
              </div>

              <ScrollArea className="h-[420px] rounded-md border border-gray-200">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>股票</TableHead>
                      <TableHead>代码</TableHead>
                      <TableHead>概念</TableHead>
                      <TableHead>来源话题</TableHead>
                      <TableHead>置信度</TableHead>
                      <TableHead>理由</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {stockConcepts.stocks.map((stock) => (
                      <TableRow key={`${stock.stock_name}-${stock.stock_code || 'unknown'}`}>
                        <TableCell className="font-medium">{stock.stock_name}</TableCell>
                        <TableCell>
                          {stock.stock_code ? `${stock.stock_code}${stock.market ? `.${stock.market}` : ''}` : '未匹配'}
                        </TableCell>
                        <TableCell className="max-w-xs whitespace-normal">
                          <div className="flex flex-wrap gap-1">
                            {stock.concepts.map((concept) => (
                              <Badge key={concept} variant="secondary">
                                {concept}
                              </Badge>
                            ))}
                          </div>
                        </TableCell>
                        <TableCell className="max-w-[160px] truncate" title={stock.topic_ids.join(', ')}>
                          {stock.topic_ids.join(', ') || '-'}
                        </TableCell>
                        <TableCell>{Math.round((stock.confidence || 0) * 100)}%</TableCell>
                        <TableCell className="max-w-md whitespace-normal text-muted-foreground">
                          {stock.reason || '-'}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </ScrollArea>
            </div>
          ) : (
            <div className="flex h-40 items-center justify-center rounded-md border border-dashed border-gray-300 text-sm text-muted-foreground">
              还没有股票概念结果，点击上方按钮提取
            </div>
          )}
          {stockConcepts?.updated_at && (
            <div className="mt-3 text-xs text-muted-foreground">
              更新时间：{formatDateTime(stockConcepts.updated_at)}
            </div>
          )}
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
              还没有这一天的日报，点击上方按钮创建任务
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
