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

export interface TopicOwner {
  avatar_url?: string | null;
  location?: string | null;
  name?: string | null;
}

export interface TopicDetail {
  topic_id?: string | number;
  type?: string | null;
  title?: string | null;
  create_time?: string | null;
  reading_count?: number | null;
  likes_count?: number | null;
  comments_count?: number | null;
  talk?: {
    text?: string | null;
    owner?: TopicOwner | null;
  } | null;
  question?: {
    text?: string | null;
    anonymous?: boolean | null;
    owner?: TopicOwner | null;
    owner_location?: string | null;
  } | null;
  answer?: {
    text?: string | null;
    owner?: TopicOwner | null;
  } | null;
}

export interface FetchMoreCommentsResponse {
  success: boolean;
  message: string;
  comments_fetched: number;
}

export interface TopicStatsUpdate {
  likes_count: number;
  comments_count: number;
  reading_count: number;
  readers_count: number;
}

export type RefreshTopicResponse =
  | {
      success: true;
      message: string;
      updated_data: TopicStatsUpdate;
    }
  | {
      success: false;
      message: string;
    };

export interface DeleteSingleTopicResponse {
  success: boolean;
  message?: string;
  deleted_topic_id?: number;
  deleted?: Record<string, number>;
}

export interface FetchSingleTopicResponse {
  success: true;
  topic_id: number;
  group_id: number;
  imported: string;
  comments_fetched: number;
  message?: string;
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

export interface DeleteGroupResponse {
  success: boolean;
  message?: string;
  details?: {
    downloads_dir_removed?: boolean;
    images_cache_removed?: boolean;
    group_dir_removed?: boolean;
  };
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
