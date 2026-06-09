'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { toast } from 'sonner';

import { apiClient, DailyStockConcept, TopicDetail } from '@/lib/api';
import DailyStockConceptsView from '@/components/DailyStockConceptsView';
import DailyTopicReportView from '@/components/DailyTopicReportView';
import DailyStockDetailDialog, { type StockTrendDay } from '@/components/DailyStockDetailDialog';
import DailyTopicDetailDialog from '@/components/DailyTopicDetailDialog';
import { useDailyTopicAnalysisData } from '@/hooks/useDailyTopicAnalysisData';
import {
  getDateText,
  getTodayText,
  isRisingTrend,
  normalizeCompanyName,
  normalizeConceptName,
  stockKey,
  type ConceptQualityTag,
  type ConceptStat,
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
  const [selectedTopicId, setSelectedTopicId] = useState<string | null>(null);
  const [topicDetail, setTopicDetail] = useState<TopicDetail | null>(null);
  const [loadingTopicDetail, setLoadingTopicDetail] = useState(false);
  const [selectedConcept, setSelectedConcept] = useState<string | null>(null);
  const [selectedConceptDetail, setSelectedConceptDetail] = useState<string | null>(null);
  const [onlyRecommendationHits, setOnlyRecommendationHits] = useState(false);
  const topicDetailRequestRef = useRef(0);
  const stockTrendRequestRef = useRef(0);
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

  const conceptStats = useMemo<ConceptStat[]>(() => {
    const conceptMap = new Map<string, { aliases: Set<string>; stocks: Set<string>; topics: Set<string>; recommendedStocks: Set<string> }>();
    for (const stock of stockConcepts?.stocks || []) {
      const stockName = stock.stock_name?.trim();
      if (!stockName) {
        continue;
      }
      const normalizedStockName = normalizeCompanyName(stockName);
      for (const rawConcept of stock.concepts || []) {
        const alias = rawConcept.trim();
        if (!alias) {
          continue;
        }
        const concept = normalizeConceptName(alias);
        if (!conceptMap.has(concept)) {
          conceptMap.set(concept, {
            aliases: new Set(),
            stocks: new Set(),
            topics: new Set(),
            recommendedStocks: new Set(),
          });
        }
        const item = conceptMap.get(concept);
        item?.aliases.add(alias);
        item?.stocks.add(stockName);
        stock.topic_ids.forEach((topicId) => item?.topics.add(String(topicId)));
        if (recommendedCompanies.has(normalizedStockName)) {
          item?.recommendedStocks.add(stockName);
        }
      }
    }

    return Array.from(conceptMap.entries())
      .map(([concept, value]) => ({
        concept,
        aliases: Array.from(value.aliases).sort((a, b) => a.localeCompare(b, 'zh-CN')),
        stockNames: Array.from(value.stocks).sort((a, b) => a.localeCompare(b, 'zh-CN')),
        stockCount: value.stocks.size,
        topicIds: Array.from(value.topics).sort((a, b) => a.localeCompare(b, 'zh-CN')),
        topicCount: value.topics.size,
        recommendationHitCount: value.recommendedStocks.size,
      }))
      .sort((a, b) => {
        if (b.topicCount !== a.topicCount) {
          return b.topicCount - a.topicCount;
        }
        if (b.recommendationHitCount !== a.recommendationHitCount) {
          return b.recommendationHitCount - a.recommendationHitCount;
        }
        if (b.stockCount !== a.stockCount) {
          return b.stockCount - a.stockCount;
        }
        return a.concept.localeCompare(b.concept, 'zh-CN');
      });
  }, [recommendedCompanies, stockConcepts]);

  const conceptTrendMap = useMemo(
    () => new Map(conceptTrendItems.map((item) => [item.concept, item])),
    [conceptTrendItems]
  );
  const getConceptQualityTags = useCallback((stat: ConceptStat): ConceptQualityTag[] => {
    const tags: ConceptQualityTag[] = [];
    const trend = conceptTrendMap.get(stat.concept);
    if (stat.topicCount >= 2) {
      tags.push({ label: '多话题共振', className: 'bg-blue-100 text-blue-800' });
    }
    if (stat.recommendationHitCount > 0) {
      tags.push({ label: '推荐池共振', className: 'bg-emerald-100 text-emerald-800' });
    }
    if (stat.topicCount <= 1 && stat.stockCount >= 8) {
      tags.push({ label: '单话题扩散', className: 'bg-amber-100 text-amber-800' });
    }
    if (trend && trend.counts.slice(0, -1).every((count) => count === 0) && trend.counts.at(-1)! > 0) {
      tags.push({ label: '新出现', className: 'bg-violet-100 text-violet-800' });
    }
    if (trend && isRisingTrend(trend.counts)) {
      tags.push({ label: '持续升温', className: 'bg-rose-100 text-rose-800' });
    }
    return tags;
  }, [conceptTrendMap]);
  const filteredStocks = useMemo(() => {
    const stocks = stockConcepts?.stocks || [];
    return stocks.filter((stock) => {
      if (selectedConcept && !stock.concepts.some((concept) => normalizeConceptName(concept) === selectedConcept)) {
        return false;
      }
      if (onlyRecommendationHits && !recommendedCompanies.has(normalizeCompanyName(stock.stock_name))) {
        return false;
      }
      return true;
    });
  }, [onlyRecommendationHits, recommendedCompanies, selectedConcept, stockConcepts]);
  const recommendedStockCount = useMemo(
    () => filteredStocks.filter((stock) => recommendedCompanies.has(normalizeCompanyName(stock.stock_name))).length,
    [filteredStocks, recommendedCompanies]
  );
  const selectedConceptStat = useMemo(
    () => conceptStats.find((item) => item.concept === selectedConceptDetail) || null,
    [conceptStats, selectedConceptDetail]
  );
  const selectedConceptTrend = useMemo(
    () => conceptTrendItems.find((item) => item.concept === selectedConceptDetail) || null,
    [conceptTrendItems, selectedConceptDetail]
  );

  useEffect(() => {
    if (mode !== 'stock-concepts') {
      setSelectedStock(null);
      setStockTrend([]);
      setSelectedTopicId(null);
      setTopicDetail(null);
    }
  }, [mode]);

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

  const openTopicDetail = async (topicId: string | number) => {
    const id = String(topicId);
    const requestId = topicDetailRequestRef.current + 1;
    topicDetailRequestRef.current = requestId;
    try {
      setSelectedTopicId(id);
      setTopicDetail(null);
      setLoadingTopicDetail(true);
      const detail = await apiClient.getTopicDetail(id, groupId);
      if (topicDetailRequestRef.current !== requestId) {
        return;
      }
      setTopicDetail(detail);
    } catch (error) {
      if (topicDetailRequestRef.current !== requestId) {
        return;
      }
      toast.error(`加载话题详情失败: ${error instanceof Error ? error.message : '未知错误'}`);
    } finally {
      if (topicDetailRequestRef.current === requestId) {
        setLoadingTopicDetail(false);
      }
    }
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

  const closeTopicDetail = () => {
    topicDetailRequestRef.current += 1;
    setSelectedTopicId(null);
    setTopicDetail(null);
    setLoadingTopicDetail(false);
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
