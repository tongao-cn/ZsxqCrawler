'use client';

import { useState } from 'react';
import { RefreshCw, TrendingUp } from 'lucide-react';

import { DailyStockConcept, DailyStockConceptResponse } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { DatePickerButton } from '@/components/ui/date-picker-button';
import { Label } from '@/components/ui/label';
import type { ConceptTrendItem } from '@/hooks/useDailyTopicAnalysisData';
import DailyStockConceptDetailCard from '@/components/DailyStockConceptDetailCard';
import DailyStockConceptStockTable from '@/components/DailyStockConceptStockTable';
import {
  DEFAULT_VISIBLE_CONCEPT_COUNT,
  formatDateTime,
  getTodayText,
  type ConceptQualityTag,
  type ConceptStat,
} from '@/components/DailyTopicAnalysisPanelUtils';

interface DailyStockConceptsViewProps {
  conceptStats: ConceptStat[];
  conceptTrendDates: string[];
  extractingStocks: boolean;
  filteredStocks: DailyStockConcept[];
  getConceptQualityTags: (stat: ConceptStat) => ConceptQualityTag[];
  loadingRecommendations: boolean;
  loadingStockConcepts: boolean;
  onClearConcept: () => void;
  onConceptSelect: (concept: string) => void;
  onExtract: () => void;
  onOpenStockDetail: (stock: DailyStockConcept) => void;
  onOpenTopicDetail: (topicId: string | number) => void;
  onRefresh: () => void;
  onReportDateChange: (date: string) => void;
  onToggleRecommendationHits: () => void;
  onlyRecommendationHits: boolean;
  recommendedCompanies: Set<string>;
  recommendedStockCount: number;
  reportDate: string;
  selectedConcept: string | null;
  selectedConceptStat: ConceptStat | null;
  selectedConceptTrend: ConceptTrendItem | null;
  selectedRelatedStats: ConceptStat[];
  signalStats: ConceptStat[];
  stockConcepts: DailyStockConceptResponse | null;
  unmappedRawTermCount: number;
}

function ConceptList({
  conceptStats,
  getConceptQualityTags,
  onConceptSelect,
  selectedConcept,
}: {
  conceptStats: ConceptStat[];
  getConceptQualityTags: (stat: ConceptStat) => ConceptQualityTag[];
  onConceptSelect: (concept: string) => void;
  selectedConcept: string | null;
}) {
  return (
    <div className="flex flex-col gap-2 p-3">
      {conceptStats.slice(0, DEFAULT_VISIBLE_CONCEPT_COUNT).map((item, index) => {
        const selected = selectedConcept === item.concept;
        const qualityTags = getConceptQualityTags(item);
        return (
          <button
            key={item.concept}
            type="button"
            onClick={() => onConceptSelect(item.concept)}
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
}

export default function DailyStockConceptsView({
  conceptStats,
  conceptTrendDates,
  extractingStocks,
  filteredStocks,
  getConceptQualityTags,
  loadingRecommendations,
  loadingStockConcepts,
  onClearConcept,
  onConceptSelect,
  onExtract,
  onOpenStockDetail,
  onOpenTopicDetail,
  onRefresh,
  onReportDateChange,
  onToggleRecommendationHits,
  onlyRecommendationHits,
  recommendedCompanies,
  recommendedStockCount,
  reportDate,
  selectedConcept,
  selectedConceptStat,
  selectedConceptTrend,
  selectedRelatedStats,
  signalStats,
  stockConcepts,
  unmappedRawTermCount,
}: DailyStockConceptsViewProps) {
  const [listMode, setListMode] = useState<'concept' | 'signal'>('concept');
  const activeStats = listMode === 'concept' ? conceptStats : signalStats;
  const activeTitle = listMode === 'concept' ? '概念榜' : '信号榜';
  const activeDescription = listMode === 'concept'
    ? `按去重来源话题数排序，共 ${conceptStats.length} 个概念`
    : `按去重来源话题数排序，共 ${signalStats.length} 个信号`;

  return (
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
                    <div className="flex items-center justify-between gap-2">
                      <div className="text-sm font-medium">{activeTitle}</div>
                      <div className="inline-flex rounded-md border border-gray-200 bg-gray-50 p-0.5">
                        <button
                          type="button"
                          onClick={() => setListMode('concept')}
                          className={`rounded px-2 py-1 text-xs ${
                            listMode === 'concept' ? 'bg-white text-gray-900 shadow-sm' : 'text-muted-foreground'
                          }`}
                        >
                          概念
                        </button>
                        <button
                          type="button"
                          onClick={() => setListMode('signal')}
                          className={`rounded px-2 py-1 text-xs ${
                            listMode === 'signal' ? 'bg-white text-gray-900 shadow-sm' : 'text-muted-foreground'
                          }`}
                        >
                          信号
                        </button>
                      </div>
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {activeDescription}
                    </div>
                  </div>
                  <div className="xl:max-h-[640px] xl:overflow-y-auto">
                    <ConceptList
                      conceptStats={activeStats}
                      getConceptQualityTags={getConceptQualityTags}
                      onConceptSelect={onConceptSelect}
                      selectedConcept={selectedConcept}
                    />
                  </div>
                </div>

                <div className="flex min-w-0 flex-col gap-4">
                  <div className="rounded-md border border-gray-200 p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
                      <div className="text-muted-foreground">
                        当前展示 {filteredStocks.length} / {stockConcepts.stocks.length} 只股票
                        {selectedConcept ? `，当前筛选：${selectedConcept}` : ''}
                        {onlyRecommendationHits ? '，仅看推荐池命中' : ''}
                        {loadingRecommendations ? '，推荐池命中加载中...' : `，推荐池命中 ${recommendedStockCount} 只`}
                      </div>
                    </div>
                  </div>

                  <div className="rounded-md border border-gray-200 p-3">
                    <DailyStockConceptDetailCard
                      conceptTrendDates={conceptTrendDates}
                      getConceptQualityTags={getConceptQualityTags}
                      onOpenTopicDetail={onOpenTopicDetail}
                      selectedConceptStat={selectedConceptStat}
                      selectedConceptTrend={selectedConceptTrend}
                      selectedRelatedStats={selectedRelatedStats}
                    />
                  </div>

                  <DailyStockConceptStockTable
                    filteredStocks={filteredStocks}
                    onConceptSelect={onConceptSelect}
                    onOpenStockDetail={onOpenStockDetail}
                    onOpenTopicDetail={onOpenTopicDetail}
                    recommendedCompanies={recommendedCompanies}
                    selectedConcept={selectedConcept}
                  />
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
                onChange={(value) => onReportDateChange(value || getTodayText())}
              />
            </div>

            <div className="grid grid-cols-2 gap-2">
              <Button variant="outline" onClick={onRefresh} disabled={loadingStockConcepts}>
                <RefreshCw className={loadingStockConcepts ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} />
                刷新
              </Button>
              <Button onClick={onExtract} disabled={extractingStocks}>
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
                <div className="text-xs text-muted-foreground">信号</div>
                <div className="mt-1 font-semibold">{signalStats.length}</div>
              </div>
              <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
                <div className="text-xs text-muted-foreground">未归并</div>
                <div className="mt-1 font-semibold">{unmappedRawTermCount}</div>
              </div>
              <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
                <div className="text-xs text-muted-foreground">推荐命中</div>
                <div className="mt-1 font-semibold">{loadingRecommendations ? '...' : recommendedStockCount}</div>
              </div>
            </div>

            <div className="flex flex-col gap-2 border-t border-gray-200 pt-4">
              <Button
                variant={onlyRecommendationHits ? 'default' : 'outline'}
                onClick={onToggleRecommendationHits}
                disabled={loadingRecommendations}
              >
                {onlyRecommendationHits ? '显示全部股票' : '只看推荐池命中'}
              </Button>
              {selectedConcept && (
                <Button variant="outline" onClick={onClearConcept}>
                  清除当前概念
                </Button>
              )}
            </div>

            <div className="rounded-md bg-gray-50 p-3 text-xs leading-5 text-muted-foreground">
              {selectedConcept ? `当前筛选：${selectedConcept}` : '当前未筛选'}
              <br />
              更新时间：{formatDateTime(stockConcepts?.updated_at)}
            </div>
          </CardContent>
        </Card>
      </aside>
    </div>
  );
}
