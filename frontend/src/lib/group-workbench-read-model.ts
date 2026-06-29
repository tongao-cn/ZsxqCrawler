export interface GroupLoadRetryDecision {
  shouldRetry: boolean;
  nextRetryCount: number;
  delayMs: number;
  finalError: string | null;
}

export interface GroupLocalFileStats {
  total: number;
  downloaded: number;
  pending: number;
  failed: number;
}

interface FileStatsResponseLike {
  download_stats?: {
    total_files?: number | null;
    downloaded?: number | null;
    pending?: number | null;
    failed?: number | null;
  } | null;
}

const RETRYABLE_LOAD_ERROR_MARKERS = ['未知错误', '空数据', '反爬虫'];
const MAX_AUTO_RETRIES = 5;

export const EMPTY_LOCAL_FILE_STATS: GroupLocalFileStats = {
  total: 0,
  downloaded: 0,
  pending: 0,
  failed: 0,
};

export function isRetryableLoadError(message: string) {
  return RETRYABLE_LOAD_ERROR_MARKERS.some((marker) => message.includes(marker));
}

export function resolveGroupDetailRetry(errorMessage: string, currentRetryCount: number): GroupLoadRetryDecision {
  return resolveRetryDecision(errorMessage, currentRetryCount, {
    baseDelayMs: 1000,
    stepDelayMs: 500,
    maxDelayMs: 5000,
  });
}

export function resolveTopicsRetry(errorMessage: string, currentRetryCount: number): GroupLoadRetryDecision {
  return resolveRetryDecision(errorMessage, currentRetryCount, {
    baseDelayMs: 1000,
    stepDelayMs: 300,
    maxDelayMs: 3000,
  });
}

export function normalizeGroupLocalFileStats(stats: FileStatsResponseLike | null | undefined): GroupLocalFileStats {
  const downloadStats = stats?.download_stats || {};
  const total = downloadStats.total_files || 0;
  return {
    total,
    downloaded: downloadStats.downloaded || 0,
    pending: downloadStats.pending || 0,
    failed: downloadStats.failed || 0,
  };
}

function resolveRetryDecision(
  errorMessage: string,
  currentRetryCount: number,
  timing: {
    baseDelayMs: number;
    stepDelayMs: number;
    maxDelayMs: number;
  },
): GroupLoadRetryDecision {
  if (!isRetryableLoadError(errorMessage)) {
    return {
      shouldRetry: false,
      nextRetryCount: currentRetryCount,
      delayMs: 0,
      finalError: errorMessage,
    };
  }

  if (currentRetryCount >= MAX_AUTO_RETRIES) {
    return {
      shouldRetry: false,
      nextRetryCount: currentRetryCount,
      delayMs: 0,
      finalError: `${errorMessage}，自动重试已达上限`,
    };
  }

  const nextRetryCount = currentRetryCount + 1;
  return {
    shouldRetry: true,
    nextRetryCount,
    delayMs: Math.min(timing.baseDelayMs + nextRetryCount * timing.stepDelayMs, timing.maxDelayMs),
    finalError: null,
  };
}
