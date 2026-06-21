export type {
  AShareAnalysisChart,
  AShareAnalysisCoverageItem,
  AShareAnalysisExportTdxBlock,
  AShareAnalysisExportTdxPayload,
  AShareAnalysisExportTdxResponse,
  AShareAnalysisLatestTdxExport,
  AShareAnalysisLatestTdxExportBlock,
  AShareAnalysisRankingItem,
  AShareAnalysisResetPayload,
  AShareAnalysisRunPayload,
  AShareAnalysisSeries,
  AShareAnalysisStatus,
  AShareAnalysisStorageStatus,
  AShareAnalysisSummary,
  DailyStockConcept,
  DailyStockConceptResponse,
  DailyTopicAnalysisPayload,
  DailyTopicReport,
  StockQuestionResponse,
  StockQuestionTopicMatch,
  StockTopicAnalysisResponse,
  StockTopicBatchAnalysisResponse,
  StockTopicImageExtractResponse,
  StockTopicMatch,
} from './analysisTypes';
export type {
  ColumnComment,
  ColumnFile,
  ColumnImage,
  ColumnInfo,
  ColumnsFetchSettings,
  ColumnsStats,
  ColumnTopic,
  ColumnTopicDetail,
  ColumnVideo,
} from './columnTypes';
export type { DatabaseStats } from './coreTypes';
export type { FileAIAnalysis, FileItem, FileStatus, LocalFileStatus } from './fileTypes';
export type {
  Account,
  AccountSelf,
  FetchMoreCommentsResponse,
  Group,
  GroupStats,
  Topic,
  TopicDetail,
  TopicOwner,
} from './groupTypes';
export type { ApiErrorDetail, Task, TaskCreateResponse, TaskLogsResponse } from './taskTypes';

export interface ApiResponse<T = any> {
  data?: T;
  message?: string;
  error?: string;
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
