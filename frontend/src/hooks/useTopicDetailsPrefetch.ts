'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import type { TopicCardProps } from '@/components/TopicCard';
import { apiClient, type Topic } from '@/lib/api';

type TopicDetail = NonNullable<TopicCardProps['topicDetail']>;
type TopicDetailsMap = Map<string, TopicDetail>;

interface UseTopicDetailsCacheOptions {
  active?: boolean;
  groupId: number;
  topics?: Topic[];
}

export function useTopicDetailsCache({
  active = true,
  groupId,
  topics = [],
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

  useEffect(() => {
    if (!active || topics.length === 0) {
      return;
    }

    let cancelled = false;
    const topicIds = topics
      .map((topic) => String(topic?.topic_id || ''))
      .filter((topicId) => {
        if (!topicId || topicDetailsRef.current.has(topicId)) {
          return false;
        }
        return !inFlightRef.current.has(`${groupId}-${topicId}`);
      });

    const prefetchDetails = async () => {
      const concurrency = 4;

      for (let index = 0; index < topicIds.length && !cancelled; index += concurrency) {
        const batch = topicIds.slice(index, index + concurrency);
        await Promise.all(batch.map((topicId) => loadTopicDetail(topicId)));
      }
    };

    void prefetchDetails();

    return () => {
      cancelled = true;
    };
  }, [active, groupId, loadTopicDetail, topics]);

  return {
    loadTopicDetail,
    topicDetails,
  };
}
