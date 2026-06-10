'use client';

import { useCallback, useState } from 'react';
import { toast } from 'sonner';

import { apiClient, TopicDetail } from '@/lib/api';
import { useLatestRequestGuard } from '@/hooks/useLatestRequestGuard';

export function useDailyTopicDetailState(groupId: number) {
  const [selectedTopicId, setSelectedTopicId] = useState<string | null>(null);
  const [topicDetail, setTopicDetail] = useState<TopicDetail | null>(null);
  const [loadingTopicDetail, setLoadingTopicDetail] = useState(false);
  const { invalidateRequests, isLatestRequest, nextRequestId } = useLatestRequestGuard();

  const openTopicDetail = useCallback(async (topicId: string | number) => {
    const id = String(topicId);
    const requestId = nextRequestId();
    try {
      setSelectedTopicId(id);
      setTopicDetail(null);
      setLoadingTopicDetail(true);
      const detail = await apiClient.getTopicDetail(id, groupId);
      if (!isLatestRequest(requestId)) {
        return;
      }
      setTopicDetail(detail);
    } catch (error) {
      if (!isLatestRequest(requestId)) {
        return;
      }
      toast.error(`加载话题详情失败: ${error instanceof Error ? error.message : '未知错误'}`);
    } finally {
      if (isLatestRequest(requestId)) {
        setLoadingTopicDetail(false);
      }
    }
  }, [groupId, isLatestRequest, nextRequestId]);

  const closeTopicDetail = useCallback(() => {
    invalidateRequests();
    setSelectedTopicId(null);
    setTopicDetail(null);
    setLoadingTopicDetail(false);
  }, [invalidateRequests]);

  return {
    closeTopicDetail,
    loadingTopicDetail,
    openTopicDetail,
    selectedTopicId,
    topicDetail,
  };
}
