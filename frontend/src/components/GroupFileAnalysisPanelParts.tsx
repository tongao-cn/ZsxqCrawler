'use client';

import { Dispatch, SetStateAction } from 'react';
import { Download, Loader2, RefreshCw, Search, Sparkles } from 'lucide-react';
import { FileItem } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

export function formatFileSize(size: number) {
  if (!size) return '未知大小';
  const units = ['B', 'KB', 'MB', 'GB'];
  let value = size;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
}

export function formatDate(value?: string | null) {
  if (!value) return '未知时间';
  return new Date(value).toLocaleString('zh-CN');
}

export function getExtractedTextLabel(contentType?: string | null) {
  if (contentType?.startsWith('audio/')) {
    return '转录原文';
  }
  return '提取原文';
}

export function isFileDownloaded(file: FileItem) {
  return Boolean(
    file.local_exists
    || file.local_path
    || ['completed', 'downloaded', 'skipped'].includes(file.download_status)
  );
}

interface GroupFileHeaderProps {
  downloadStatusLabel: string;
  analysisStatusLabel: string;
  searchQuery: string;
  page: number;
}

export function GroupFileHeader({
  downloadStatusLabel,
  analysisStatusLabel,
  searchQuery,
  page,
}: GroupFileHeaderProps) {
  return (
    <div className="flex flex-col gap-2 lg:flex-row lg:items-end lg:justify-between">
      <div>
        <div className="text-lg font-semibold text-gray-950">文件工作台</div>
        <div className="text-sm text-muted-foreground">
          定位文件、下载或重试、AI 分析和查看结果都在这里完成。
        </div>
      </div>
      <div className="rounded-lg border border-blue-100 bg-blue-50 px-3 py-2 text-xs text-blue-700">
        当前筛选：{downloadStatusLabel} · {analysisStatusLabel} · {searchQuery ? `关键词 ${searchQuery}` : '无关键词'} · 第 {page} 页
      </div>
    </div>
  );
}

interface GroupFileSummaryProps {
  filesCount: number;
  totalFiles: number;
  downloadedCount: number;
  failedCount: number;
  pendingAnalysisCount: number;
}

export function GroupFileSummary({
  filesCount,
  totalFiles,
  downloadedCount,
  failedCount,
  pendingAnalysisCount,
}: GroupFileSummaryProps) {
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
      <div className="rounded-lg border border-gray-200 bg-white p-3">
        <div className="text-xs text-muted-foreground">当前页</div>
        <div className="mt-1 text-xl font-semibold">{filesCount}</div>
      </div>
      <div className="rounded-lg border border-gray-200 bg-white p-3">
        <div className="text-xs text-muted-foreground">匹配总数</div>
        <div className="mt-1 text-xl font-semibold">{totalFiles}</div>
      </div>
      <div className="rounded-lg border border-gray-200 bg-white p-3">
        <div className="text-xs text-muted-foreground">当前页已下载</div>
        <div className="mt-1 text-xl font-semibold text-green-700">{downloadedCount}</div>
      </div>
      <div className="rounded-lg border border-gray-200 bg-white p-3">
        <div className="text-xs text-muted-foreground">当前页失败</div>
        <div className="mt-1 text-xl font-semibold text-red-700">{failedCount}</div>
      </div>
      <div className="rounded-lg border border-gray-200 bg-white p-3">
        <div className="text-xs text-muted-foreground">当前页待分析</div>
        <div className="mt-1 text-xl font-semibold text-amber-700">{pendingAnalysisCount}</div>
      </div>
    </div>
  );
}

interface GroupFileToolbarProps {
  searchInput: string;
  setSearchInput: Dispatch<SetStateAction<string>>;
  onSearch: () => void;
  loading: boolean;
  statusFilter: string;
  onStatusFilterChange: (value: string) => void;
  analysisStatusFilter: string;
  onAnalysisStatusFilterChange: (value: string) => void;
  onRefresh: () => void;
  batchAnalyzing: boolean;
  downloadableCount: number;
  batchDownloadActive: boolean;
  onDownloadCurrentPage: () => void;
  onDownloadFilteredResults: () => void;
  pendingAnalysisCount: number;
  onAnalyzeCurrentPage: () => void;
  onShowPending: () => void;
  showPendingDisabled: boolean;
  hasActiveFilters: boolean;
  onClearFilters: () => void;
}

export function GroupFileToolbar({
  searchInput,
  setSearchInput,
  onSearch,
  loading,
  statusFilter,
  onStatusFilterChange,
  analysisStatusFilter,
  onAnalysisStatusFilterChange,
  onRefresh,
  batchAnalyzing,
  downloadableCount,
  batchDownloadActive,
  onDownloadCurrentPage,
  onDownloadFilteredResults,
  pendingAnalysisCount,
  onAnalyzeCurrentPage,
  onShowPending,
  showPendingDisabled,
  hasActiveFilters,
  onClearFilters,
}: GroupFileToolbarProps) {
  return (
    <div className="rounded-lg border border-gray-200 bg-gray-50 p-3">
      <div className="flex flex-col gap-2 xl:flex-row xl:items-center">
        <div className="flex min-w-0 flex-1 gap-2">
          <Input
            value={searchInput}
            placeholder="搜索文件名、来源话题、扩展名..."
            onChange={(event) => setSearchInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                onSearch();
              }
            }}
          />
          <Button variant="outline" size="sm" onClick={onSearch} disabled={loading}>
            <Search className="h-4 w-4 mr-2" />
            搜索
          </Button>
        </div>
        <div className="flex flex-wrap gap-2">
          <Select value={statusFilter} onValueChange={onStatusFilterChange}>
            <SelectTrigger className="w-36">
              <SelectValue placeholder="获取状态" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部获取状态</SelectItem>
              <SelectItem value="pending">未下载</SelectItem>
              <SelectItem value="completed">已完成</SelectItem>
              <SelectItem value="failed">失败</SelectItem>
              <SelectItem value="skipped">已存在</SelectItem>
            </SelectContent>
          </Select>
          <Select value={analysisStatusFilter} onValueChange={onAnalysisStatusFilterChange}>
            <SelectTrigger className="w-36">
              <SelectValue placeholder="分析状态" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部分析状态</SelectItem>
              <SelectItem value="pending">未分析</SelectItem>
              <SelectItem value="analyzed">已分析</SelectItem>
            </SelectContent>
          </Select>
          <Button
            variant="outline"
            size="sm"
            onClick={onRefresh}
            disabled={loading || batchAnalyzing}
          >
            <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            刷新
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={onDownloadCurrentPage}
            disabled={downloadableCount === 0 || loading || batchDownloadActive}
          >
            <Download className="h-4 w-4 mr-2" />
            下载当前页
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={onDownloadFilteredResults}
            disabled={loading || batchDownloadActive}
          >
            <Download className="h-4 w-4 mr-2" />
            下载筛选结果
          </Button>
          <Button
            size="sm"
            onClick={onAnalyzeCurrentPage}
            disabled={pendingAnalysisCount === 0 || batchAnalyzing}
          >
            {batchAnalyzing ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <Sparkles className="h-4 w-4 mr-2" />
            )}
            分析当前页
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={onShowPending}
            disabled={showPendingDisabled}
          >
            只看需处理
          </Button>
          {hasActiveFilters && (
            <Button
              size="sm"
              variant="ghost"
              onClick={onClearFilters}
            >
              清空筛选
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

interface GroupFilePaginationProps {
  page: number;
  totalPages: number;
  loading: boolean;
  onLoadPage: (page: number) => void;
}

export function GroupFilePagination({
  page,
  totalPages,
  loading,
  onLoadPage,
}: GroupFilePaginationProps) {
  if (totalPages <= 1) {
    return null;
  }

  return (
    <div className="flex flex-shrink-0 items-center justify-center gap-3 border-t border-gray-200 pt-4">
      <Button
        variant="outline"
        size="sm"
        onClick={() => onLoadPage(Math.max(1, page - 1))}
        disabled={page === 1 || loading}
      >
        上一页
      </Button>
      <div className="text-sm text-muted-foreground">
        第 {page} / {totalPages} 页
      </div>
      <Button
        variant="outline"
        size="sm"
        onClick={() => onLoadPage(Math.min(totalPages, page + 1))}
        disabled={page === totalPages || loading}
      >
        下一页
      </Button>
    </div>
  );
}
