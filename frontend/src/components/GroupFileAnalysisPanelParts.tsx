'use client';

import { Dispatch, SetStateAction } from 'react';
import { Download, FileText, Loader2, RefreshCw, Search, Sparkles } from 'lucide-react';
import { FileAIAnalysis, FileItem } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import type { FileTaskState } from '@/components/GroupFileTaskWatchers';

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

function getDownloadStatusBadge(file: FileItem) {
  if (isFileDownloaded(file)) {
    if (file.download_status === 'skipped') {
      return <Badge className="bg-slate-100 text-slate-800">已存在</Badge>;
    }
    return <Badge className="bg-green-100 text-green-800">已完成</Badge>;
  }

  switch (file.download_status) {
    case 'pending':
      return <Badge className="bg-yellow-100 text-yellow-800">未下载</Badge>;
    case 'failed':
      return <Badge className="bg-red-100 text-red-800">失败</Badge>;
    default:
      return <Badge variant="secondary">{file.download_status || 'unknown'}</Badge>;
  }
}

function getAnalysisStatusBadge(file: FileItem) {
  if (file.has_ai_analysis) {
    return <Badge variant="secondary">已有分析</Badge>;
  }
  return <Badge variant="outline">未分析</Badge>;
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

interface GroupFileTableProps {
  files: FileItem[];
  loading: boolean;
  hasActiveFilters: boolean;
  downloadingFiles: Set<number>;
  analyzingFileIds: Set<number>;
  fileTasks: Map<number, FileTaskState>;
  onOpenAnalysis: (file: FileItem, force?: boolean) => void;
  onDownloadFile: (file: FileItem) => void;
}

export function GroupFileTable({
  files,
  loading,
  hasActiveFilters,
  downloadingFiles,
  analyzingFileIds,
  fileTasks,
  onOpenAnalysis,
  onDownloadFile,
}: GroupFileTableProps) {
  if (loading) {
    return (
      <div className="min-h-0 flex-1 overflow-auto">
        <div className="rounded-lg border border-dashed p-10 text-center text-muted-foreground">文件列表加载中...</div>
      </div>
    );
  }

  if (files.length === 0) {
    return (
      <div className="min-h-0 flex-1 overflow-auto">
        <div className="rounded-lg border border-dashed p-10 text-center text-muted-foreground">
          {hasActiveFilters
            ? '没有匹配的文件记录'
            : '当前群还没有文件记录，请先采集包含附件的话题'}
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-0 flex-1 overflow-auto">
      <div className="rounded-lg border border-gray-200">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>文件名</TableHead>
              <TableHead>大小</TableHead>
              <TableHead>下载次数</TableHead>
              <TableHead>创建时间</TableHead>
              <TableHead>下载状态</TableHead>
              <TableHead>分析状态</TableHead>
              <TableHead className="text-right">操作</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {files.map((file) => {
              const downloaded = isFileDownloaded(file);
              const creatingTask = downloadingFiles.has(file.file_id);
              const analyzing = analyzingFileIds.has(file.file_id);
              const fileTask = fileTasks.get(file.file_id);

              return (
                <TableRow key={file.file_id}>
                  <TableCell className="min-w-[260px] max-w-xl whitespace-normal">
                    <div className="flex min-w-0 items-center gap-2">
                      <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                      <div className="min-w-0">
                        <div className="truncate font-medium" title={file.name}>{file.name}</div>
                        {file.local_path && (
                          <div className="mt-1 truncate text-xs text-muted-foreground" title={file.local_path}>
                            {file.local_path}
                          </div>
                        )}
                      </div>
                    </div>
                  </TableCell>
                  <TableCell>{formatFileSize(file.size)}</TableCell>
                  <TableCell>{file.download_count || 0}</TableCell>
                  <TableCell>{formatDate(file.create_time)}</TableCell>
                  <TableCell>{getDownloadStatusBadge(file)}</TableCell>
                  <TableCell>
                    <div className="space-y-1">
                      {getAnalysisStatusBadge(file)}
                      {file.analysis_updated_at && (
                        <div className="text-xs text-muted-foreground">
                          {formatDate(file.analysis_updated_at)}
                        </div>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex flex-col items-end gap-1">
                      {downloaded ? (
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={analyzing}
                          onClick={() => onOpenAnalysis(file, false)}
                        >
                          {analyzing ? (
                            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                          ) : (
                            <Sparkles className="h-4 w-4 mr-2" />
                          )}
                          {analyzing ? '分析中' : file.has_ai_analysis ? '查看分析' : 'AI 分析'}
                        </Button>
                      ) : (
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={creatingTask}
                          onClick={() => onDownloadFile(file)}
                        >
                          {creatingTask ? (
                            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                          ) : (
                            <Download className="h-4 w-4 mr-2" />
                          )}
                          {creatingTask ? '创建中' : file.download_status === 'failed' ? '重试' : '下载'}
                        </Button>
                      )}
                      {fileTask && !downloaded && (
                        <div className={`max-w-48 truncate text-xs ${
                          fileTask.status === 'failed' || fileTask.status === 'cancelled'
                            ? 'text-red-600'
                            : fileTask.status === 'completed'
                              ? 'text-green-600'
                              : 'text-muted-foreground'
                        }`} title={fileTask.message}>
                          {fileTask.message}
                        </div>
                      )}
                      {!fileTask && file.download_status === 'failed' && file.download_error_message && (
                        <div className="max-w-48 truncate text-xs text-red-600" title={file.download_error_message}>
                          {file.download_error_code ? `${file.download_error_code}: ` : ''}{file.download_error_message}
                        </div>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
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

interface FileAnalysisDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  selectedFile: FileItem | null;
  analysis: FileAIAnalysis | null;
  analysisLoading: boolean;
  onReanalyze: (file: FileItem) => void;
}

export function FileAnalysisDialog({
  open,
  onOpenChange,
  selectedFile,
  analysis,
  analysisLoading,
  onReanalyze,
}: FileAnalysisDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-3xl max-h-[85vh] overflow-auto">
        <DialogHeader>
          <DialogTitle>{selectedFile?.name || '文件 AI 分析'}</DialogTitle>
          <DialogDescription>
            基于本地已下载文件内容生成摘要；当前优先支持 txt/md/csv/json/docx/pdf 和 mp3
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="flex items-center justify-between gap-3">
            <div className="text-sm text-muted-foreground">
              {selectedFile ? `文件大小：${formatFileSize(selectedFile.size)}` : ''}
            </div>
            {selectedFile && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => onReanalyze(selectedFile)}
                disabled={analysisLoading}
              >
                <RefreshCw className={`h-4 w-4 mr-2 ${analysisLoading ? 'animate-spin' : ''}`} />
                重新分析
              </Button>
            )}
          </div>

          {analysisLoading ? (
            <div className="rounded-lg border border-dashed p-10 text-center text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin mx-auto mb-3" />
              AI 正在分析文件内容...
            </div>
          ) : analysis?.status === 'failed' ? (
            <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
              {analysis.error_message || '分析失败'}
            </div>
          ) : (
            <>
              <div className="rounded-lg border border-gray-200 bg-gray-50 p-3 text-sm">
                <div>模型：{analysis?.model || '未知'}</div>
                <div>接口：{analysis?.wire_api || '未知'}</div>
                <div>最近更新时间：{formatDate(analysis?.updated_at)}</div>
              </div>

              <details open className="rounded-lg border border-gray-200 p-4">
                <summary className="cursor-pointer text-sm font-medium">AI 总结</summary>
                <div className="mt-3 whitespace-pre-wrap text-sm leading-6">
                  {analysis?.summary || '暂无分析结果'}
                </div>
              </details>

              {(analysis?.extracted_text || analysis?.extracted_text_preview) && (
                <details className="rounded-lg border border-gray-200 p-4">
                  <summary className="cursor-pointer text-sm font-medium">
                    {getExtractedTextLabel(analysis?.content_type)}
                  </summary>
                  <div className="mt-3 whitespace-pre-wrap text-xs leading-6 text-muted-foreground">
                    {analysis?.extracted_text || analysis?.extracted_text_preview}
                  </div>
                </details>
              )}
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
