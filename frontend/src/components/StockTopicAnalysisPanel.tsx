'use client';

import { useCallback, useState } from 'react';
import { BarChart3, RefreshCw, Search, Sparkles } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { toast } from 'sonner';

import { apiClient, StockTopicAnalysisResponse } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { useTaskStatus } from '@/hooks/useTaskStatus';

interface StockTopicAnalysisPanelProps {
  groupId: number;
  onTaskCreated?: (taskId: string) => void;
}

function formatDateTime(value?: string | null) {
  if (!value) {
    return '-';
  }
  return new Date(value).toLocaleString('zh-CN');
}

function formatStockCode(result: StockTopicAnalysisResponse | null) {
  if (!result?.stock_code) {
    return '未匹配';
  }
  return `${result.stock_code}${result.market ? `.${result.market}` : ''}`;
}

function mergeSearchAndLatestResult(
  searchResult: StockTopicAnalysisResponse,
  latestResult: StockTopicAnalysisResponse | null,
): StockTopicAnalysisResponse {
  if (!latestResult?.summary_markdown) {
    return searchResult;
  }
  return {
    ...searchResult,
    concepts: latestResult.concepts.length > 0 ? latestResult.concepts : searchResult.concepts,
    recommendation_count: latestResult.recommendation_count || searchResult.recommendation_count,
    summary_markdown: latestResult.summary_markdown,
    model: latestResult.model,
    status: latestResult.status,
    error: latestResult.error,
    created_at: latestResult.created_at,
    updated_at: latestResult.updated_at,
  };
}

export default function StockTopicAnalysisPanel({ groupId, onTaskCreated }: StockTopicAnalysisPanelProps) {
  const [stockName, setStockName] = useState('');
  const [result, setResult] = useState<StockTopicAnalysisResponse | null>(null);
  const [searching, setSearching] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [activeAnalysis, setActiveAnalysis] = useState<{ taskId: string; stockName: string } | null>(null);

  const normalizedStockName = stockName.trim();

  const refreshSavedAnalysis = useCallback(async (targetStockName: string) => {
    const searchResult = await apiClient.searchStockTopics(groupId, targetStockName);
    const latest = await apiClient.getLatestStockTopicAnalysis(groupId, targetStockName);
    setResult(mergeSearchAndLatestResult(searchResult, latest));
  }, [groupId]);

  const handleSearch = useCallback(async () => {
    if (!normalizedStockName) {
      toast.error('请输入股票名称');
      return;
    }
    try {
      setSearching(true);
      const data = await apiClient.searchStockTopics(groupId, normalizedStockName);
      let latest: StockTopicAnalysisResponse | null = null;
      try {
        latest = await apiClient.getLatestStockTopicAnalysis(groupId, normalizedStockName);
      } catch {
        latest = null;
      }
      setResult(mergeSearchAndLatestResult(data, latest));
    } catch (error) {
      toast.error(`搜索失败: ${error instanceof Error ? error.message : '未知错误'}`);
    } finally {
      setSearching(false);
    }
  }, [groupId, normalizedStockName]);

  const handleAnalyze = useCallback(async () => {
    if (!normalizedStockName) {
      toast.error('请输入股票名称');
      return;
    }
    try {
      setAnalyzing(true);
      const response = await apiClient.analyzeStockTopics(groupId, normalizedStockName);
      setActiveAnalysis({ taskId: response.task_id, stockName: normalizedStockName });
      onTaskCreated?.(response.task_id);
      toast.success(`个股话题分析任务已创建: ${response.task_id}`);
    } catch (error) {
      toast.error(`创建分析任务失败: ${error instanceof Error ? error.message : '未知错误'}`);
      } finally {
      setAnalyzing(false);
    }
  }, [groupId, normalizedStockName, onTaskCreated]);

  useTaskStatus(activeAnalysis?.taskId, {
    enabled: Boolean(activeAnalysis),
    onTerminal: async (task) => {
      if (!activeAnalysis) {
        return;
      }
      if (task.status === 'completed') {
        await refreshSavedAnalysis(activeAnalysis.stockName);
        toast.success('个股话题分析已保存');
      } else if (task.status === 'failed' || task.status === 'cancelled') {
        toast.error(task.message || '个股话题分析任务未完成');
      }
      setActiveAnalysis(null);
    },
  });

  return (
    <div className="grid gap-4 p-1 xl:grid-cols-[minmax(0,1fr)_320px] xl:items-start">
      <Card className="border border-gray-200 shadow-none">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <BarChart3 className="h-5 w-5" />
            股票话题分析
          </CardTitle>
          <CardDescription>
            输入股票名称，查看群组话题、概念、推荐次数，并基于命中话题生成总结
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-col gap-2 sm:flex-row">
            <Input
              value={stockName}
              onChange={(event) => setStockName(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  void handleSearch();
                }
              }}
              placeholder="例如：宁德时代"
            />
            <div className="grid grid-cols-2 gap-2 sm:flex">
              <Button variant="outline" onClick={() => void handleSearch()} disabled={searching || analyzing}>
                {searching ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
                搜索
              </Button>
              <Button onClick={() => void handleAnalyze()} disabled={searching || analyzing || Boolean(activeAnalysis)}>
                {analyzing ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                {activeAnalysis ? '分析中' : '一键分析'}
              </Button>
            </div>
          </div>

          {result ? (
            <div className="flex flex-col gap-4">
              <div className="grid gap-3 md:grid-cols-4">
                <div className="rounded-md border border-gray-200 p-3">
                  <div className="text-sm text-muted-foreground">股票</div>
                  <div className="mt-1 font-medium">{result.stock_name || normalizedStockName}</div>
                </div>
                <div className="rounded-md border border-gray-200 p-3">
                  <div className="text-sm text-muted-foreground">代码</div>
                  <div className="mt-1 font-medium">{formatStockCode(result)}</div>
                </div>
                <div className="rounded-md border border-gray-200 p-3">
                  <div className="text-sm text-muted-foreground">话题</div>
                  <div className="mt-1 font-medium">{result.topic_count}</div>
                </div>
                <div className="rounded-md border border-gray-200 p-3">
                  <div className="text-sm text-muted-foreground">推荐次数</div>
                  <div className="mt-1 font-medium">{result.recommendation_count}</div>
                </div>
              </div>

              <div className="flex flex-wrap gap-1">
                {result.concepts.length > 0 ? (
                  result.concepts.map((concept) => (
                    <Badge key={concept} variant="secondary">
                      {concept}
                    </Badge>
                  ))
                ) : (
                  <span className="text-sm text-muted-foreground">暂无概念</span>
                )}
              </div>

              <div className="rounded-md border border-gray-200">
                <ScrollArea className="h-[360px]">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>话题</TableHead>
                        <TableHead>概念</TableHead>
                        <TableHead>推荐</TableHead>
                        <TableHead>互动</TableHead>
                        <TableHead>摘要</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {result.topics.length > 0 ? (
                        result.topics.map((topic) => (
                          <TableRow key={topic.topic_id}>
                            <TableCell className="min-w-[170px] whitespace-normal">
                              <div className="font-medium">{topic.title || topic.topic_id}</div>
                              <div className="text-xs text-muted-foreground">
                                {formatDateTime(topic.create_time)}
                              </div>
                            </TableCell>
                            <TableCell className="min-w-[180px] whitespace-normal">
                              <div className="flex flex-wrap gap-1">
                                {topic.concepts.length > 0 ? (
                                  topic.concepts.map((concept) => (
                                    <Badge key={concept} variant="outline">
                                      {concept}
                                    </Badge>
                                  ))
                                ) : (
                                  <span className="text-muted-foreground">-</span>
                                )}
                              </div>
                            </TableCell>
                            <TableCell>{topic.recommendation_count}</TableCell>
                            <TableCell className="min-w-[120px] text-sm text-muted-foreground">
                              阅读 {topic.reading_count}
                              <br />
                              赞 {topic.likes_count} / 评 {topic.comments_count}
                            </TableCell>
                            <TableCell className="min-w-[320px] whitespace-normal text-muted-foreground">
                              {topic.content_preview || topic.reasons.join('；') || '-'}
                            </TableCell>
                          </TableRow>
                        ))
                      ) : (
                        <TableRow>
                          <TableCell colSpan={5} className="h-32 text-center text-muted-foreground">
                            未找到相关话题
                          </TableCell>
                        </TableRow>
                      )}
                    </TableBody>
                  </Table>
                </ScrollArea>
              </div>

              {result.summary_markdown && (
                <div className="rounded-md border border-gray-200 bg-white">
                  {result.updated_at && (
                    <div className="border-b border-gray-200 px-5 py-2 text-xs text-muted-foreground">
                      保存时间：{formatDateTime(result.updated_at)}
                    </div>
                  )}
                  <div className="markdown-body p-5">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{result.summary_markdown}</ReactMarkdown>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="flex h-56 items-center justify-center rounded-md border border-dashed border-gray-300 text-sm text-muted-foreground">
              输入股票名称后开始搜索
            </div>
          )}
        </CardContent>
      </Card>

      <aside className="xl:sticky xl:top-4">
        <Card className="border border-gray-200 shadow-none">
          <CardHeader>
            <CardTitle className="text-base">当前检索</CardTitle>
            <CardDescription>只读取当前群组已经入库的话题和抽取明细</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3 text-sm">
            <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
              <div className="text-xs text-muted-foreground">关键词</div>
              <div className="mt-1 font-medium">{normalizedStockName || '-'}</div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
                <div className="text-xs text-muted-foreground">话题</div>
                <div className="mt-1 font-semibold">{result?.topic_count ?? '-'}</div>
              </div>
              <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
                <div className="text-xs text-muted-foreground">概念</div>
                <div className="mt-1 font-semibold">{result?.concepts.length ?? '-'}</div>
              </div>
            </div>
            <div className="rounded-md bg-gray-50 p-3 text-xs leading-5 text-muted-foreground">
              一键分析会创建后台任务，完成后保存最新分析结果，并把摘要回填到当前页面。
              {result?.model ? (
                <>
                  <br />
                  模型：{result.model}
                </>
              ) : null}
            </div>
          </CardContent>
        </Card>
      </aside>
    </div>
  );
}
