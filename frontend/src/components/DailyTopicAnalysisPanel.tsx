'use client';

import { useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';

import { apiClient, DailyStockConcept } from '@/lib/api';
import DailyStockConceptsView from '@/components/DailyStockConceptsView';
import DailyTopicReportView from '@/components/DailyTopicReportView';
import DailyStockDetailDialog, { type StockTrendDay } from '@/components/DailyStockDetailDialog';
import DailyTopicDetailDialog from '@/components/DailyTopicDetailDialog';
import { useDailyTopicAnalysisData } from '@/hooks/useDailyTopicAnalysisData';
import { useDailyStockConceptDerivedState } from '@/hooks/useDailyStockConceptDerivedState';
import { useDailyTopicDetailState } from '@/hooks/useDailyTopicDetailState';
import {
  getDateText,
  getTodayText,
  normalizeCompanyName,
  normalizeConceptName,
  stockKey,
} from '@/components/DailyTopicAnalysisPanelUtils';

interface DailyTopicAnalysisPanelProps {
  groupId: number;
  onTaskCreated?: (taskId: string) => void;
  mode?: 'report' | 'stock-concepts';
}

export default function DailyTopicAnalysisPanel({
  groupId,
  onTaskCreated,
  mode = 'report',
}: DailyTopicAnalysisPanelProps) {
  const [reportDate, setReportDate] = useState(getTodayText);
  const [submitting, setSubmitting] = useState(false);
  const [extractingStocks, setExtractingStocks] = useState(false);
  const [selectedStock, setSelectedStock] = useState<DailyStockConcept | null>(null);
  const [stockTrend, setStockTrend] = useState<StockTrendDay[]>([]);
  const [loadingStockTrend, setLoadingStockTrend] = useState(false);
  const [selectedConcept, setSelectedConcept] = useState<string | null>(null);
  const [selectedConceptDetail, setSelectedConceptDetail] = useState<string | null>(null);
  const [onlyRecommendationHits, setOnlyRecommendationHits] = useState(false);
  const stockTrendRequestRef = useRef(0);
  const {
    closeTopicDetail,
    loadingTopicDetail,
    openTopicDetail,
    selectedTopicId,
    topicDetail,
  } = useDailyTopicDetailState(groupId);
  const {
    conceptTrendDates,
    conceptTrendItems,
    loadReport,
    loadStockConcepts,
    loadingRecommendations,
    loadingReport,
    loadingStockConcepts,
    recommendedCompanies,
    report,
    stockConcepts,
  } = useDailyTopicAnalysisData({
    groupId,
    mode,
    normalizeCompanyName,
    normalizeConceptName,
    reportDate,
  });

  const {
    conceptStats,
    filteredStocks,
    getConceptQualityTags,
    recommendedStockCount,
    selectedConceptStat,
    selectedConceptTrend,
  } = useDailyStockConceptDerivedState({
    conceptTrendItems,
    onlyRecommendationHits,
    recommendedCompanies,
    selectedConcept,
    selectedConceptDetail,
    stockConcepts,
  });

  useEffect(() => {
    if (mode !== 'stock-concepts') {
      setSelectedStock(null);
      setStockTrend([]);
      closeTopicDetail();
    }
  }, [closeTopicDetail, mode]);

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
      toast.success(`股票概念视图生成任务已创建: ${response.task_id}`);
      onTaskCreated?.(response.task_id);
    } catch (error) {
      toast.error(`创建股票概念视图任务失败: ${error instanceof Error ? error.message : '未知错误'}`);
    } finally {
      setExtractingStocks(false);
    }
  };

  const openConceptDetail = (concept: string) => {
    setSelectedConceptDetail(concept);
    setSelectedConcept(concept);
  };

  const openStockDetail = async (stock: DailyStockConcept) => {
    const selectedReportDate = reportDate;
    const targetKey = stockKey(stock);
    const requestId = stockTrendRequestRef.current + 1;
    stockTrendRequestRef.current = requestId;
    setSelectedStock(stock);
    setStockTrend([]);
    setLoadingStockTrend(true);
    const dates = Array.from({ length: 7 }, (_, index) => getDateText(index - 6, selectedReportDate));
    try {
      const results = await Promise.all(
        dates.map(async (date) => {
          try {
            return await apiClient.getDailyStockConcepts(groupId, date);
          } catch {
            return null;
          }
        })
      );
      if (stockTrendRequestRef.current !== requestId) {
        return;
      }
      setStockTrend(
        dates.map((date, index) => {
          const matched = results[index]?.stocks.find((item) => stockKey(item) === targetKey);
          const uniqueTopicIds = new Set((matched?.topic_ids || []).map((topicId) => String(topicId)));
          return {
            date,
            concepts: matched?.concepts || [],
            topicCount: uniqueTopicIds.size,
            present: Boolean(matched),
          };
        })
      );
    } finally {
      if (stockTrendRequestRef.current === requestId) {
        setLoadingStockTrend(false);
      }
    }
  };

  const closeStockDetail = () => {
    stockTrendRequestRef.current += 1;
    setSelectedStock(null);
    setStockTrend([]);
    setLoadingStockTrend(false);
  };

  return (
    <div className="flex flex-col gap-4 p-1">
      {mode === 'stock-concepts' ? (
        <DailyStockConceptsView
          conceptStats={conceptStats}
          conceptTrendDates={conceptTrendDates}
          extractingStocks={extractingStocks}
          filteredStocks={filteredStocks}
          getConceptQualityTags={getConceptQualityTags}
          loadingRecommendations={loadingRecommendations}
          loadingStockConcepts={loadingStockConcepts}
          onClearConcept={() => {
            setSelectedConcept(null);
            setSelectedConceptDetail(null);
          }}
          onConceptSelect={openConceptDetail}
          onExtract={handleExtractStockConcepts}
          onOpenStockDetail={(stock) => void openStockDetail(stock)}
          onOpenTopicDetail={(topicId) => void openTopicDetail(topicId)}
          onRefresh={() => void loadStockConcepts()}
          onReportDateChange={setReportDate}
          onToggleRecommendationHits={() => setOnlyRecommendationHits((value) => !value)}
          onlyRecommendationHits={onlyRecommendationHits}
          recommendedCompanies={recommendedCompanies}
          recommendedStockCount={recommendedStockCount}
          reportDate={reportDate}
          selectedConcept={selectedConcept}
          selectedConceptStat={selectedConceptStat}
          selectedConceptTrend={selectedConceptTrend}
          stockConcepts={stockConcepts}
        />
      ) : (
        <DailyTopicReportView
          loadingReport={loadingReport}
          onGenerate={handleRunToday}
          onRefresh={() => void loadReport()}
          onReportDateChange={setReportDate}
          report={report}
          reportDate={reportDate}
          submitting={submitting}
        />
      )}

      <DailyStockDetailDialog
        loadingStockTrend={loadingStockTrend}
        onOpenChange={(open) => !open && closeStockDetail()}
        onOpenTopicDetail={(topicId) => void openTopicDetail(topicId)}
        open={Boolean(selectedStock)}
        selectedStock={selectedStock}
        stockTrend={stockTrend}
      />

      <DailyTopicDetailDialog
        loading={loadingTopicDetail}
        onOpenChange={(open) => !open && closeTopicDetail()}
        open={Boolean(selectedTopicId)}
        topicDetail={topicDetail}
        topicId={selectedTopicId}
      />
    </div>
  );
}
