export interface FileItem {
  file_id: number;
  name: string;
  size: number;
  download_count: number;
  create_time: string;
  download_status: string;
  local_exists?: boolean;
  local_path?: string | null;
  download_error_code?: string | null;
  download_error_message?: string | null;
  last_download_attempt_at?: string | null;
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
