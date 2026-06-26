import type { Task } from './taskTypes';

export interface DailyTopicReport {
  group_id: string;
  report_date: string;
  topic_count: number;
  model?: string | null;
  prompt_version?: string | null;
  summary_markdown?: string | null;
  raw_json?: {
    report_path?: string;
    topic_ids?: Array<string | number>;
    [key: string]: unknown;
  };
  status: string;
  error?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface DailyTopicAnalysisPayload {
  date?: string;
  commentsPerTopic?: number;
  crawlLatestFirst?: boolean;
}

export interface DailyStockConcept {
  stock_name: string;
  stock_code: string;
  market: string;
  concepts: string[];
  reason: string;
  topic_ids: Array<string | number>;
  confidence: number;
  model?: string;
}

export interface DailyStockConceptResponse {
  group_id: string;
  report_date: string;
  stocks: DailyStockConcept[];
  status: string;
  error?: string | null;
  updated_at?: string | null;
}

export interface ResearchRadarRequestPayload {
  date?: string;
  commentsPerTopic?: number;
}

export interface ResearchRadarEvidence {
  id?: number;
  source_type: string;
  source_id: string;
  topic_id: string;
  source_time: string;
  excerpt: string;
  matched_entities: Record<string, unknown>;
  support_reason: string;
  navigation: {
    type?: string;
    topic_id?: string | number;
    [key: string]: unknown;
  };
}

export interface ResearchRadarEntity {
  entity_type: string;
  name: string;
  code?: string;
  market?: string;
  weight: number;
  evidence_count: number;
}

export interface ResearchRadarLogicItem {
  id?: number;
  rank: number;
  tier: 'strong' | 'medium' | 'weak' | string;
  title: string;
  summary: string;
  direction: string;
  concepts: string[];
  stocks: Array<{
    name: string;
    code?: string;
    market?: string;
    confidence?: number;
  }>;
  catalysts: string[];
  risks: string[];
  evidence_count: number;
  confidence: number;
  evidence: ResearchRadarEvidence[];
  entities: ResearchRadarEntity[];
}

export interface ResearchRadarRun {
  id: number;
  group_id: string;
  report_date: string;
  window_days: number;
  status: string;
  model?: string | null;
  summary: {
    logic_count?: number;
    strong_count?: number;
    medium_count?: number;
    weak_count?: number;
    direction_count?: number;
    stock_count?: number;
    [key: string]: unknown;
  };
  task_id?: string | null;
  error?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  logic_items: ResearchRadarLogicItem[];
}

export interface StockTopicMatch {
  topic_id: string;
  title: string;
  create_time: string;
  likes_count: number;
  comments_count: number;
  reading_count: number;
  content_preview: string;
  concepts: string[];
  reasons: string[];
  confidence: number;
  recommendation_count: number;
}

export interface StockTopicAnalysisResponse {
  group_id: string;
  stock_name: string;
  stock_code: string;
  market: string;
  topics: StockTopicMatch[];
  concepts: string[];
  topic_count: number;
  recommendation_count: number;
  summary_markdown?: string;
  model?: string;
  status?: string;
  error?: string;
  created_at?: string;
  updated_at?: string;
  processed_topic_ids?: string[];
  analyzed_topic_ids?: string[];
  skipped_topic_ids?: string[];
  new_topic_count?: number;
  analysis_mode?: 'saved' | 'initialize' | 'incremental' | 'up_to_date' | string;
}

export interface StockTopicImageExtractResponse {
  stockNames: string[];
  model?: string;
  mime_type?: string;
  image_bytes?: number;
}

export interface StockQuestionTopicMatch {
  topic_id: string;
  title: string;
  create_time: string;
  likes_count: number;
  comments_count: number;
  reading_count: number;
  content_preview: string;
  matched_keywords: string[];
}

export interface StockQuestionResponse {
  group_id: string;
  question: string;
  keywords: string[];
  keyword_model?: string;
  topics: StockQuestionTopicMatch[];
  topic_count: number;
  summary_markdown?: string;
  model?: string;
  status?: string;
}

export interface AShareAnalysisSummary {
  group_id?: string | null;
  output_path: string;
  state_path: string;
  output_exists: boolean;
  state_exists: boolean;
  available_dates: string[];
  available_start_date?: string | null;
  available_end_date?: string | null;
  date_count: number;
  rows_count: number;
  total_mentions: number;
  unique_companies: number;
  processed_items: number;
  updated_at?: string | null;
  source_topics_db_exists?: boolean | null;
  source_topics_count?: number | null;
  source_oldest_topic_time?: string | null;
  source_latest_topic_time?: string | null;
}

export interface AShareAnalysisStorageStatus {
  enabled: boolean;
  mode: string;
  label: string;
  daily_rows?: number;
  processed_rows?: number;
}

export interface AShareAnalysisLatestTdxExportBlock {
  window_days: number;
  block_name: string;
  block_code: string;
  block_path: string;
  written_count: number;
  skipped_count: number;
  skipped_companies: string[];
}

export interface AShareAnalysisLatestTdxExport {
  group_id?: string | null;
  export_id: number;
  exported_at: string;
  start_date?: string | null;
  end_date?: string | null;
  tdx_root: string;
  ranking_top_n: number;
  total_written: number;
  unresolved_count: number;
  unresolved_companies: string[];
  stock_basic_source?: string;
  source_detail?: string;
  backup_files: string[];
  blocks: AShareAnalysisLatestTdxExportBlock[];
}

export interface AShareAnalysisStatus {
  group_id?: string | null;
  summary: AShareAnalysisSummary;
  defaults: {
    days: number;
    concurrency: number;
    model: string;
    api_base: string;
    wire_api: string;
    reasoning_effort: string;
    ranking_windows: number[];
  };
  api_key_configured: boolean;
  latest_task?: Task | null;
  running_task?: Task | null;
  storage?: AShareAnalysisStorageStatus;
  latest_tdx_export?: AShareAnalysisLatestTdxExport | null;
}

export interface AShareAnalysisSeries {
  key: string;
  label: string;
  total: number;
  color: string;
}

export interface AShareAnalysisRankingItem {
  company: string;
  count: number;
  rank: number;
  previous_rank?: number | null;
  rank_change?: number | null;
  trend?: 'new' | 'up' | 'down' | 'flat';
}

export interface AShareAnalysisCoverageItem {
  company: string;
  layer: 'core' | 'main' | 'extended' | 'long_tail' | 'short_active';
  layer_label: string;
  layer_order: number;
  rank_30?: number | null;
  count_30?: number | null;
  previous_rank_30?: number | null;
  rank_change_30?: number | null;
  trend_30?: 'new' | 'up' | 'down' | 'flat' | null;
  rank_7?: number | null;
  count_7?: number | null;
  rank_14?: number | null;
  count_14?: number | null;
  tags: string[];
}

export interface AShareAnalysisChart {
  group_id?: string | null;
  available_dates: string[];
  selected_start_date?: string | null;
  selected_end_date?: string | null;
  chart_data: Array<Record<string, string | number>>;
  series: AShareAnalysisSeries[];
  rankings: Record<string, AShareAnalysisRankingItem[]>;
  coverage_pool?: AShareAnalysisCoverageItem[];
  date_count: number;
  company_count: number;
  total_companies_in_range: number;
  top_n: number;
  ranking_top_n: number;
}

export interface AShareAnalysisRunPayload {
  group_id?: string | number;
  days: number;
  concurrency?: number;
  model?: string;
  api_base?: string;
  wire_api?: string;
  reasoning_effort?: string;
  start_date?: string;
  end_date?: string;
  reset_start_date?: string;
  reset_end_date?: string;
}

export interface AShareAnalysisResetPayload {
  group_id?: string | number;
  start_date: string;
  end_date: string;
}

export interface AShareAnalysisExportTdxPayload {
  group_id?: string | number;
  group_name?: string;
  start_date?: string;
  end_date?: string;
}

export interface AShareAnalysisExportTdxBlock {
  window_days: number;
  block_name: string;
  block_code: string;
  block_path: string;
  written_count: number;
  skipped_count: number;
  skipped_companies: string[];
}

export interface AShareAnalysisExportTdxResponse {
  success: boolean;
  group_id?: string | null;
  tdx_root: string;
  selected_start_date?: string | null;
  selected_end_date?: string | null;
  ranking_top_n: number;
  used_stock_cache: boolean;
  stock_basic_source?: string;
  stock_cache_path: string;
  backup_files: string[];
  blocks: AShareAnalysisExportTdxBlock[];
  total_written: number;
  unresolved_companies: string[];
  ambiguous_companies: Record<string, string[]>;
  export_id?: number | null;
}
