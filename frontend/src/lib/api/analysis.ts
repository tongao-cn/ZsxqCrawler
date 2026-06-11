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

  async runAShareAnalysis(payload: AShareAnalysisRunPayload) {
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
