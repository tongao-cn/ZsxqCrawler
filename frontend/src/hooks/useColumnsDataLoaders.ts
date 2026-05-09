'use client';

import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { apiClient, ColumnInfo, ColumnTopic, ColumnTopicDetail, ColumnsStats } from '@/lib/api';

export function useColumnsDataLoaders(groupId: string) {
  const [columns, setColumns] = useState<ColumnInfo[]>([]);
  const [stats, setStats] = useState<ColumnsStats | null>(null);
  const [selectedColumn, setSelectedColumn] = useState<ColumnInfo | null>(null);
  const [columnTopics, setColumnTopics] = useState<ColumnTopic[]>([]);
  const [selectedTopic, setSelectedTopic] = useState<ColumnTopicDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [topicsLoading, setTopicsLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [loadingComments, setLoadingComments] = useState(false);

  const resetColumnsData = useCallback(() => {
    setColumns([]);
    setColumnTopics([]);
    setSelectedColumn(null);
    setSelectedTopic(null);
    setStats(null);
  }, []);

  const loadTopicDetail = useCallback(async (topicId: number) => {
    try {
      setDetailLoading(true);
      const detail = await apiClient.getColumnTopicDetail(groupId, topicId);
      setSelectedTopic(detail);
    } catch (error) {
      console.error('加载文章详情失败:', error);
      toast.error('加载文章详情失败');
    } finally {
      setDetailLoading(false);
    }
  }, [groupId]);

  const loadColumnTopics = useCallback(async (columnId: number) => {
    try {
      setTopicsLoading(true);
      setSelectedTopic(null);
      const data = await apiClient.getColumnTopics(groupId, columnId);
      setColumnTopics(data.topics || []);

      if (data.topics && data.topics.length > 0 && data.topics[0].has_detail) {
        await loadTopicDetail(data.topics[0].topic_id);
      }
    } catch (error) {
      console.error('加载专栏文章列表失败:', error);
      toast.error('加载文章列表失败');
    } finally {
      setTopicsLoading(false);
    }
  }, [groupId, loadTopicDetail]);

  const loadColumns = useCallback(async () => {
    try {
      setLoading(true);
      const data = await apiClient.getGroupColumns(groupId);
      setColumns(data.columns || []);
      setStats(data.stats);

      if (data.columns && data.columns.length > 0) {
        setSelectedColumn(data.columns[0]);
        await loadColumnTopics(data.columns[0].column_id);
      }
    } catch (error) {
      console.error('加载专栏目录失败:', error);
      toast.error('加载专栏目录失败');
    } finally {
      setLoading(false);
    }
  }, [groupId, loadColumnTopics]);

  const handleFetchMoreComments = useCallback(async () => {
    if (!selectedTopic) return;

    try {
      setLoadingComments(true);
      const result = await apiClient.getColumnTopicFullComments(groupId, selectedTopic.topic_id);
      if (result.success && result.comments) {
        setSelectedTopic(prev => prev ? {
          ...prev,
          comments: result.comments,
        } : null);
        toast.success(`已获取 ${result.total} 条评论`);
      }
    } catch (error) {
      console.error('获取完整评论失败:', error);
      toast.error('获取完整评论失败');
    } finally {
      setLoadingComments(false);
    }
  }, [groupId, selectedTopic]);

  const handleSelectColumn = useCallback(async (column: ColumnInfo) => {
    setSelectedColumn(column);
    await loadColumnTopics(column.column_id);
  }, [loadColumnTopics]);

  const handleSelectTopic = useCallback(async (topic: ColumnTopic) => {
    if (topic.has_detail) {
      await loadTopicDetail(topic.topic_id);
    } else {
      toast.info('该文章尚未采集详情，请先采集专栏内容');
    }
  }, [loadTopicDetail]);

  useEffect(() => {
    loadColumns();
  }, [loadColumns]);

  return {
    columns,
    stats,
    selectedColumn,
    columnTopics,
    selectedTopic,
    loading,
    topicsLoading,
    detailLoading,
    loadingComments,
    loadColumns,
    resetColumnsData,
    handleFetchMoreComments,
    handleSelectColumn,
    handleSelectTopic,
  };
}
