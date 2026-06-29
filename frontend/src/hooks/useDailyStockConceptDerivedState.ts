import { useMemo } from 'react';

import type { DailyStockConceptResponse } from '@/lib/api';
import type { ConceptTrendItem } from '@/hooks/useDailyTopicAnalysisData';
import { buildDailyStockConceptViewModel } from '@/lib/daily-stock-concept-view-model';

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
  return useMemo(() => buildDailyStockConceptViewModel({
    conceptTrendItems,
    onlyRecommendationHits,
    recommendedCompanies,
    selectedConcept,
    selectedConceptDetail,
    stockConcepts,
  }), [
    conceptTrendItems,
    onlyRecommendationHits,
    recommendedCompanies,
    selectedConcept,
    selectedConceptDetail,
    stockConcepts,
  ]);
}
