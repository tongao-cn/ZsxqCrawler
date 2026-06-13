'use client';

import { useCallback, useEffect, useState } from 'react';

import { apiClient, DailyStockConceptResponse, DailyTopicReport } from '@/lib/api';

export interface ConceptTrendItem {
  concept: string;
  counts: number[];
  stockCounts: number[];
  total: number;
  stockTotal: number;
}

type DailyTopicMode = 'report' | 'stock-concepts';

interface UseDailyTopicAnalysisDataOptions {
  groupId: number;
  mode: DailyTopicMode;
  normalizeCompanyName: (value?: string | null) => string;
  normalizeConceptName: (value?: string | null) => string;
  normalizeSignalTagName?: (value?: string | null) => string | null;
  reportDate: string;
}

function isAbortError(error: unknown) {
  return error instanceof DOMException && error.name === 'AbortError';
}

function getDateText(offsetDays = 0, baseDate?: string) {
  const date = baseDate ? new Date(`${baseDate}T00:00:00`) : new Date();
  date.setDate(date.getDate() + offsetDays);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export function useDailyTopicAnalysisData({
  groupId,
  mode,
  normalizeCompanyName,
  normalizeConceptName,
  normalizeSignalTagName,
  reportDate,
}: UseDailyTopicAnalysisDataOptions) {
  const [loadingReport, setLoadingReport] = useState(false);
  const [loadingStockConcepts, setLoadingStockConcepts] = useState(false);
  const [report, setReport] = useState<DailyTopicReport | null>(null);
  const [stockConcepts, setStockConcepts] = useState<DailyStockConceptResponse | null>(null);
  const [conceptTrendDates, setConceptTrendDates] = useState<string[]>([]);
  const [conceptTrendItems, setConceptTrendItems] = useState<ConceptTrendItem[]>([]);
  const [recommendedCompanies, setRecommendedCompanies] = useState<Set<string>>(new Set());
  const [loadingRecommendations, setLoadingRecommendations] = useState(false);

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
    if (mode !== 'report') {
      setReport(null);
      setLoadingReport(false);
      return;
    }
    const controller = new AbortController();
    void loadReport(controller.signal);
    return () => controller.abort();
  }, [loadReport, mode]);

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
    if (mode !== 'stock-concepts') {
      setStockConcepts(null);
      setLoadingStockConcepts(false);
      return;
    }
    const controller = new AbortController();
    void loadStockConcepts(controller.signal);
    return () => controller.abort();
  }, [loadStockConcepts, mode]);

  const loadConceptTrend = useCallback(async (signal?: AbortSignal) => {
    const dates = Array.from({ length: 7 }, (_, index) => getDateText(index - 6, reportDate));
    try {
      const results = await Promise.all(
        dates.map(async (date) => {
          try {
            return await apiClient.getDailyStockConcepts(groupId, date, { signal });
          } catch (error) {
            if (isAbortError(error)) {
              throw error;
            }
            return null;
          }
        })
      );
      if (signal?.aborted) {
        return;
      }
      const conceptMap = new Map<string, { topics: Array<Set<string>>; stocks: Array<Set<string>> }>();
      results.forEach((result, dateIndex) => {
        for (const stock of result?.stocks || []) {
          const uniqueConcepts = new Set(
            (stock.concepts || [])
              .map((concept) => normalizeSignalTagName?.(concept) || normalizeConceptName(concept))
              .filter(Boolean)
          );
          uniqueConcepts.forEach((concept) => {
            if (!conceptMap.has(concept)) {
              conceptMap.set(concept, {
                topics: Array.from({ length: dates.length }, () => new Set<string>()),
                stocks: Array.from({ length: dates.length }, () => new Set<string>()),
              });
            }
            const item = conceptMap.get(concept);
            item?.stocks[dateIndex]?.add(stock.stock_name);
            stock.topic_ids.forEach((topicId) => item?.topics[dateIndex]?.add(String(topicId)));
          });
        }
      });
      const items = Array.from(conceptMap.entries())
        .map(([concept, value]) => {
          const counts = value.topics.map((topics) => topics.size);
          const stockCounts = value.stocks.map((stocks) => stocks.size);
          return {
            concept,
            counts,
            stockCounts,
            total: counts.reduce((sum, count) => sum + count, 0),
            stockTotal: stockCounts.reduce((sum, count) => sum + count, 0),
          };
        })
        .sort((a, b) => {
          if (b.total !== a.total) {
            return b.total - a.total;
          }
          if (b.stockTotal !== a.stockTotal) {
            return b.stockTotal - a.stockTotal;
          }
          return a.concept.localeCompare(b.concept, 'zh-CN');
        })
        .slice(0, 12);
      setConceptTrendDates(dates);
      setConceptTrendItems(items);
    } catch (error) {
      if (!isAbortError(error)) {
        setConceptTrendDates(dates);
        setConceptTrendItems([]);
      }
    }
  }, [groupId, normalizeConceptName, normalizeSignalTagName, reportDate]);

  useEffect(() => {
    if (mode !== 'stock-concepts') {
      setConceptTrendDates([]);
      setConceptTrendItems([]);
      return;
    }
    const controller = new AbortController();
    void loadConceptTrend(controller.signal);
    return () => controller.abort();
  }, [loadConceptTrend, mode]);

  const loadRecommendationHits = useCallback(async (signal?: AbortSignal) => {
    try {
      setLoadingRecommendations(true);
      const chart = await apiClient.getAShareAnalysisChart({
        groupId,
        startDate: reportDate,
        endDate: reportDate,
        topN: 100,
      }, {
        signal,
      });
      if (signal?.aborted) {
        return;
      }
      const companies = new Set<string>();
      Object.values(chart.rankings || {}).forEach((rows) => {
        rows.forEach((item) => companies.add(normalizeCompanyName(item.company)));
      });
      setRecommendedCompanies(companies);
    } catch (error) {
      if (isAbortError(error)) {
        return;
      }
      setRecommendedCompanies(new Set());
    } finally {
      if (!signal?.aborted) {
        setLoadingRecommendations(false);
      }
    }
  }, [groupId, normalizeCompanyName, reportDate]);

  useEffect(() => {
    if (mode !== 'stock-concepts') {
      setRecommendedCompanies(new Set());
      setLoadingRecommendations(false);
      return;
    }
    const controller = new AbortController();
    void loadRecommendationHits(controller.signal);
    return () => controller.abort();
  }, [loadRecommendationHits, mode]);

  return {
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
  };
}
