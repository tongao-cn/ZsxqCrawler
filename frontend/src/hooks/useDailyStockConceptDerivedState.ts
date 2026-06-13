import { useCallback, useMemo } from 'react';

import { DailyStockConceptResponse } from '@/lib/api';
import { ConceptTrendItem } from '@/hooks/useDailyTopicAnalysisData';
import {
  isRisingTrend,
  normalizeCompanyName,
  normalizeConceptName,
  normalizeSignalTagName,
  type ConceptQualityTag,
  type ConceptStat,
} from '@/components/DailyTopicAnalysisPanelUtils';

interface UseDailyStockConceptDerivedStateOptions {
  conceptTrendItems: ConceptTrendItem[];
  onlyRecommendationHits: boolean;
  recommendedCompanies: Set<string>;
  selectedConcept: string | null;
  selectedConceptDetail: string | null;
  stockConcepts: DailyStockConceptResponse | null;
}

export function useDailyStockConceptDerivedState({
  conceptTrendItems,
  onlyRecommendationHits,
  recommendedCompanies,
  selectedConcept,
  selectedConceptDetail,
  stockConcepts,
}: UseDailyStockConceptDerivedStateOptions) {
  const { conceptStats, signalStats } = useMemo<{ conceptStats: ConceptStat[]; signalStats: ConceptStat[] }>(() => {
    const conceptMap = new Map<string, { aliases: Set<string>; stocks: Set<string>; topics: Set<string>; recommendedStocks: Set<string> }>();
    const signalMap = new Map<string, { aliases: Set<string>; stocks: Set<string>; topics: Set<string>; recommendedStocks: Set<string> }>();
    const addStat = (
      target: Map<string, { aliases: Set<string>; stocks: Set<string>; topics: Set<string>; recommendedStocks: Set<string> }>,
      concept: string,
      alias: string,
      stockName: string,
      topicIds: Array<string | number>,
      isRecommended: boolean
    ) => {
      if (!target.has(concept)) {
        target.set(concept, {
          aliases: new Set(),
          stocks: new Set(),
          topics: new Set(),
          recommendedStocks: new Set(),
        });
      }
      const item = target.get(concept);
      item?.aliases.add(alias);
      item?.stocks.add(stockName);
      topicIds.forEach((topicId) => item?.topics.add(String(topicId)));
      if (isRecommended) {
        item?.recommendedStocks.add(stockName);
      }
    };
    const toStats = (
      source: Map<string, { aliases: Set<string>; stocks: Set<string>; topics: Set<string>; recommendedStocks: Set<string> }>
    ) => Array.from(source.entries())
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
        const signalTag = normalizeSignalTagName(alias);
        if (signalTag) {
          addStat(signalMap, signalTag, alias, stockName, stock.topic_ids, recommendedCompanies.has(normalizedStockName));
        } else {
          addStat(conceptMap, normalizeConceptName(alias), alias, stockName, stock.topic_ids, recommendedCompanies.has(normalizedStockName));
        }
      }
    }

    return {
      conceptStats: toStats(conceptMap),
      signalStats: toStats(signalMap),
    };
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
      if (
        selectedConcept &&
        !stock.concepts.some((concept) => (
          normalizeSignalTagName(concept) === selectedConcept ||
          normalizeConceptName(concept) === selectedConcept
        ))
      ) {
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
    () => (
      conceptStats.find((item) => item.concept === selectedConceptDetail) ||
      signalStats.find((item) => item.concept === selectedConceptDetail) ||
      null
    ),
    [conceptStats, selectedConceptDetail, signalStats]
  );

  const selectedConceptTrend = useMemo(
    () => conceptTrendItems.find((item) => item.concept === selectedConceptDetail) || null,
    [conceptTrendItems, selectedConceptDetail]
  );

  return {
    conceptStats,
    filteredStocks,
    getConceptQualityTags,
    recommendedStockCount,
    selectedConceptStat,
    selectedConceptTrend,
    signalStats,
  };
}
