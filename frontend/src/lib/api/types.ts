export interface ApiResponse<T = any> {
  data?: T;
  message?: string;
  error?: string;
}

export interface Task {
  task_id: string;
  type: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  message: string;
  result?: any;
  created_at: string;
  updated_at: string;
  group_id?: string | number | null;
  ingestion_lock_key?: string | null;
}

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

export interface StockTopicBatchAnalysisResponse {
  group_id: string;
  stocks: StockTopicAnalysisResponse[];
  summary?: {
    total: number;
    success: number;
    failed: number;
    no_topics: number;
  };
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

export interface TaskCreateResponse {
  task_id: string;
  message: string;
}

export interface ApiErrorDetail {
  message?: string;
  error?: string;
  task_id?: string;
  type?: string;
  status?: string;
  [key: string]: unknown;
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

export interface AShareAnalysisChart {
  group_id?: string | null;
  available_dates: string[];
  selected_start_date?: string | null;
  selected_end_date?: string | null;
  chart_data: Array<Record<string, string | number>>;
  series: AShareAnalysisSeries[];
  rankings: Record<string, AShareAnalysisRankingItem[]>;
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

export interface DatabaseStats {
  configured?: boolean;
  topic_database: {
    stats: Record<string, number>;
    timestamp_info: {
      total_topics: number;
      oldest_timestamp: string;
      newest_timestamp: string;
      has_data: boolean;
    };
  };
  file_database: {
    stats: Record<string, number>;
  };
}

export interface Topic {
  topic_id: string;
  title: string;
  create_time: string;
  likes_count: number;
  comments_count: number;
  reading_count: number;
  type: string;
  imported_at?: string;
}

export interface FetchMoreCommentsResponse {
  success: boolean;
  message: string;
  comments_fetched: number;
}

export interface FileItem {
  file_id: number;
  name: string;
  size: number;
  download_count: number;
  create_time: string;
  download_status: string;
  local_exists?: boolean;
  local_path?: string | null;
  has_ai_analysis?: boolean;
  analysis_updated_at?: string | null;
}

export interface FileAIAnalysis {
  file_id: number;
  status: string;
  summary?: string | null;
  extracted_text?: string | null;
  extracted_text_preview?: string | null;
  content_type?: string | null;
  source_path?: string | null;
  source_size?: number | null;
  model?: string | null;
  api_base?: string | null;
  wire_api?: string | null;
  reasoning_effort?: string | null;
  error_message?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  cached?: boolean;
}

export interface FileStatus {
  file_id: number;
  name: string;
  size: number;
  download_status: string;
  local_exists: boolean;
  local_size: number;
  local_path?: string;
  is_complete: boolean;
}

export interface PaginatedResponse<T> {
  data: T[];
  pagination: {
    page: number;
    per_page: number;
    total: number;
    pages: number;
  };
}

export interface Group {
  account?: Account;
  group_id: number;
  name: string;
  type: string;
  background_url?: string;
  description?: string;
  create_time?: string;
  subscription_time?: string;
  expiry_time?: string;
  join_time?: string;
  last_active_time?: string;
  status?: string;
  source?: string; // "account" | "local" | "account|local"
  is_trial?: boolean;
  trial_end_time?: string;
  membership_end_time?: string;
  owner?: {
    user_id: number;
    name: string;
    alias?: string;
    avatar_url?: string;
    description?: string;
  };
  statistics?: {
    members?: {
      count: number;
    };
    topics?: {
      topics_count: number;
      answers_count: number;
      digests_count: number;
    };
    files?: {
      count: number;
    };
  };
}

export interface GroupStats {
  group_id: number;
  topics_count: number;
  users_count: number;
  latest_topic_time?: string;
  earliest_topic_time?: string;
  total_likes: number;
  total_comments: number;
  total_readings: number;
}
export interface Account {
  id: string;
  name?: string;
  cookie?: string; // 已掩码
  created_at?: string;
  is_default?: boolean;
}

export interface AccountSelf {
  account_id: string;
  uid?: string;
  name?: string;
  avatar_url?: string;
  location?: string;
  user_sid?: string;
  grade?: string;
  fetched_at?: string;
  raw_json?: any;
}

export interface ColumnInfo {
  column_id: number;
  group_id: number;
  name: string;
  cover_url?: string;
  topics_count: number;
  create_time?: string;
  last_topic_attach_time?: string;
  imported_at?: string;
}

export interface ColumnTopic {
  topic_id: number;
  column_id: number;
  group_id: number;
  title?: string;
  text?: string;
  create_time?: string;
  attached_to_column_time?: string;
  imported_at?: string;
  has_detail?: boolean;
}

export interface ColumnTopicDetail {
  topic_id: number;
  group_id: number;
  type?: string;
  title?: string;
  full_text?: string;
  likes_count: number;
  comments_count: number;
  readers_count: number;
  digested: boolean;
  sticky: boolean;
  create_time?: string;
  modify_time?: string;
  raw_json?: string;
  imported_at?: string;
  updated_at?: string;
  owner?: {
    user_id: number;
    name: string;
    alias?: string;
    avatar_url?: string;
    description?: string;
    location?: string;
  };
  // Q&A type content
  question?: {
    text?: string;
    owner?: {
      user_id: number;
      name: string;
      alias?: string;
      avatar_url?: string;
    };
    images?: ColumnImage[];
  };
  answer?: {
    text?: string;
    owner?: {
      user_id: number;
      name: string;
      alias?: string;
      avatar_url?: string;
    };
    images?: ColumnImage[];
  };
  images: ColumnImage[];
  files: ColumnFile[];
  videos: ColumnVideo[];
  comments: ColumnComment[];
}

export interface ColumnImage {
  image_id: number;
  type?: string;
  thumbnail?: { url?: string; width?: number; height?: number };
  large?: { url?: string; width?: number; height?: number };
  original?: { url?: string; width?: number; height?: number; size?: number };
  local_path?: string;
}

export interface ColumnVideo {
  video_id: number;
  size?: number;
  duration?: number;
  cover?: {
    url?: string;
    width?: number;
    height?: number;
    local_path?: string;
  };
  video_url?: string;
  download_status?: string;
  local_path?: string;
  download_time?: string;
}

export interface ColumnFile {
  file_id: number;
  name: string;
  hash?: string;
  size?: number;
  duration?: number;
  download_count?: number;
  create_time?: string;
  download_status?: string;
  local_path?: string;
  download_time?: string;
}

export interface ColumnComment {
  comment_id: number;
  parent_comment_id?: number;
  text?: string;
  create_time?: string;
  likes_count: number;
  rewards_count: number;
  replies_count: number;
  sticky: boolean;
  owner?: {
    user_id: number;
    name: string;
    alias?: string;
    avatar_url?: string;
    location?: string;
  };
  repliee?: {
    user_id: number;
    name: string;
    alias?: string;
    avatar_url?: string;
  };
  images?: Array<{
    image_id?: number;
    type?: string;
    thumbnail?: { url?: string; width?: number; height?: number };
    large?: { url?: string; width?: number; height?: number };
    original?: { url?: string; width?: number; height?: number };
  }>;
  // Nested replies
  replied_comments?: ColumnComment[];
}

export interface ColumnsStats {
  columns_count: number;
  topics_count: number;
  details_count: number;
  images_count: number;
  files_count: number;
  files_downloaded: number;
  videos_count: number;
  videos_downloaded: number;
  comments_count: number;
}

export interface ColumnsFetchSettings {
  crawlIntervalMin?: number;
  crawlIntervalMax?: number;
  longSleepIntervalMin?: number;
  longSleepIntervalMax?: number;
  itemsPerBatch?: number;
  downloadFiles?: boolean;
  downloadVideos?: boolean;
  cacheImages?: boolean;
  incrementalMode?: boolean;
}
