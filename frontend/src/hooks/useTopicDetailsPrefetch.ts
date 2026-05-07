'use client';

import { useEffect, useRef, useState } from 'react';

import { apiClient, Topic } from '@/lib/api';

type TopicDetailsMap = Map<string, any>;

interface UseTopicDetailsPrefetchOptions {
  active: boolean;
  groupId: number;
  topics: Topic[];
}

export function useTopicDetailsPrefetch({
  active,
  groupId,
  topics,
}: UseTopicDetailsPrefetchOptions) {
  const [topicDetails, setTopicDetails] = useState<TopicDetailsMap>(new Map());
  const topicDetailsRef = useRef<TopicDetailsMap>(new Map());
  const inFlightRef = useRef<Map<string, Promise<any>>>(new Map());

  useEffect(() => {
    topicDetailsRef.current = topicDetails;
  }, [topicDetails]);

  useEffect(() => {
    if (!active) return;
    if (!topics || topics.length === 0) return;
    let cancelled = false;

    const topicIds = topics
      .map((topic: any) => String((topic as any)?.topic_id || ''))
      .filter((topicId) => {
        if (!topicId) return false;
        if (topicDetailsRef.current.has(topicId)) return false;
        return !inFlightRef.current.has(`${groupId}-${topicId}`);
      });

    const prefetchDetails = async () => {
      const concurrency = 4;

      for (let index = 0; index < topicIds.length && !cancelled; index += concurrency) {
        const batch = topicIds.slice(index, index + concurrency);
        const updates = await Promise.all(batch.map(async (topicId) => {
          const key = `${groupId}-${topicId}`;
          if (cancelled || topicDetailsRef.current.has(topicId) || inFlightRef.current.has(key)) {
            return null;
          }

          const request = apiClient.getTopicDetail(topicId, groupId);
          inFlightRef.current.set(key, request);

          try {
            const detail = await request;
            if (cancelled) return null;
            return [topicId, detail] as const;
          } catch (err) {
            console.error('预取话题详情失败:', err);
            return null;
          } finally {
            inFlightRef.current.delete(key);
          }
        }));

        const successfulUpdates = updates.filter((item): item is readonly [string, any] => Boolean(item));
        if (cancelled || successfulUpdates.length === 0) {
          continue;
        }

        setTopicDetails((prev) => {
          const next = new Map(prev);
          let changed = false;

          for (const [topicId, detail] of successfulUpdates) {
            if (!next.has(topicId)) {
              next.set(topicId, detail);
              changed = true;
            }
          }

          if (!changed) {
            return prev;
          }

          topicDetailsRef.current = next;
          return next;
        });
      }
    };

    void prefetchDetails();

    return () => {
      cancelled = true;
    };
  }, [active, topics, groupId]);

  return topicDetails;
}
