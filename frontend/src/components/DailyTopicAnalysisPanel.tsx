'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { RefreshCw, TrendingUp } from 'lucide-react';
import { toast } from 'sonner';

import { apiClient, DailyStockConcept, TopicDetail } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { DatePickerButton } from '@/components/ui/date-picker-button';
import DailyTopicReportView from '@/components/DailyTopicReportView';
import DailyStockDetailDialog, { type StockTrendDay } from '@/components/DailyStockDetailDialog';
import DailyTopicDetailDialog from '@/components/DailyTopicDetailDialog';
import { Label } from '@/components/ui/label';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { useDailyTopicAnalysisData } from '@/hooks/useDailyTopicAnalysisData';
import {
  DEFAULT_VISIBLE_CONCEPT_COUNT,
  formatDateTime,
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

  const visibleConceptStats = conceptStats.slice(0, DEFAULT_VISIBLE_CONCEPT_COUNT);
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

  const renderTopicButtons = (topicIds: Array<string | number>) => (
    <div className="flex flex-wrap gap-1">
      {topicIds.length > 0 ? (
        topicIds.map((topicId) => (
          <Button
            key={String(topicId)}
            variant="link"
            size="sm"
            className="h-auto px-0 py-0 text-xs"
            onClick={() => void openTopicDetail(topicId)}
          >
            {String(topicId)}
          </Button>
        ))
      ) : (
        <span className="text-muted-foreground">-</span>
      )}
    </div>
  );

  const renderConceptList = () => (
    <div className="flex flex-col gap-2 p-3">
      {visibleConceptStats.map((item, index) => {
        const selected = selectedConcept === item.concept;
        const qualityTags = getConceptQualityTags(item);
        return (
          <button
            key={item.concept}
            type="button"
            onClick={() => openConceptDetail(item.concept)}
            className={`w-full rounded-md border p-3 text-left transition-colors ${
              selected
                ? 'border-blue-300 bg-blue-50'
                : 'border-gray-200 bg-white hover:bg-gray-50'
            }`}
          >
            <div className="flex items-start gap-2">
              <span className="mt-0.5 w-6 text-sm text-muted-foreground">{index + 1}</span>
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-medium" title={item.concept}>
                  {item.concept}
                </div>
                {item.aliases.length > 1 && (
                  <div className="mt-1 truncate text-xs text-muted-foreground" title={item.aliases.join(' / ')}>
                    含 {item.aliases.slice(0, 3).join(' / ')}
                    {item.aliases.length > 3 ? ` 等 ${item.aliases.length} 个` : ''}
                  </div>
                )}
                <div className="mt-2 flex flex-wrap gap-1">
                  <Badge variant="secondary">话题 {item.topicCount}</Badge>
                  <Badge variant="outline">股 {item.stockCount}</Badge>
                  {item.recommendationHitCount > 0 && (
                    <Badge className="bg-emerald-100 text-emerald-800">推 {item.recommendationHitCount}</Badge>
                  )}
                </div>
                {qualityTags.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {qualityTags.slice(0, 2).map((tag) => (
                      <Badge key={`${item.concept}-${tag.label}`} className={tag.className}>
                        {tag.label}
                      </Badge>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </button>
        );
      })}
    </div>
  );

  return (
    <div className="flex flex-col gap-4 p-1">
      {mode === 'stock-concepts' ? (
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px] xl:items-start">
          <Card className="border border-gray-200 shadow-none">
            <CardHeader>
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <CardTitle className="flex items-center gap-2">
                    <TrendingUp className="h-5 w-5" />
                    股票概念视图
                  </CardTitle>
                  <CardDescription>
                    基于 A 股推荐池的话题级抽取明细，汇总当天股票、概念和来源话题
                  </CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent>
          {stockConcepts && stockConcepts.stocks.length > 0 ? (
            <div className="flex flex-col gap-4">
              <div className="grid gap-4 xl:grid-cols-[340px_minmax(0,1fr)]">
                <div className="rounded-md border border-gray-200">
                  <div className="border-b border-gray-200 p-3">
                    <div className="text-sm font-medium">概念榜</div>
                    <div className="text-xs text-muted-foreground">
                      按去重来源话题数排序，共 {conceptStats.length} 个概念
                    </div>
                  </div>
                  <div className="xl:max-h-[640px] xl:overflow-y-auto">
                    {renderConceptList()}
                  </div>
                </div>

                <div className="flex min-w-0 flex-col gap-4">
                  <div className="rounded-md border border-gray-200 p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
                      <div className="text-muted-foreground">
                        当前展示 {filteredStocks.length} / {stockConcepts.stocks.length} 只股票
                        {selectedConcept ? `，当前概念：${selectedConcept}` : ''}
                        {onlyRecommendationHits ? '，仅看推荐池命中' : ''}
                        {loadingRecommendations ? '，推荐池命中加载中...' : `，推荐池命中 ${recommendedStockCount} 只`}
                      </div>
                    </div>
                  </div>

                  <div className="rounded-md border border-gray-200 p-3">
                    {selectedConceptStat ? (
                      <div className="flex flex-col gap-4">
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div>
                            <div className="text-base font-semibold">{selectedConceptStat.concept}</div>
                            <div className="mt-1 text-xs text-muted-foreground">选中概念详情</div>
                          </div>
                          <div className="flex flex-wrap gap-1">
                            {getConceptQualityTags(selectedConceptStat).map((tag) => (
                              <Badge key={`${selectedConceptStat.concept}-detail-${tag.label}`} className={tag.className}>
                                {tag.label}
                              </Badge>
                            ))}
                          </div>
                        </div>
                        {selectedConceptStat.aliases.length > 1 && (
                          <div>
                            <div className="mb-2 text-sm font-medium">合并概念</div>
                            <div className="flex flex-wrap gap-1">
                              {selectedConceptStat.aliases.map((alias) => (
                                <Badge key={`${selectedConceptStat.concept}-alias-${alias}`} variant="outline">
                                  {alias}
                                </Badge>
                              ))}
                            </div>
                          </div>
                        )}
                        <div className="grid gap-3 md:grid-cols-4">
                          <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
                            <div className="text-xs text-muted-foreground">来源话题</div>
                            <div className="mt-1 font-medium">{selectedConceptStat.topicCount}</div>
                          </div>
                          <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
                            <div className="text-xs text-muted-foreground">相关股票</div>
                            <div className="mt-1 font-medium">{selectedConceptStat.stockCount}</div>
                          </div>
                          <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
                            <div className="text-xs text-muted-foreground">推荐池命中</div>
                            <div className="mt-1 font-medium">{selectedConceptStat.recommendationHitCount}</div>
                          </div>
                          <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
                            <div className="text-xs text-muted-foreground">7 天累计话题</div>
                            <div className="mt-1 font-medium">{selectedConceptTrend?.total ?? 0}</div>
                          </div>
                        </div>
                        <div>
                          <div className="mb-2 text-sm font-medium">近 7 天趋势</div>
                          {selectedConceptTrend ? (
                            <div className="overflow-x-auto">
                              <Table>
                                <TableHeader>
                                  <TableRow>
                                    {conceptTrendDates.map((date) => (
                                      <TableHead key={date} className="text-right">
                                        {date.slice(5)}
                                      </TableHead>
                                    ))}
                                    <TableHead className="text-right">合计</TableHead>
                                  </TableRow>
                                </TableHeader>
                                <TableBody>
                                  <TableRow>
                                    {selectedConceptTrend.counts.map((count, index) => (
                                      <TableCell key={`${selectedConceptStat.concept}-trend-${conceptTrendDates[index]}`} className="text-right tabular-nums">
                                        {count ? `${count} (${selectedConceptTrend.stockCounts[index]})` : '-'}
                                      </TableCell>
                                    ))}
                                    <TableCell className="text-right font-medium tabular-nums">
                                      {selectedConceptTrend.total} ({selectedConceptTrend.stockTotal})
                                    </TableCell>
                                  </TableRow>
                                </TableBody>
                              </Table>
                            </div>
                          ) : (
                            <div className="text-sm text-muted-foreground">暂无近 7 天趋势数据</div>
                          )}
                        </div>
                        <div>
                          <div className="mb-2 text-sm font-medium">来源话题</div>
                          <div className="flex flex-wrap gap-2 rounded-md bg-gray-50 p-3">
                            {selectedConceptStat.topicIds.map((topicId) => (
                              <Button
                                key={String(topicId)}
                                variant="link"
                                size="sm"
                                className="h-auto px-0 py-0"
                                onClick={() => void openTopicDetail(topicId)}
                              >
                                {String(topicId)}
                              </Button>
                            ))}
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div className="flex h-40 items-center justify-center rounded-md border border-dashed border-gray-300 text-sm text-muted-foreground">
                        从左侧选择一个概念查看详情
                      </div>
                    )}
                  </div>

                  <ScrollArea className="h-[420px] rounded-md border border-gray-200">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>股票</TableHead>
                          <TableHead>代码</TableHead>
                          <TableHead>推荐池</TableHead>
                          <TableHead>概念</TableHead>
                          <TableHead>来源话题</TableHead>
                          <TableHead>置信度</TableHead>
                          <TableHead>理由</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {filteredStocks.map((stock) => (
                          <TableRow key={`${stock.stock_name}-${stock.stock_code || 'unknown'}`}>
                            <TableCell>
                              <Button
                                variant="link"
                                className="h-auto px-0 py-0 font-medium"
                                onClick={() => void openStockDetail(stock)}
                              >
                                {stock.stock_name}
                              </Button>
                            </TableCell>
                            <TableCell>
                              {stock.stock_code ? `${stock.stock_code}${stock.market ? `.${stock.market}` : ''}` : '未匹配'}
                            </TableCell>
                            <TableCell>
                              {recommendedCompanies.has(normalizeCompanyName(stock.stock_name)) ? (
                                <Badge className="bg-emerald-100 text-emerald-800">命中</Badge>
                              ) : (
                                <span className="text-muted-foreground">-</span>
                              )}
                            </TableCell>
                            <TableCell className="max-w-xs whitespace-normal">
                              <div className="flex flex-wrap gap-1">
                                {stock.concepts.map((concept) => {
                                  const normalizedConcept = normalizeConceptName(concept);
                                  return (
                                    <Badge
                                      key={concept}
                                      variant={normalizedConcept === selectedConcept ? 'default' : 'secondary'}
                                      className="cursor-pointer"
                                      onClick={() => openConceptDetail(normalizedConcept)}
                                      title={normalizedConcept !== concept ? `已合并到：${normalizedConcept}` : concept}
                                    >
                                      {concept}
                                      {normalizedConcept !== concept ? ` -> ${normalizedConcept}` : ''}
                                    </Badge>
                                  );
                                })}
                              </div>
                            </TableCell>
                            <TableCell className="max-w-[180px] whitespace-normal">
                              {renderTopicButtons(stock.topic_ids)}
                            </TableCell>
                            <TableCell>{Math.round((stock.confidence || 0) * 100)}%</TableCell>
                            <TableCell className="max-w-md whitespace-normal text-muted-foreground">
                              {stock.reason || '-'}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </ScrollArea>
                </div>
              </div>
            </div>
          ) : (
            <div className="flex h-40 items-center justify-center rounded-md border border-dashed border-gray-300 text-sm text-muted-foreground">
              还没有当天股票概念视图，请先运行股票推荐池，或点击右侧按钮从已有结果生成
            </div>
          )}
          {stockConcepts?.updated_at && (
            <div className="mt-3 text-xs text-muted-foreground">
              更新时间：{formatDateTime(stockConcepts.updated_at)}
            </div>
          )}
            </CardContent>
          </Card>
          <aside className="xl:sticky xl:top-4">
            <Card className="border border-gray-200 shadow-none">
              <CardHeader>
                <CardTitle className="text-base">概念视图操作</CardTitle>
                <CardDescription>选择日期，从推荐池抽取明细生成当天概念视图</CardDescription>
              </CardHeader>
              <CardContent className="flex flex-col gap-4">
                <div className="flex flex-col gap-2">
                  <Label htmlFor="daily-stock-concepts-date">报告日期</Label>
                  <DatePickerButton
                    value={reportDate}
                    onChange={(value) => setReportDate(value || getTodayText())}
                  />
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <Button variant="outline" onClick={() => void loadStockConcepts()} disabled={loadingStockConcepts}>
                    <RefreshCw className={loadingStockConcepts ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} />
                    刷新
                  </Button>
                  <Button onClick={handleExtractStockConcepts} disabled={extractingStocks}>
                    {extractingStocks ? (
                      <RefreshCw className="h-4 w-4 animate-spin" />
                    ) : (
                      <TrendingUp className="h-4 w-4" />
                    )}
                    生成视图
                  </Button>
                </div>

                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
                    <div className="text-xs text-muted-foreground">概念</div>
                    <div className="mt-1 font-semibold">{conceptStats.length}</div>
                  </div>
                  <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
                    <div className="text-xs text-muted-foreground">股票</div>
                    <div className="mt-1 font-semibold">{stockConcepts?.stocks.length ?? 0}</div>
                  </div>
                  <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
                    <div className="text-xs text-muted-foreground">当前展示</div>
                    <div className="mt-1 font-semibold">{filteredStocks.length}</div>
                  </div>
                  <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
                    <div className="text-xs text-muted-foreground">推荐命中</div>
                    <div className="mt-1 font-semibold">{loadingRecommendations ? '...' : recommendedStockCount}</div>
                  </div>
                </div>

                <div className="flex flex-col gap-2 border-t border-gray-200 pt-4">
                  <Button
                    variant={onlyRecommendationHits ? 'default' : 'outline'}
                    onClick={() => setOnlyRecommendationHits((value) => !value)}
                    disabled={loadingRecommendations}
                  >
                    {onlyRecommendationHits ? '显示全部股票' : '只看推荐池命中'}
                  </Button>
                  {selectedConcept && (
                    <Button
                      variant="outline"
                      onClick={() => {
                        setSelectedConcept(null);
                        setSelectedConceptDetail(null);
                      }}
                    >
                      清除当前概念
                    </Button>
                  )}
                </div>

                <div className="rounded-md bg-gray-50 p-3 text-xs leading-5 text-muted-foreground">
                  {selectedConcept ? `当前概念：${selectedConcept}` : '当前未筛选概念'}
                  <br />
                  更新时间：{formatDateTime(stockConcepts?.updated_at)}
                </div>
              </CardContent>
            </Card>
          </aside>
        </div>
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
