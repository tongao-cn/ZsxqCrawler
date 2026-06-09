'use client';

import { ChangeEvent, ClipboardEvent, KeyboardEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { RefreshCw, Sparkles } from 'lucide-react';
import { toast } from 'sonner';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import StockTopicAnalysisInputCard from '@/components/StockTopicAnalysisInputCard';
import StockTopicAnalysisResultDialog from '@/components/StockTopicAnalysisResultDialog';
import StockTopicAnalysisResultsTable from '@/components/StockTopicAnalysisResultsTable';
import StockTopicAnalysisStatsCard from '@/components/StockTopicAnalysisStatsCard';
import { apiClient, StockTopicAnalysisResponse } from '@/lib/api';
import { useTaskStatus } from '@/hooks/useTaskStatus';

const MAX_STOCK_COUNT = 50;
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

function getResultKey(result: StockTopicAnalysisResponse) {
  return result.stock_name.trim();
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
    (latestResult?.processed_topic_ids || latestResult?.analyzed_topic_ids || []).map(String),
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
  const [selectedStockNames, setSelectedStockNames] = useState<Set<string>>(() => new Set());
  const imageInputRef = useRef<HTMLInputElement | null>(null);

  const parsedStockNames = useMemo(() => parseStockNames(stockInput), [stockInput]);
  const selectedResults = useMemo(
    () => results.filter((result) => selectedStockNames.has(getResultKey(result))),
    [results, selectedStockNames],
  );
  const totalTopics = results.reduce((sum, result) => sum + result.topic_count, 0);
  const analyzedCount = results.filter((result) => Boolean(result.summary_markdown)).length;
  const newTopicCount = results.reduce((sum, result) => sum + (result.new_topic_count ?? 0), 0);
  const analyzeButtonLabel = getAnalyzeButtonLabel(results, parsedStockNames.length, Boolean(activeBatchAnalysis), analyzing);
  const allResultsSelected = results.length > 0 && selectedResults.length === results.length;

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
    setSelectedStockNames((current) => {
      const available = new Set(mergedResults.map(getResultKey));
      return new Set(Array.from(current).filter((stockName) => available.has(stockName)));
    });
    return mergedResults;
  }, [groupId]);

  const createAnalysisTask = async (stockNames: string[], successPrefix: string) => {
    try {
      setAnalyzing(true);
      const response = await apiClient.analyzeStockTopicsBatch(groupId, stockNames);
      setActiveBatchAnalysis({ taskId: response.task_id, stockNames: [...stockNames] });
      onTaskCreated?.(response.task_id);
      toast.success(`${successPrefix}: ${response.task_id}`);
    } catch (error) {
      toast.error(`创建分析任务失败: ${error instanceof Error ? error.message : '未知错误'}`);
    } finally {
      setAnalyzing(false);
    }
  };

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
    await createAnalysisTask(parsedStockNames, '批量个股分析任务已创建');
  };

  const handleAnalyzeSelected = async () => {
    const stockNames = selectedResults.map((result) => result.stock_name);
    if (stockNames.length === 0) {
      toast.error('请先勾选要分析的股票');
      return;
    }
    await createAnalysisTask(stockNames, `选中 ${stockNames.length} 只股票的分析任务已创建`);
  };

  const handleAnalyzeOne = async (result: StockTopicAnalysisResponse) => {
    await createAnalysisTask([result.stock_name], `${result.stock_name} 分析任务已创建`);
  };

  const toggleAllResults = (checked: boolean) => {
    setSelectedStockNames(checked ? new Set(results.map(getResultKey)) : new Set());
  };

  const toggleResult = (result: StockTopicAnalysisResponse, checked: boolean) => {
    const stockName = getResultKey(result);
    setSelectedStockNames((current) => {
      const next = new Set(current);
      if (checked) {
        next.add(stockName);
      } else {
        next.delete(stockName);
      }
      return next;
    });
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

  const handleStockInputKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) {
      return;
    }
    event.preventDefault();
    void handleSearch();
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
        <StockTopicAnalysisInputCard
          analyzeButtonLabel={analyzeButtonLabel}
          analyzing={analyzing}
          extractingImage={extractingImage}
          imageInputRef={imageInputRef}
          maxStockCount={MAX_STOCK_COUNT}
          onAnalyze={handleAnalyze}
          onImageSelected={handleImageSelected}
          onImageUploadClick={() => imageInputRef.current?.click()}
          onSearch={handleSearch}
          onStockInputChange={setStockInput}
          onStockInputKeyDown={handleStockInputKeyDown}
          onStockInputPaste={(event) => void handleStockInputPaste(event)}
          parsedStockCount={parsedStockNames.length}
          searching={searching}
          stockInput={stockInput}
          taskActive={Boolean(activeBatchAnalysis)}
        />

        <Card>
          <CardHeader className="flex flex-row items-start justify-between gap-3">
            <div>
              <CardTitle>批量结果</CardTitle>
              <CardDescription>每只股票一行；搜索查询已有结果，分析任务只处理未处理过的新话题</CardDescription>
            </div>
            <div className="flex flex-wrap justify-end gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={handleAnalyzeSelected}
                disabled={analyzing || Boolean(activeBatchAnalysis) || selectedResults.length === 0}
              >
                <Sparkles className="mr-2 h-4 w-4" />
                分析/初始化选中 {selectedResults.length > 0 ? selectedResults.length : ''}
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => void loadBatchResults(parsedStockNames)}
                disabled={searching || parsedStockNames.length === 0}
              >
                <RefreshCw className="mr-2 h-4 w-4" />
                刷新
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            <StockTopicAnalysisResultsTable
              active={Boolean(activeBatchAnalysis)}
              allResultsSelected={allResultsSelected}
              analyzing={analyzing}
              getResultKey={getResultKey}
              onAnalyzeOne={(result) => void handleAnalyzeOne(result)}
              onOpenResult={setSelectedResult}
              onToggleAllResults={toggleAllResults}
              onToggleResult={toggleResult}
              renderStatusBadge={getStatusBadge}
              results={results}
              selectedStockNames={selectedStockNames}
            />
          </CardContent>
        </Card>
      </div>

      <StockTopicAnalysisStatsCard
        active={Boolean(activeBatchAnalysis)}
        analyzedCount={analyzedCount}
        newTopicCount={newTopicCount}
        parsedStockCount={parsedStockNames.length}
        resultCount={results.length}
        selectedCount={selectedResults.length}
        totalTopics={totalTopics}
      />

      <StockTopicAnalysisResultDialog
        onOpenChange={(open) => !open && setSelectedResult(null)}
        selectedResult={selectedResult}
      />
    </div>
  );
}
