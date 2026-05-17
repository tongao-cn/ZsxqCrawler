'use client';

import { ChangeEvent, ClipboardEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Eye, ImagePlus, RefreshCw, Search, Sparkles } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { toast } from 'sonner';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Textarea } from '@/components/ui/textarea';
import { apiClient, StockTopicAnalysisResponse } from '@/lib/api';
import { useTaskStatus } from '@/hooks/useTaskStatus';

const MAX_STOCK_COUNT = 20;
const MAX_IMAGE_BYTES = 4 * 1024 * 1024;

interface StockTopicAnalysisPanelProps {
  groupId: number | string;
  onTaskCreated?: (taskId: string) => void;
}

interface ActiveBatchAnalysis {
  taskId: string;
  stockNames: string[];
}

interface StockTopicPanelCache {
  stockInput: string;
  results: StockTopicAnalysisResponse[];
}

function parseStockNames(value: string) {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const item of value.split(/[\s,，、;；]+/)) {
    const text = item.trim();
    if (!text || seen.has(text)) {
      continue;
    }
    seen.add(text);
    result.push(text);
    if (result.length >= MAX_STOCK_COUNT) {
      break;
    }
  }
  return result;
}

function mergeStockInput(currentInput: string, extractedNames: string[]) {
  return parseStockNames([currentInput, extractedNames.join('、')].join('\n')).join('、');
}

function readFileAsDataUrl(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ''));
    reader.onerror = () => reject(new Error('读取图片失败'));
    reader.readAsDataURL(file);
  });
}

function formatDateTime(value?: string | null) {
  if (!value) {
    return '-';
  }
  try {
    return new Date(value).toLocaleString('zh-CN');
  } catch {
    return value;
  }
}

function formatStockCode(result: StockTopicAnalysisResponse) {
  if (!result.stock_code) {
    return '-';
  }
  return result.market ? `${result.market}.${result.stock_code}` : result.stock_code;
}

function getStatusLabel(result: StockTopicAnalysisResponse) {
  if ((result.new_topic_count ?? 0) > 0 && result.summary_markdown) {
    return `有 ${result.new_topic_count} 条待处理话题`;
  }
  if (result.status === 'failed') {
    return '失败';
  }
  if (result.status === 'missing') {
    return result.topic_count > 0 ? '待分析' : '未保存';
  }
  if (result.summary_markdown) {
    return '已处理';
  }
  if (result.status === 'completed' && result.topic_count <= 0) {
    return '无话题';
  }
  if (result.topic_count > 0) {
    return '待分析';
  }
  return '无话题';
}

function getStatusBadge(result: StockTopicAnalysisResponse) {
  const label = getStatusLabel(result);
  if (label.startsWith('有 ')) {
    return <Badge className="bg-blue-100 text-blue-800">{label}</Badge>;
  }
  switch (label) {
    case '已处理':
      return <Badge className="bg-green-100 text-green-800">已处理</Badge>;
    case '待分析':
      return <Badge className="bg-amber-100 text-amber-800">待分析</Badge>;
    case '失败':
      return <Badge className="bg-red-100 text-red-800">失败</Badge>;
    case '无话题':
      return <Badge className="bg-gray-100 text-gray-700">无话题</Badge>;
    default:
      return <Badge variant="secondary">{label}</Badge>;
  }
}

function mergeSearchAndLatestResult(
  searchResult: StockTopicAnalysisResponse,
  latestResult: StockTopicAnalysisResponse | null,
): StockTopicAnalysisResponse {
  const latestTopicIds = new Set(
    (latestResult?.processed_topic_ids || latestResult?.analyzed_topic_ids || latestResult?.topics.map((topic) => topic.topic_id) || []).map(String),
  );
  const newTopicCount = searchResult.topics.filter((topic) => !latestTopicIds.has(String(topic.topic_id))).length;
  if (!latestResult || latestResult.status === 'missing') {
    return {
      ...searchResult,
      processed_topic_ids: [],
      analyzed_topic_ids: [],
      new_topic_count: searchResult.topic_count,
      analysis_mode: 'initialize',
    };
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
    processed_topic_ids: Array.from(latestTopicIds),
    analyzed_topic_ids: Array.from(latestTopicIds),
    new_topic_count: newTopicCount,
    analysis_mode: newTopicCount > 0 ? 'incremental' : 'up_to_date',
  };
}

function getAnalyzeButtonLabel(results: StockTopicAnalysisResponse[], parsedStockCount: number, active: boolean, creating: boolean) {
  if (active) {
    return '分析中';
  }
  if (creating) {
    return '创建中...';
  }
  if (results.length === 0 || results.length !== parsedStockCount) {
    return '初始化/查询后处理';
  }
  const missingCount = results.filter((result) => !result.summary_markdown && result.topic_count > 0).length;
  const incrementalCount = results.filter((result) => (result.new_topic_count ?? 0) > 0 && result.summary_markdown).length;
  if (missingCount > 0 && incrementalCount > 0) {
    return `初始化 ${missingCount} / 增量 ${incrementalCount}`;
  }
  if (missingCount > 0) {
    return `初始化 ${missingCount} 只`;
  }
  if (incrementalCount > 0) {
    return `增量处理 ${incrementalCount} 只`;
  }
  return '已处理完成，重新处理';
}

export default function StockTopicAnalysisPanel({ groupId, onTaskCreated }: StockTopicAnalysisPanelProps) {
  const cacheKey = `stock-topic-analysis:${groupId}`;
  const [stockInput, setStockInput] = useState('');
  const [results, setResults] = useState<StockTopicAnalysisResponse[]>([]);
  const [searching, setSearching] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [extractingImage, setExtractingImage] = useState(false);
  const [activeBatchAnalysis, setActiveBatchAnalysis] = useState<ActiveBatchAnalysis | null>(null);
  const [selectedResult, setSelectedResult] = useState<StockTopicAnalysisResponse | null>(null);
  const imageInputRef = useRef<HTMLInputElement | null>(null);

  const parsedStockNames = useMemo(() => parseStockNames(stockInput), [stockInput]);
  const totalTopics = results.reduce((sum, result) => sum + result.topic_count, 0);
  const analyzedCount = results.filter((result) => Boolean(result.summary_markdown)).length;
  const newTopicCount = results.reduce((sum, result) => sum + (result.new_topic_count ?? 0), 0);
  const analyzeButtonLabel = getAnalyzeButtonLabel(results, parsedStockNames.length, Boolean(activeBatchAnalysis), analyzing);

  useEffect(() => {
    try {
      const raw = window.sessionStorage.getItem(cacheKey);
      if (!raw) {
        return;
      }
      const cached = JSON.parse(raw) as Partial<StockTopicPanelCache>;
      if (typeof cached.stockInput === 'string') {
        setStockInput(cached.stockInput);
      }
      if (Array.isArray(cached.results)) {
        setResults(cached.results);
      }
    } catch {
      window.sessionStorage.removeItem(cacheKey);
    }
  }, [cacheKey]);

  useEffect(() => {
    try {
      window.sessionStorage.setItem(cacheKey, JSON.stringify({ stockInput, results }));
    } catch {
      // Ignore quota or privacy-mode storage failures; the page still works without cache.
    }
  }, [cacheKey, stockInput, results]);

  const loadBatchResults = useCallback(async (stockNames: string[]) => {
    const [searchResults, latestBatch] = await Promise.all([
      Promise.all(stockNames.map((stockName) => apiClient.searchStockTopics(groupId, stockName))),
      apiClient.getLatestStockTopicAnalyses(groupId, stockNames),
    ]);
    const latestByName = new Map(
      latestBatch.stocks.map((item) => [item.stock_name.trim(), item]),
    );
    const mergedResults = searchResults.map((searchResult, index) => {
      const latest = latestBatch.stocks[index] || latestByName.get(searchResult.stock_name.trim()) || latestByName.get(stockNames[index]) || null;
      return mergeSearchAndLatestResult(searchResult, latest);
    });
    setResults(mergedResults);
    return mergedResults;
  }, [groupId]);

  const handleSearch = async () => {
    if (parsedStockNames.length === 0) {
      toast.error('请输入至少一只股票名称');
      return;
    }
    try {
      setSearching(true);
      const nextResults = await loadBatchResults(parsedStockNames);
      const nextNewTopicCount = nextResults.reduce((sum, result) => sum + (result.new_topic_count ?? 0), 0);
      toast.success(`已查询 ${parsedStockNames.length} 只股票，发现 ${nextNewTopicCount} 条待处理话题`);
    } catch (error) {
      toast.error(`搜索失败: ${error instanceof Error ? error.message : '未知错误'}`);
    } finally {
      setSearching(false);
    }
  };

  const handleAnalyze = async () => {
    if (parsedStockNames.length === 0) {
      toast.error('请输入至少一只股票名称');
      return;
    }
    try {
      setAnalyzing(true);
      const response = await apiClient.analyzeStockTopicsBatch(groupId, parsedStockNames);
      setActiveBatchAnalysis({ taskId: response.task_id, stockNames: parsedStockNames });
      onTaskCreated?.(response.task_id);
      toast.success(`批量个股分析任务已创建: ${response.task_id}`);
    } catch (error) {
      toast.error(`创建批量分析任务失败: ${error instanceof Error ? error.message : '未知错误'}`);
    } finally {
      setAnalyzing(false);
    }
  };

  const extractStocksFromImageFile = async (file: File) => {
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
      toast.error('仅支持 JPG、PNG 或 WebP 图片');
      return;
    }
    if (file.size > MAX_IMAGE_BYTES) {
      toast.error('图片不能超过 4MB');
      return;
    }

    try {
      setExtractingImage(true);
      const imageDataUrl = await readFileAsDataUrl(file);
      const response = await apiClient.extractStockTopicsFromImage(imageDataUrl);
      setStockInput((value) => mergeStockInput(value, response.stockNames));
      toast.success(`已从图片识别 ${response.stockNames.length} 只股票`);
    } catch (error) {
      const message = error instanceof Error ? error.message : '未知错误';
      if (message.includes('没有识别到明确股票名称')) {
        toast.info(message);
      } else {
        toast.error(`图片识别失败: ${message}`);
      }
    } finally {
      setExtractingImage(false);
    }
  };

  const handleImageSelected = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) {
      return;
    }
    await extractStocksFromImageFile(file);
  };

  const handleStockInputPaste = async (event: ClipboardEvent<HTMLTextAreaElement>) => {
    const imageFile = Array.from(event.clipboardData.files).find((file) => file.type.startsWith('image/'));
    if (!imageFile) {
      return;
    }
    event.preventDefault();
    await extractStocksFromImageFile(imageFile);
  };

  useTaskStatus(activeBatchAnalysis?.taskId, {
    enabled: Boolean(activeBatchAnalysis),
    onTerminal: async (task) => {
      const stockNames = activeBatchAnalysis?.stockNames || [];
      if (task.status === 'completed') {
        await loadBatchResults(stockNames);
        toast.success('批量个股分析已保存');
      } else {
        toast.error(task.message || '批量个股分析任务未完成');
      }
      setActiveBatchAnalysis(null);
    },
  });

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
      <div className="space-y-4">
        <Card>
          <CardHeader>
            <CardTitle>个股分析</CardTitle>
            <CardDescription>输入多只股票，查询已保存结果；没有结果可初始化，有新话题可增量更新</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <input
              ref={imageInputRef}
              type="file"
              accept="image/png,image/jpeg,image/webp"
              className="hidden"
              onChange={handleImageSelected}
            />
            <Textarea
              value={stockInput}
              onChange={(event) => setStockInput(event.target.value)}
              onPaste={(event) => void handleStockInputPaste(event)}
              placeholder={'例如：德龙激光、宁德时代\n中际旭创 贵州茅台'}
              className="min-h-24 resize-y"
            />
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="text-sm text-muted-foreground">
                已识别 {parsedStockNames.length}/{MAX_STOCK_COUNT} 只，自动去重
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  onClick={() => imageInputRef.current?.click()}
                  disabled={extractingImage}
                >
                  <ImagePlus className="mr-2 h-4 w-4" />
                  {extractingImage ? '识别中...' : '图片提取'}
                </Button>
                <Button variant="outline" onClick={handleSearch} disabled={searching || parsedStockNames.length === 0}>
                  <Search className="mr-2 h-4 w-4" />
                  {searching ? '搜索中...' : '搜索'}
                </Button>
                <Button onClick={handleAnalyze} disabled={analyzing || Boolean(activeBatchAnalysis) || parsedStockNames.length === 0}>
                  <Sparkles className="mr-2 h-4 w-4" />
                  {analyzeButtonLabel}
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-start justify-between gap-3">
            <div>
              <CardTitle>批量结果</CardTitle>
              <CardDescription>每只股票一行；搜索查询已有结果，分析任务只处理未处理过的新话题</CardDescription>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => void loadBatchResults(parsedStockNames)}
              disabled={searching || parsedStockNames.length === 0}
            >
              <RefreshCw className="mr-2 h-4 w-4" />
              刷新
            </Button>
          </CardHeader>
          <CardContent>
            {results.length === 0 ? (
              <div className="flex min-h-48 items-center justify-center rounded-md border border-dashed text-sm text-muted-foreground">
                输入股票后点击搜索，查看话题命中和已保存分析
              </div>
            ) : (
              <div className="overflow-hidden rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>股票</TableHead>
                      <TableHead>代码</TableHead>
                      <TableHead className="text-right">话题数</TableHead>
                      <TableHead className="text-right">待处理话题</TableHead>
                      <TableHead>概念</TableHead>
                      <TableHead className="text-right">推荐次数</TableHead>
                      <TableHead>状态</TableHead>
                      <TableHead>保存时间</TableHead>
                      <TableHead className="text-right">查看</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {results.map((result) => (
                      <TableRow key={`${result.stock_name}-${result.stock_code || 'no-code'}`}>
                        <TableCell className="font-medium">{result.stock_name}</TableCell>
                        <TableCell className="font-mono text-xs text-muted-foreground">{formatStockCode(result)}</TableCell>
                        <TableCell className="text-right">{result.topic_count}</TableCell>
                        <TableCell className="text-right">{result.new_topic_count ?? '-'}</TableCell>
                        <TableCell>
                          {result.concepts.length === 0 ? (
                            <span className="text-muted-foreground">-</span>
                          ) : (
                            <div className="flex max-w-64 flex-wrap gap-1">
                              {result.concepts.slice(0, 4).map((concept) => (
                                <Badge key={concept} variant="secondary">{concept}</Badge>
                              ))}
                              {result.concepts.length > 4 && <Badge variant="outline">+{result.concepts.length - 4}</Badge>}
                            </div>
                          )}
                        </TableCell>
                        <TableCell className="text-right">{result.recommendation_count}</TableCell>
                        <TableCell>{getStatusBadge(result)}</TableCell>
                        <TableCell className="whitespace-nowrap text-xs text-muted-foreground">{formatDateTime(result.updated_at)}</TableCell>
                        <TableCell className="text-right">
                          <Button variant="outline" size="sm" onClick={() => setSelectedResult(result)}>
                            <Eye className="mr-2 h-4 w-4" />
                            查看
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <Card className="h-fit">
        <CardHeader>
          <CardTitle>统计</CardTitle>
              <CardDescription>当前输入与结果概览</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">输入股票</span>
            <span className="font-medium">{parsedStockNames.length}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">结果行数</span>
            <span className="font-medium">{results.length}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">命中话题</span>
            <span className="font-medium">{totalTopics}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">已保存总结</span>
            <span className="font-medium">{analyzedCount}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">待处理话题</span>
            <span className="font-medium">{newTopicCount}</span>
          </div>
          {activeBatchAnalysis && (
            <div className="rounded-md border border-blue-100 bg-blue-50 p-3 text-xs text-blue-700">
              批量分析任务运行中，完成后会自动刷新表格。
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={Boolean(selectedResult)} onOpenChange={(open) => !open && setSelectedResult(null)}>
        <DialogContent className="max-h-[90vh] w-[calc(100vw-32px)] max-w-[1200px] grid-rows-[auto_auto_auto_minmax(0,1fr)] overflow-hidden sm:max-w-[1200px]">
          {selectedResult && (
            <>
              <DialogHeader>
                <DialogTitle className="text-xl">{selectedResult.stock_name} AI 总结</DialogTitle>
                <DialogDescription>
                  {formatStockCode(selectedResult)} · 话题 {selectedResult.topic_count} · 待处理话题 {selectedResult.new_topic_count ?? 0} · 推荐 {selectedResult.recommendation_count} · {formatDateTime(selectedResult.updated_at)}
                </DialogDescription>
              </DialogHeader>
              <div className="grid gap-3 text-sm sm:grid-cols-4">
                <div className="rounded-md border p-3">
                  <div className="text-muted-foreground">状态</div>
                  <div className="mt-1">{getStatusBadge(selectedResult)}</div>
                </div>
                <div className="rounded-md border p-3">
                  <div className="text-muted-foreground">话题数</div>
                  <div className="mt-1 font-semibold">{selectedResult.topic_count}</div>
                </div>
                <div className="rounded-md border p-3">
                  <div className="text-muted-foreground">推荐次数</div>
                  <div className="mt-1 font-semibold">{selectedResult.recommendation_count}</div>
                </div>
                <div className="rounded-md border p-3">
                  <div className="text-muted-foreground">模型</div>
                  <div className="mt-1 truncate font-medium">{selectedResult.model || '-'}</div>
                </div>
              </div>
              {selectedResult.concepts.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {selectedResult.concepts.map((concept) => (
                    <Badge key={concept} variant="secondary">{concept}</Badge>
                  ))}
                </div>
              )}
              <ScrollArea className="min-h-0 h-[62vh] rounded-md border p-6">
                {selectedResult.summary_markdown ? (
                  <div className="prose max-w-none text-base leading-7">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{selectedResult.summary_markdown}</ReactMarkdown>
                  </div>
                ) : (
                  <div className="text-sm text-muted-foreground">
                    {selectedResult.error || '暂无 AI 总结，请先点击一键分析。'}
                  </div>
                )}
              </ScrollArea>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
