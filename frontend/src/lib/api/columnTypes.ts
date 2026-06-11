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
