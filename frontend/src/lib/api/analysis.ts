import { TasksApiClient } from './tasks';
import type {
  AShareAnalysisChart,
  AShareAnalysisExportTdxPayload,
  AShareAnalysisExportTdxResponse,
  AShareAnalysisResetPayload,
  AShareAnalysisRunPayload,
  AShareAnalysisStatus,
  DailyStockConceptResponse,
  DailyTopicAnalysisPayload,
  DailyTopicReport,
  StockTopicBatchAnalysisResponse,
  StockTopicAnalysisResponse,
  StockTopicImageExtractResponse,
  StockQuestionResponse,
} from './analysisTypes';
import type { TaskCreateResponse } from './taskTypes';
import type { ApiRequestOptions } from './client';

function normalizeOptionalId(value?: string | number) {
  if (value === undefined || value === null) {
    return undefined;
  }
  const normalized = String(value).trim();
  return normalized || undefined;
}

function getStockTopicReadModelKey(result: StockTopicAnalysisResponse) {
  return result.stock_name.trim();
}

function mergeStockTopicSearchAndLatest(
  searchResult: StockTopicAnalysisResponse,
  latestResult: StockTopicAnalysisResponse | null,
): StockTopicAnalysisResponse {
  const latestTopicIds = new Set(
    (latestResult?.processed_topic_ids || latestResult?.analyzed_topic_ids || []).map(String),
  );
  const newTopicCount = searchResult.topics.filter((topic) => !latestTopicIds.has(String(topic.topic_id))).length;
  if (!latestResult || latestResult.status === 'missing') {
    return {
      ...searchResult,
      processed_topic_ids: [],
      analyzed_topic_ids: [],
      new_topic_count: searchResult.topic_count,
      analysis_mode: 'initialize',
    };
  }
  return {
    ...searchResult,
    concepts: latestResult.concepts.length > 0 ? latestResult.concepts : searchResult.concepts,
    recommendation_count: latestResult.recommendation_count || searchResult.recommendation_count,
    summary_markdown: latestResult.summary_markdown,
    model: latestResult.model,
    status: latestResult.status,
    error: latestResult.error,
    created_at: latestResult.created_at,
    updated_at: latestResult.updated_at,
    processed_topic_ids: Array.from(latestTopicIds),
    analyzed_topic_ids: Array.from(latestTopicIds),
    new_topic_count: newTopicCount,
    analysis_mode: newTopicCount > 0 ? 'incremental' : 'up_to_date',
  };
}

function mergeStockTopicReadModels(
  stockNames: string[],
  searchResults: StockTopicAnalysisResponse[],
  latestBatch: StockTopicBatchAnalysisResponse,
) {
  const latestByName = new Map(
    latestBatch.stocks.map((item) => [getStockTopicReadModelKey(item), item]),
  );
  return searchResults.map((searchResult, index) => {
    const latest = latestBatch.stocks[index]
      || latestByName.get(getStockTopicReadModelKey(searchResult))
      || latestByName.get(stockNames[index])
      || null;
    return mergeStockTopicSearchAndLatest(searchResult, latest);
  });
}

export class AnalysisApiClient extends TasksApiClient {
  async getAShareAnalysisStatus(groupId?: string | number): Promise<AShareAnalysisStatus> {
    const search = new URLSearchParams();
    if (groupId !== undefined && groupId !== null && String(groupId).trim() !== '') {
      search.set('group_id', String(groupId));
    }
    const query = search.toString();
    return this.request(`/api/analytics/a-share/status${query ? `?${query}` : ''}`);
  }

  async getAShareAnalysisChart(params?: {
    groupId?: string | number;
    startDate?: string;
    endDate?: string;
    topN?: number;
  }, options: ApiRequestOptions = {}): Promise<AShareAnalysisChart> {
    const search = new URLSearchParams();
    if (params?.groupId !== undefined && params?.groupId !== null && String(params.groupId).trim() !== '') {
      search.set('group_id', String(params.groupId));
    }
    if (params?.startDate) {
      search.set('start_date', params.startDate);
    }
    if (params?.endDate) {
      search.set('end_date', params.endDate);
    }
    if (params?.topN) {
      search.set('top_n', params.topN.toString());
    }
    const query = search.toString();
    return this.request(`/api/analytics/a-share/chart${query ? `?${query}` : ''}`, {
      signal: options.signal,
    });
  }

  async runAShareAnalysis(payload: AShareAnalysisRunPayload): Promise<TaskCreateResponse> {
    const groupId = normalizeOptionalId(payload.group_id);
    return this.request('/api/analytics/a-share/run', {
      method: 'POST',
      body: JSON.stringify({
        ...payload,
        ...(groupId ? { group_id: groupId } : {}),
      }),
    });
  }

  async resetAShareAnalysisRange(payload: AShareAnalysisResetPayload) {
    const groupId = normalizeOptionalId(payload.group_id);
    return this.request('/api/analytics/a-share/reset-range', {
      method: 'POST',
      body: JSON.stringify({
        ...payload,
        ...(groupId ? { group_id: groupId } : {}),
      }),
    });
  }

  async exportAShareRankingsToTdx(
    payload: AShareAnalysisExportTdxPayload = {}
  ): Promise<AShareAnalysisExportTdxResponse> {
    const groupId = normalizeOptionalId(payload.group_id);
    return this.request('/api/analytics/a-share/export-tdx', {
      method: 'POST',
      body: JSON.stringify({
        ...payload,
        ...(groupId ? { group_id: groupId } : {}),
      }),
    });
  }

  async runDailyTopicAnalysisToday(
    groupId: number | string,
    payload: DailyTopicAnalysisPayload = {}
  ): Promise<TaskCreateResponse> {
    return this.request(`/api/analysis/daily/run-today/${groupId}`, {
      method: 'POST',
      body: JSON.stringify({
        commentsPerTopic: payload.commentsPerTopic ?? 0,
        crawlLatestFirst: payload.crawlLatestFirst ?? true,
        ...(payload.date ? { date: payload.date } : {}),
      }),
    });
  }

  async createDailyTopicAnalysis(
    groupId: number | string,
    payload: DailyTopicAnalysisPayload = {}
  ): Promise<TaskCreateResponse> {
    return this.request(`/api/analysis/daily/${groupId}`, {
      method: 'POST',
      body: JSON.stringify({
        commentsPerTopic: payload.commentsPerTopic ?? 0,
        ...(payload.date ? { date: payload.date } : {}),
      }),
    });
  }

  async getDailyTopicReport(groupId: number | string, date?: string, options: ApiRequestOptions = {}): Promise<DailyTopicReport> {
    const search = new URLSearchParams();
    if (date) {
      search.set('date', date);
    }
    const query = search.toString();
    return this.request(`/api/analysis/daily/${groupId}${query ? `?${query}` : ''}`, {
      signal: options.signal,
    });
  }

  async createDailyStockConcepts(
    groupId: number | string,
    payload: DailyTopicAnalysisPayload = {}
  ): Promise<TaskCreateResponse> {
    return this.request(`/api/analysis/daily-stock-concepts/${groupId}`, {
      method: 'POST',
      body: JSON.stringify({
        commentsPerTopic: payload.commentsPerTopic ?? 0,
        ...(payload.date ? { date: payload.date } : {}),
      }),
    });
  }

  async getDailyStockConcepts(groupId: number | string, date?: string, options: ApiRequestOptions = {}): Promise<DailyStockConceptResponse> {
    const search = new URLSearchParams();
    if (date) {
      search.set('date', date);
    }
    const query = search.toString();
    return this.request(`/api/analysis/daily-stock-concepts/${groupId}${query ? `?${query}` : ''}`, {
      signal: options.signal,
    });
  }

  async searchStockTopics(groupId: number | string, stockName: string, options: ApiRequestOptions = {}): Promise<StockTopicAnalysisResponse> {
    const search = new URLSearchParams({ stock_name: stockName });
    return this.request(`/api/analysis/stock-topics/${groupId}?${search}`, {
      signal: options.signal,
    });
  }

  async analyzeStockTopics(groupId: number | string, stockName: string): Promise<TaskCreateResponse> {
    return this.request(`/api/analysis/stock-topics/${groupId}/analyze`, {
      method: 'POST',
      body: JSON.stringify({ stockName }),
    });
  }

  async analyzeStockTopicsBatch(groupId: number | string, stockNames: string[]): Promise<TaskCreateResponse> {
    return this.request(`/api/analysis/stock-topics/${groupId}/analyze-batch`, {
      method: 'POST',
      body: JSON.stringify({ stockNames }),
    });
  }

  async extractStockTopicsFromImage(imageDataUrl: string): Promise<StockTopicImageExtractResponse> {
    return this.request('/api/analysis/stock-topics/extract-stocks-from-image', {
      method: 'POST',
      body: JSON.stringify({ imageDataUrl }),
    });
  }

  async getLatestStockTopicAnalysis(groupId: number | string, stockName: string, options: ApiRequestOptions = {}): Promise<StockTopicAnalysisResponse> {
    const search = new URLSearchParams({ stock_name: stockName });
    return this.request(`/api/analysis/stock-topics/${groupId}/latest?${search}`, {
      signal: options.signal,
    });
  }

  async getLatestStockTopicAnalyses(groupId: number | string, stockNames: string[], options: ApiRequestOptions = {}): Promise<StockTopicBatchAnalysisResponse> {
    const search = new URLSearchParams({ stock_names: stockNames.join('、') });
    return this.request(`/api/analysis/stock-topics/${groupId}/latest-batch?${search}`, {
      signal: options.signal,
    });
  }

  async loadStockTopicAnalysisReadModels(
    groupId: number | string,
    stockNames: string[],
    options: ApiRequestOptions = {},
  ): Promise<StockTopicAnalysisResponse[]> {
    const [searchResults, latestBatch] = await Promise.all([
      Promise.all(stockNames.map((stockName) => this.searchStockTopics(groupId, stockName, options))),
      this.getLatestStockTopicAnalyses(groupId, stockNames, options),
    ]);
    return mergeStockTopicReadModels(stockNames, searchResults, latestBatch);
  }

  async searchStockQuestionTopics(groupId: number | string, question: string, options: ApiRequestOptions = {}): Promise<StockQuestionResponse> {
    const search = new URLSearchParams({ question });
    return this.request(`/api/analysis/stock-topics/${groupId}/questions?${search}`, {
      signal: options.signal,
    });
  }

  async analyzeStockQuestion(groupId: number | string, question: string): Promise<TaskCreateResponse> {
    return this.request(`/api/analysis/stock-topics/${groupId}/questions/analyze`, {
      method: 'POST',
      body: JSON.stringify({ question }),
    });
  }
}
