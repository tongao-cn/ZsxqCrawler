'use client';

import { useEffect, useState } from 'react';

import { apiClient } from '@/lib/api';
import DailyStockConceptsView from '@/components/DailyStockConceptsView';
import DailyTopicReportView from '@/components/DailyTopicReportView';
import DailyStockDetailDialog from '@/components/DailyStockDetailDialog';
import DailyTopicDetailDialog from '@/components/DailyTopicDetailDialog';
import { useDailyTopicAnalysisData } from '@/hooks/useDailyTopicAnalysisData';
import { useDailyStockConceptDerivedState } from '@/hooks/useDailyStockConceptDerivedState';
import { useDailyStockTrendState } from '@/hooks/useDailyStockTrendState';
import { useDailyTopicDetailState } from '@/hooks/useDailyTopicDetailState';
import { useTaskLauncher } from '@/hooks/useTaskLauncher';
import {
  getTodayText,
  normalizeCompanyName,
  normalizeConceptName,
  normalizeSignalTagName,
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
  const [selectedConcept, setSelectedConcept] = useState<string | null>(null);
  const [selectedConceptDetail, setSelectedConceptDetail] = useState<string | null>(null);
  const [onlyRecommendationHits, setOnlyRecommendationHits] = useState(false);
  const { handleTaskCreateError, notifyTaskLaunch } = useTaskLauncher({
    onTaskCreated,
  });
  const {
    closeStockDetail,
    loadingStockTrend,
    openStockDetail,
    selectedStock,
    stockTrend,
  } = useDailyStockTrendState({ groupId, reportDate });
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
    normalizeSignalTagName,
    reportDate,
  });

  const {
    conceptStats,
    filteredStocks,
    getConceptQualityTags,
    recommendedStockCount,
    selectedConceptStat,
    selectedConceptTrend,
    selectedRelatedStats,
    signalStats,
    unmappedRawTermCount,
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
      closeStockDetail();
      closeTopicDetail();
    }
  }, [closeStockDetail, closeTopicDetail, mode]);

  const handleRunToday = async () => {
    try {
      setSubmitting(true);
      const response = await apiClient.createDailyTopicAnalysis(groupId, {
        date: reportDate,
      });
      notifyTaskLaunch(response, (taskId) => `每日 AI 总结任务已创建: ${taskId}`);
    } catch (error) {
      handleTaskCreateError(error, '创建每日 AI 总结任务失败');
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
      notifyTaskLaunch(response, (taskId) => `股票概念视图生成任务已创建: ${taskId}`);
    } catch (error) {
      handleTaskCreateError(error, '创建股票概念视图任务失败');
    } finally {
      setExtractingStocks(false);
    }
  };

  const openConceptDetail = (concept: string) => {
    setSelectedConceptDetail(concept);
    setSelectedConcept(concept);
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
          selectedRelatedStats={selectedRelatedStats}
          signalStats={signalStats}
          stockConcepts={stockConcepts}
          unmappedRawTermCount={unmappedRawTermCount}
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
