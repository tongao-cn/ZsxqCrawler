import type { DailyStockConcept, DailyStockConceptResponse } from '@/lib/api';
import {
  classifyStockConceptTerm,
  isRisingTrend,
  normalizeCompanyName,
  normalizeConceptName,
  normalizeSignalTagName,
  type ConceptQualityTag,
  type ConceptStat,
} from '@/components/DailyTopicAnalysisPanelUtils';

export interface DailyStockConceptTrendItem {
  concept: string;
  counts: number[];
}

export interface DailyStockConceptViewModelInput<TTrend extends DailyStockConceptTrendItem> {
  conceptTrendItems: TTrend[];
  onlyRecommendationHits: boolean;
  recommendedCompanies: Set<string>;
  selectedConcept: string | null;
  selectedConceptDetail: string | null;
  stockConcepts: DailyStockConceptResponse | null;
}

export interface DailyStockConceptViewModel<TTrend extends DailyStockConceptTrendItem> {
  conceptStats: ConceptStat[];
  filteredStocks: DailyStockConcept[];
  getConceptQualityTags: (stat: ConceptStat) => ConceptQualityTag[];
  recommendedStockCount: number;
  selectedConceptStat: ConceptStat | null;
  selectedConceptTrend: TTrend | null;
  selectedRelatedStats: ConceptStat[];
  signalStats: ConceptStat[];
  unmappedRawTermCount: number;
}

export interface StockConceptBadgeItem {
  name: string;
  aliases: string[];
}

interface SplitStockConceptMaps {
  industryConcepts: Map<string, string>;
  signalTags: Map<string, string>;
}

type StatBucket = {
  aliases: Set<string>;
  stocks: Set<string>;
  topics: Set<string>;
  recommendedStocks: Set<string>;
};

type StatMap = Map<string, StatBucket>;

function addStat(
  target: StatMap,
  concept: string,
  alias: string,
  stockName: string,
  topicIds: Array<string | number>,
  isRecommended: boolean
) {
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
}

function toStats(source: StatMap): ConceptStat[] {
  return Array.from(source.entries())
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
}

function splitStockConceptMaps(concepts: string[]): SplitStockConceptMaps {
  const industryConcepts = new Map<string, string>();
  const signalTags = new Map<string, string>();
  for (const rawConcept of concepts) {
    const alias = rawConcept.trim();
    if (!alias) {
      continue;
    }
    const signalTag = normalizeSignalTagName(alias);
    if (signalTag) {
      signalTags.set(signalTag, alias);
    } else {
      industryConcepts.set(normalizeConceptName(alias), alias);
    }
  }
  return { industryConcepts, signalTags };
}

function toBadgeItems(source: Map<string, Set<string>>): StockConceptBadgeItem[] {
  return Array.from(source.entries()).map(([name, aliases]) => ({
    name,
    aliases: Array.from(aliases),
  }));
}

export function splitStockConceptTerms(concepts: string[]): {
  industry: StockConceptBadgeItem[];
  signals: StockConceptBadgeItem[];
} {
  const industry = new Map<string, Set<string>>();
  const signals = new Map<string, Set<string>>();
  for (const concept of concepts) {
    const alias = concept.trim();
    if (!alias) {
      continue;
    }
    const signalTag = normalizeSignalTagName(alias);
    const target = signalTag ? signals : industry;
    const normalized = signalTag || normalizeConceptName(alias);
    if (!target.has(normalized)) {
      target.set(normalized, new Set());
    }
    target.get(normalized)?.add(alias);
  }
  return {
    industry: toBadgeItems(industry),
    signals: toBadgeItems(signals),
  };
}

function buildConceptStats(stockConcepts: DailyStockConceptResponse | null, recommendedCompanies: Set<string>) {
  const conceptMap: StatMap = new Map();
  const signalMap: StatMap = new Map();
  const unmappedRawTerms = new Set<string>();

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
      if (classifyStockConceptTerm(alias) === 'unmapped') {
        unmappedRawTerms.add(alias);
      }
      const signalTag = normalizeSignalTagName(alias);
      if (signalTag) {
        addStat(
          signalMap,
          signalTag,
          alias,
          stockName,
          stock.topic_ids,
          recommendedCompanies.has(normalizedStockName)
        );
      } else {
        addStat(
          conceptMap,
          normalizeConceptName(alias),
          alias,
          stockName,
          stock.topic_ids,
          recommendedCompanies.has(normalizedStockName)
        );
      }
    }
  }

  return {
    conceptStats: toStats(conceptMap),
    signalStats: toStats(signalMap),
    unmappedRawTermCount: unmappedRawTerms.size,
  };
}

function buildFilteredStocks(
  stockConcepts: DailyStockConceptResponse | null,
  selectedConcept: string | null,
  onlyRecommendationHits: boolean,
  recommendedCompanies: Set<string>
) {
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
}

function buildRelatedStats(
  stockConcepts: DailyStockConceptResponse | null,
  selectedConceptDetail: string | null,
  recommendedCompanies: Set<string>
) {
  if (!selectedConceptDetail) {
    return [];
  }
  const selectedIsSignal = normalizeSignalTagName(selectedConceptDetail) === selectedConceptDetail;
  const relatedMap: StatMap = new Map();
  for (const stock of stockConcepts?.stocks || []) {
    const stockName = stock.stock_name?.trim();
    if (!stockName) {
      continue;
    }
    const normalizedStockName = normalizeCompanyName(stockName);
    const { industryConcepts, signalTags } = splitStockConceptMaps(stock.concepts || []);
    const matchesSelection = selectedIsSignal
      ? signalTags.has(selectedConceptDetail)
      : industryConcepts.has(selectedConceptDetail);
    if (!matchesSelection) {
      continue;
    }
    const relatedItems = selectedIsSignal ? industryConcepts : signalTags;
    relatedItems.forEach((alias, concept) => {
      addStat(
        relatedMap,
        concept,
        alias,
        stockName,
        stock.topic_ids,
        recommendedCompanies.has(normalizedStockName)
      );
    });
  }
  return toStats(relatedMap).slice(0, 8);
}

function buildQualityTagGetter<TTrend extends DailyStockConceptTrendItem>(conceptTrendItems: TTrend[]) {
  const conceptTrendMap = new Map(conceptTrendItems.map((item) => [item.concept, item]));
  return (stat: ConceptStat): ConceptQualityTag[] => {
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
  };
}

export function buildDailyStockConceptViewModel<TTrend extends DailyStockConceptTrendItem>({
  conceptTrendItems,
  onlyRecommendationHits,
  recommendedCompanies,
  selectedConcept,
  selectedConceptDetail,
  stockConcepts,
}: DailyStockConceptViewModelInput<TTrend>): DailyStockConceptViewModel<TTrend> {
  const { conceptStats, signalStats, unmappedRawTermCount } = buildConceptStats(stockConcepts, recommendedCompanies);
  const filteredStocks = buildFilteredStocks(
    stockConcepts,
    selectedConcept,
    onlyRecommendationHits,
    recommendedCompanies
  );

  return {
    conceptStats,
    filteredStocks,
    getConceptQualityTags: buildQualityTagGetter(conceptTrendItems),
    recommendedStockCount: filteredStocks.filter((stock) => (
      recommendedCompanies.has(normalizeCompanyName(stock.stock_name))
    )).length,
    selectedConceptStat: (
      conceptStats.find((item) => item.concept === selectedConceptDetail) ||
      signalStats.find((item) => item.concept === selectedConceptDetail) ||
      null
    ),
    selectedConceptTrend: conceptTrendItems.find((item) => item.concept === selectedConceptDetail) || null,
    selectedRelatedStats: buildRelatedStats(stockConcepts, selectedConceptDetail, recommendedCompanies),
    signalStats,
    unmappedRawTermCount,
  };
}
