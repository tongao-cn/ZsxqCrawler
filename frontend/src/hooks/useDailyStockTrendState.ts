'use client';

import { useCallback, useState } from 'react';

import { DailyStockConcept, apiClient } from '@/lib/api';
import { getDateText, stockKey } from '@/components/DailyTopicAnalysisPanelUtils';
import { type StockTrendDay } from '@/components/DailyStockDetailDialog';
import { useLatestRequestGuard } from '@/hooks/useLatestRequestGuard';

interface UseDailyStockTrendStateOptions {
  groupId: number;
  reportDate: string;
}

export function useDailyStockTrendState({
  groupId,
  reportDate,
}: UseDailyStockTrendStateOptions) {
  const [selectedStock, setSelectedStock] = useState<DailyStockConcept | null>(null);
  const [stockTrend, setStockTrend] = useState<StockTrendDay[]>([]);
  const [loadingStockTrend, setLoadingStockTrend] = useState(false);
  const { invalidateRequests, isLatestRequest, nextRequestId } = useLatestRequestGuard();

  const openStockDetail = useCallback(async (stock: DailyStockConcept) => {
    const selectedReportDate = reportDate;
    const targetKey = stockKey(stock);
    const requestId = nextRequestId();
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
      if (!isLatestRequest(requestId)) {
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
      if (isLatestRequest(requestId)) {
        setLoadingStockTrend(false);
      }
    }
  }, [groupId, isLatestRequest, nextRequestId, reportDate]);

  const closeStockDetail = useCallback(() => {
    invalidateRequests();
    setSelectedStock(null);
    setStockTrend([]);
    setLoadingStockTrend(false);
  }, [invalidateRequests]);

  return {
    closeStockDetail,
    loadingStockTrend,
    openStockDetail,
    selectedStock,
    stockTrend,
  };
}
