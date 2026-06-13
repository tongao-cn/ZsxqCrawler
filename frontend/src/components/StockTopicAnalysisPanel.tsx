'use client';

import { RefreshCw, Sparkles } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import StockTopicAnalysisInputCard from '@/components/StockTopicAnalysisInputCard';
import StockTopicAnalysisResultDialog from '@/components/StockTopicAnalysisResultDialog';
import StockTopicAnalysisResultsTable from '@/components/StockTopicAnalysisResultsTable';
import StockTopicAnalysisStatsCard from '@/components/StockTopicAnalysisStatsCard';
import { StockTopicAnalysisStatusBadge } from '@/components/StockTopicAnalysisStatusBadge';
import { MAX_STOCK_COUNT, getStockTopicResultKey, useStockTopicAnalysisPanel } from '@/hooks/useStockTopicAnalysisPanel';

interface StockTopicAnalysisPanelProps {
  groupId: number | string;
  onTaskCreated?: (taskId: string) => void;
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
              renderStatusBadge={(result) => <StockTopicAnalysisStatusBadge result={result} />}
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
