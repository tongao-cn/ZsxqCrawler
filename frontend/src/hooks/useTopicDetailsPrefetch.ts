'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import type { TopicCardProps } from '@/components/TopicCard';
import { apiClient } from '@/lib/api';

type TopicDetail = NonNullable<TopicCardProps['topicDetail']>;
type TopicDetailsMap = Map<string, TopicDetail>;

interface UseTopicDetailsCacheOptions {
  groupId: number;
}

export function useTopicDetailsCache({
  groupId,
}: UseTopicDetailsCacheOptions) {
  const [topicDetails, setTopicDetails] = useState<TopicDetailsMap>(new Map());
  const topicDetailsRef = useRef<TopicDetailsMap>(new Map());
  const inFlightRef = useRef<Map<string, Promise<TopicDetail>>>(new Map());

  useEffect(() => {
    topicDetailsRef.current = topicDetails;
  }, [topicDetails]);

  useEffect(() => {
    topicDetailsRef.current = new Map();
    inFlightRef.current.clear();
    setTopicDetails(new Map());
  }, [groupId]);

  const loadTopicDetail = useCallback(async (topicIdValue: string | number) => {
    const topicId = String(topicIdValue || '');
    if (!topicId) {
      return null;
    }
    const cached = topicDetailsRef.current.get(topicId);
    if (cached) {
      return cached;
    }

    const key = `${groupId}-${topicId}`;
    const existing = inFlightRef.current.get(key);
    if (existing) {
      return existing;
    }

    const request = apiClient.getTopicDetail(topicId, groupId) as Promise<TopicDetail>;
    inFlightRef.current.set(key, request);

    try {
      const detail = await request;
      setTopicDetails((prev) => {
        if (prev.has(topicId)) {
          return prev;
        }
        const next = new Map(prev);
        next.set(topicId, detail);
        topicDetailsRef.current = next;
        return next;
      });
      return detail;
    } catch (err) {
      console.error('加载话题详情失败:', err);
      return null;
    } finally {
      inFlightRef.current.delete(key);
    }
  }, [groupId]);

  return {
    loadTopicDetail,
    topicDetails,
  };
}
