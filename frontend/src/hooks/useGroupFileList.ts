'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';

import { apiClient, FileItem, PaginatedResponse } from '@/lib/api';
import { isFileDownloaded } from '@/components/GroupFileAnalysisPanelParts';

interface UseGroupFileListOptions {
  downloadingFiles: Set<number>;
  groupId: number;
}

export function useGroupFileList({
  downloadingFiles,
  groupId,
}: UseGroupFileListOptions) {
  const [files, setFiles] = useState<FileItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalFiles, setTotalFiles] = useState(0);
  const [searchInput, setSearchInput] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [analysisStatusFilter, setAnalysisStatusFilter] = useState('all');

  const downloadedFiles = useMemo(() => files.filter(isFileDownloaded), [files]);
  const failedFiles = useMemo(
    () => files.filter((file) => !isFileDownloaded(file) && file.download_status === 'failed'),
    [files]
  );
  const pendingAnalysisFiles = useMemo(
    () => files.filter((file) => isFileDownloaded(file) && !file.has_ai_analysis),
    [files]
  );
  const downloadableFiles = useMemo(
    () => files.filter((file) => !isFileDownloaded(file) && !downloadingFiles.has(file.file_id)),
    [downloadingFiles, files]
  );
  const hasActiveFilters = Boolean(searchQuery) || statusFilter !== 'all' || analysisStatusFilter !== 'all';
  const downloadStatusLabel = {
    all: '全部获取状态',
    pending: '未下载',
    completed: '已完成',
    failed: '失败',
    skipped: '已存在',
  }[statusFilter] || statusFilter;
  const analysisStatusLabel = {
    all: '全部分析状态',
    pending: '未分析',
    analyzed: '已分析',
  }[analysisStatusFilter] || analysisStatusFilter;

  const loadFiles = useCallback(async (targetPage: number) => {
    try {
      setLoading(true);
      const status = statusFilter === 'all' ? undefined : statusFilter;
      const analysisStatus = analysisStatusFilter === 'all' ? undefined : analysisStatusFilter;
      const data: PaginatedResponse<FileItem> = await apiClient.getFiles(
        groupId,
        targetPage,
        20,
        status,
        searchQuery || undefined,
        analysisStatus,
      );
      setFiles(data.data || []);
      setPage(data.pagination.page);
      setTotalPages(data.pagination.pages || 1);
      setTotalFiles(data.pagination.total || 0);
    } catch (error) {
      toast.error(`加载文件列表失败: ${error instanceof Error ? error.message : '未知错误'}`);
    } finally {
      setLoading(false);
    }
  }, [analysisStatusFilter, groupId, searchQuery, statusFilter]);

  useEffect(() => {
    void loadFiles(1);
  }, [loadFiles]);

  const handleSearch = () => {
    const nextQuery = searchInput.trim();
    setPage(1);
    if (nextQuery === searchQuery) {
      void loadFiles(1);
      return;
    }
    setSearchQuery(nextQuery);
  };

  const handleStatusFilterChange = (value: string) => {
    setPage(1);
    setStatusFilter(value);
  };

  const handleAnalysisStatusFilterChange = (value: string) => {
    setPage(1);
    setAnalysisStatusFilter(value);
  };

  const showPendingAnalysis = () => {
    setStatusFilter('all');
    setAnalysisStatusFilter('pending');
    setPage(1);
  };

  const clearFilters = () => {
    setSearchInput('');
    setSearchQuery('');
    setStatusFilter('all');
    setAnalysisStatusFilter('all');
    setPage(1);
  };

  return {
    analysisStatusFilter,
    analysisStatusLabel,
    clearFilters,
    downloadableFiles,
    downloadedFiles,
    downloadStatusLabel,
    failedFiles,
    files,
    handleAnalysisStatusFilterChange,
    handleSearch,
    handleStatusFilterChange,
    hasActiveFilters,
    loadFiles,
    loading,
    page,
    pendingAnalysisFiles,
    searchInput,
    searchQuery,
    setSearchInput,
    showPendingAnalysis,
    statusFilter,
    totalFiles,
    totalPages,
  };
}
