'use client';

import { Dispatch, SetStateAction, useCallback, useState } from 'react';
import { toast } from 'sonner';

import { apiClient, Topic } from '@/lib/api';
import { useSyncedRef } from '@/hooks/useSyncedRef';

type TopicId = string | number;

interface UseTopicActionsOptions {
  groupId: number;
  setTopics: Dispatch<SetStateAction<Topic[]>>;
  loadTopics: () => void | Promise<void>;
  loadGroupStats: () => void | Promise<void>;
}

export function useTopicActions({
  groupId,
  setTopics,
  loadTopics,
  loadGroupStats,
}: UseTopicActionsOptions) {
  const [expandedComments, setExpandedComments] = useState<Set<string>>(new Set());
  const [expandedContent, setExpandedContent] = useState<Set<string>>(new Set());
  const [fetchingComments, setFetchingComments] = useState<Set<string>>(new Set());
  const [refreshingTopics, setRefreshingTopics] = useState<Set<string>>(new Set());
  const [deletingTopics, setDeletingTopics] = useState<Set<string>>(new Set());
  const fetchingCommentsRef = useSyncedRef(fetchingComments);
  const refreshingTopicsRef = useSyncedRef(refreshingTopics);

  const toggleComments = useCallback((topicId: TopicId) => {
    const key = String(topicId);
    setExpandedComments((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  }, []);

  const toggleContent = useCallback((topicId: TopicId) => {
    const key = String(topicId);
    setExpandedContent((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  }, []);

  const refreshSingleTopic = useCallback(async (topicId: TopicId) => {
    const topicKey = String(topicId);
    if (refreshingTopicsRef.current.has(topicKey)) {
      return;
    }

    refreshingTopicsRef.current = new Set(refreshingTopicsRef.current).add(topicKey);
    setRefreshingTopics(new Set(refreshingTopicsRef.current));

    try {
      const response = await apiClient.refreshTopic(topicKey, groupId) as any;

      if (response.success) {
        toast.success(`${response.message} - 点赞:${response.updated_data.likes_count} 评论:${response.updated_data.comments_count}`);

        setTopics((prevTopics) => (
          prevTopics.map((topic) => (
            String(topic.topic_id) === topicKey
              ? {
                  ...topic,
                  likes_count: response.updated_data.likes_count,
                  comments_count: response.updated_data.comments_count,
                  reading_count: response.updated_data.reading_count,
                  readers_count: response.updated_data.readers_count,
                  imported_at: new Date().toISOString(),
                }
              : topic
          ))
        ));
      } else {
        toast.error(response.message || '刷新话题失败');
      }
    } catch (error) {
      toast.error('刷新话题失败');
      console.error('刷新话题失败:', error);
    } finally {
      const next = new Set(refreshingTopicsRef.current);
      next.delete(topicKey);
      refreshingTopicsRef.current = next;
      setRefreshingTopics(next);
    }
  }, [groupId, refreshingTopicsRef, setTopics]);

  const deleteSingleTopicConfirmed = useCallback(async (topicId: TopicId) => {
    const topicKey = String(topicId);
    setDeletingTopics((prev) => new Set(prev).add(topicKey));

    try {
      const response = await apiClient.deleteSingleTopic(groupId, topicKey) as any;

      if (response && response.success) {
        setTopics((prev) => prev.filter((topic) => String(topic.topic_id) !== topicKey));
        toast.success('话题已删除');
        void loadGroupStats();
      } else {
        toast.error(response?.message || '删除失败');
      }
    } catch (error) {
      toast.error('删除失败');
      console.error('删除话题失败:', error);
    } finally {
      setDeletingTopics((prev) => {
        const next = new Set(prev);
        next.delete(topicKey);
        return next;
      });
    }
  }, [groupId, loadGroupStats, setTopics]);

  const fetchMoreComments = useCallback(async (topicId: TopicId) => {
    const topicKey = String(topicId);
    if (fetchingCommentsRef.current.has(topicKey)) {
      return;
    }

    fetchingCommentsRef.current = new Set(fetchingCommentsRef.current).add(topicKey);
    setFetchingComments(new Set(fetchingCommentsRef.current));

    try {
      const result = await apiClient.fetchMoreComments(topicKey, groupId);
      toast.success(result.message);

      if (result.comments_fetched > 0) {
        await loadTopics();
      }
    } catch (error) {
      toast.error('获取评论失败');
      console.error('获取评论失败:', error);
    } finally {
      const next = new Set(fetchingCommentsRef.current);
      next.delete(topicKey);
      fetchingCommentsRef.current = next;
      setFetchingComments(next);
    }
  }, [fetchingCommentsRef, groupId, loadTopics]);

  return {
    expandedComments,
    expandedContent,
    fetchingComments,
    refreshingTopics,
    deletingTopics,
    toggleComments,
    toggleContent,
    refreshSingleTopic,
    deleteSingleTopicConfirmed,
    fetchMoreComments,
  };
}
