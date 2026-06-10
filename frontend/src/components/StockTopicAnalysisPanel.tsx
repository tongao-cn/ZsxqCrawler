'use client';

import { RefreshCw, Sparkles } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import StockTopicAnalysisInputCard from '@/components/StockTopicAnalysisInputCard';
import StockTopicAnalysisResultDialog from '@/components/StockTopicAnalysisResultDialog';
import StockTopicAnalysisResultsTable from '@/components/StockTopicAnalysisResultsTable';
import StockTopicAnalysisStatsCard from '@/components/StockTopicAnalysisStatsCard';
import { type StockTopicAnalysisResponse } from '@/lib/api';
import { MAX_STOCK_COUNT, getStockTopicResultKey, useStockTopicAnalysisPanel } from '@/hooks/useStockTopicAnalysisPanel';

interface StockTopicAnalysisPanelProps {
  groupId: number | string;
  onTaskCreated?: (taskId: string) => void;
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

export default function StockTopicAnalysisPanel({ groupId, onTaskCreated }: StockTopicAnalysisPanelProps) {
  const {
    active,
    allResultsSelected,
    analyzedCount,
    analyzeButtonLabel,
    analyzing,
    extractingImage,
    handleAnalyze,
    handleAnalyzeOne,
    handleAnalyzeSelected,
    handleImageSelected,
    handleSearch,
    handleStockInputKeyDown,
    handleStockInputPaste,
    imageInputRef,
    newTopicCount,
    parsedStockCount,
    refreshResults,
    results,
    searching,
    selectedResult,
    selectedResults,
    selectedStockNames,
    setSelectedResult,
    setStockInput,
    stockInput,
    toggleAllResults,
    toggleResult,
    totalTopics,
  } = useStockTopicAnalysisPanel({ groupId, onTaskCreated });

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
          parsedStockCount={parsedStockCount}
          searching={searching}
          stockInput={stockInput}
          taskActive={active}
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
                disabled={analyzing || active || selectedResults.length === 0}
              >
                <Sparkles className="mr-2 h-4 w-4" />
                分析/初始化选中 {selectedResults.length > 0 ? selectedResults.length : ''}
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => void refreshResults()}
                disabled={searching || parsedStockCount === 0}
              >
                <RefreshCw className="mr-2 h-4 w-4" />
                刷新
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            <StockTopicAnalysisResultsTable
              active={active}
              allResultsSelected={allResultsSelected}
              analyzing={analyzing}
              getResultKey={getStockTopicResultKey}
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
        active={active}
        analyzedCount={analyzedCount}
        newTopicCount={newTopicCount}
        parsedStockCount={parsedStockCount}
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
