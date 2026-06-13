'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';

import {
  apiClient,
  AShareAnalysisChart,
  AShareAnalysisStatus,
  AShareAnalysisSummary,
} from '@/lib/api';
import { formatAShareInputDate } from '@/lib/a-share-analysis-format';

const DEFAULT_CHART_RANGE_MONTHS = 1;

function formatLocalDate(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function subtractMonthsClamped(date: Date, months: number) {
  const targetYear = date.getFullYear();
  const targetMonth = date.getMonth() - months;
  const lastDay = new Date(targetYear, targetMonth + 1, 0).getDate();
  return new Date(targetYear, targetMonth, Math.min(date.getDate(), lastDay));
}

function getDefaultChartDateRange(summary?: AShareAnalysisSummary) {
  const availableStartDate = formatAShareInputDate(summary?.available_start_date);
  const availableEndDate = formatAShareInputDate(summary?.available_end_date);
  if (!availableEndDate) {
    return { startDate: availableStartDate, endDate: '' };
  }

  const [year, month, day] = availableEndDate.split('-').map(Number);
  if (!year || !month || !day) {
    return { startDate: availableStartDate, endDate: availableEndDate };
  }

  const defaultStartDate = formatLocalDate(
    subtractMonthsClamped(new Date(year, month - 1, day), DEFAULT_CHART_RANGE_MONTHS)
  );
  return {
    startDate: availableStartDate && availableStartDate > defaultStartDate ? availableStartDate : defaultStartDate,
    endDate: availableEndDate,
  };
}

interface UseAShareAnalysisDataOptions {
  defaultTopN: number;
  selectedGroupId?: number;
}

export function useAShareAnalysisData({
  defaultTopN,
  selectedGroupId,
}: UseAShareAnalysisDataOptions) {
  const [status, setStatus] = useState<AShareAnalysisStatus | null>(null);
  const [chart, setChart] = useState<AShareAnalysisChart | null>(null);
  const [loadingStatus, setLoadingStatus] = useState(false);
  const [loadingChart, setLoadingChart] = useState(false);
  const [topN, setTopN] = useState<number>(defaultTopN);
  const [selectedStartDate, setSelectedStartDate] = useState('');
  const [selectedEndDate, setSelectedEndDate] = useState('');
  const [runDays, setRunDays] = useState(21);
  const [concurrency, setConcurrency] = useState(10);
  const [runStartDate, setRunStartDate] = useState('');
  const [runEndDate, setRunEndDate] = useState('');
  const [resetStartDate, setResetStartDate] = useState('');
  const [resetEndDate, setResetEndDate] = useState('');
  const [initialized, setInitialized] = useState(false);
  const statusRequestRef = useRef(0);
  const chartRequestRef = useRef(0);

  useEffect(() => {
    if (!selectedGroupId) {
      statusRequestRef.current += 1;
      chartRequestRef.current += 1;
      setStatus(null);
      setChart(null);
      setInitialized(false);
      return;
    }

    let cancelled = false;
    let defaultChartRange = { startDate: '', endDate: '' };
    const statusRequestId = statusRequestRef.current + 1;
    const chartRequestId = chartRequestRef.current + 1;
    statusRequestRef.current = statusRequestId;
    chartRequestRef.current = chartRequestId;
    setInitialized(false);
    setTopN(defaultTopN);
    void (async () => {
      try {
        setLoadingStatus(true);
        const statusData = await apiClient.getAShareAnalysisStatus(selectedGroupId);
        if (cancelled || statusRequestRef.current !== statusRequestId) {
          return;
        }

        setStatus(statusData);
        setRunDays(statusData.defaults.days);
        setConcurrency(statusData.defaults.concurrency);
        defaultChartRange = getDefaultChartDateRange(statusData.summary);
        setSelectedStartDate(defaultChartRange.startDate);
        setSelectedEndDate(defaultChartRange.endDate);
        setRunStartDate('');
        setRunEndDate('');
        setResetStartDate('');
        setResetEndDate('');
        setInitialized(true);
      } catch (error) {
        if (!cancelled && statusRequestRef.current === statusRequestId) {
          toast.error(`加载股票推荐池状态失败: ${error instanceof Error ? error.message : '未知错误'}`);
        }
      } finally {
        if (!cancelled && statusRequestRef.current === statusRequestId) {
          setLoadingStatus(false);
        }
      }

      try {
        setLoadingChart(true);
        const chartData = await apiClient.getAShareAnalysisChart({
          groupId: selectedGroupId,
          startDate: defaultChartRange?.startDate || undefined,
          endDate: defaultChartRange?.endDate || undefined,
          topN: defaultTopN,
        });
        if (!cancelled && chartRequestRef.current === chartRequestId) {
          setChart(chartData);
        }
      } catch (error) {
        if (!cancelled && chartRequestRef.current === chartRequestId) {
          toast.error(`加载股票推荐池图表失败: ${error instanceof Error ? error.message : '未知错误'}`);
        }
      } finally {
        if (!cancelled && chartRequestRef.current === chartRequestId) {
          setLoadingChart(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [defaultTopN, selectedGroupId]);

  const loadStatus = useCallback(
    async (bootstrap: boolean = false, groupId?: number) => {
      if (!groupId) {
        return null;
      }
      const requestId = statusRequestRef.current + 1;
      statusRequestRef.current = requestId;
      try {
        setLoadingStatus(true);
        const data = await apiClient.getAShareAnalysisStatus(groupId);
        if (statusRequestRef.current !== requestId) {
          return null;
        }
        setStatus(data);

        if (!initialized || bootstrap) {
          setRunDays(data.defaults.days);
          setConcurrency(data.defaults.concurrency);
          const defaultChartRange = getDefaultChartDateRange(data.summary);
          setSelectedStartDate(defaultChartRange.startDate);
          setSelectedEndDate(defaultChartRange.endDate);
          setRunStartDate('');
          setRunEndDate('');
          setResetStartDate('');
          setResetEndDate('');
          setInitialized(true);
        }
        return data;
      } catch (error) {
        if (statusRequestRef.current === requestId) {
          toast.error(`加载股票推荐池状态失败: ${error instanceof Error ? error.message : '未知错误'}`);
        }
        return null;
      } finally {
        if (statusRequestRef.current === requestId) {
          setLoadingStatus(false);
        }
      }
    },
    [initialized]
  );

  const loadChart = useCallback(
    async (options?: {
      groupId?: number;
      startDate?: string;
      endDate?: string;
      topN?: number;
    }) => {
      if (!options?.groupId) {
        return;
      }
      const requestId = chartRequestRef.current + 1;
      chartRequestRef.current = requestId;
      try {
        setLoadingChart(true);
        const data = await apiClient.getAShareAnalysisChart({
          groupId: options.groupId,
          startDate: options?.startDate,
          endDate: options?.endDate,
          topN: options?.topN ?? topN,
        });
        if (chartRequestRef.current !== requestId) {
          return;
        }
        setChart(data);
      } catch (error) {
        if (chartRequestRef.current === requestId) {
          toast.error(`加载股票推荐池图表失败: ${error instanceof Error ? error.message : '未知错误'}`);
        }
      } finally {
        if (chartRequestRef.current === requestId) {
          setLoadingChart(false);
        }
      }
    },
    [topN]
  );

  const refreshAll = useCallback(
    async (bootstrap: boolean = false, groupId?: number) => {
      const activeGroupId = groupId ?? selectedGroupId;
      if (!activeGroupId) {
        return;
      }
      const refreshedStatus = await loadStatus(bootstrap, activeGroupId);
      const defaultChartRange = bootstrap ? getDefaultChartDateRange(refreshedStatus?.summary) : null;
      await loadChart({
        groupId: activeGroupId,
        startDate: bootstrap ? defaultChartRange?.startDate || undefined : selectedStartDate || undefined,
        endDate: bootstrap ? defaultChartRange?.endDate || undefined : selectedEndDate || undefined,
        topN,
      });
    },
    [loadChart, loadStatus, selectedEndDate, selectedGroupId, selectedStartDate, topN]
  );

  return {
    chart,
    concurrency,
    loadChart,
    loadStatus,
    loadingChart,
    loadingStatus,
    refreshAll,
    resetEndDate,
    resetStartDate,
    runDays,
    runEndDate,
    runStartDate,
    selectedEndDate,
    selectedStartDate,
    setConcurrency,
    setResetEndDate,
    setResetStartDate,
    setRunDays,
    setRunEndDate,
    setRunStartDate,
    setSelectedEndDate,
    setSelectedStartDate,
    setTopN,
    status,
    topN,
  };
}
