'use client';

import { useCallback, useEffect, useState } from 'react';
import { Download, FileText, Loader2, RefreshCw, Search, Sparkles } from 'lucide-react';
import { apiClient, FileAIAnalysis, FileItem, PaginatedResponse } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { toast } from 'sonner';


interface GroupFileAnalysisPanelProps {
  groupId: number;
}

interface FileTaskState {
  taskId: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  message: string;
}

function formatFileSize(size: number) {
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

function formatDate(value?: string | null) {
  if (!value) return '未知时间';
  return new Date(value).toLocaleString('zh-CN');
}

function getExtractedTextLabel(contentType?: string | null) {
  if (contentType?.startsWith('audio/')) {
    return '转录原文';
  }
  return '提取原文';
}

function isFileDownloaded(file: FileItem) {
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

export default function GroupFileAnalysisPanel({ groupId }: GroupFileAnalysisPanelProps) {
  const [files, setFiles] = useState<FileItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalFiles, setTotalFiles] = useState(0);
  const [searchInput, setSearchInput] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [analysisOpen, setAnalysisOpen] = useState(false);
  const [selectedFile, setSelectedFile] = useState<FileItem | null>(null);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [analysis, setAnalysis] = useState<FileAIAnalysis | null>(null);
  const [downloadingFiles, setDownloadingFiles] = useState<Set<number>>(new Set());
  const [fileTasks, setFileTasks] = useState<Map<number, FileTaskState>>(new Map());
  const [analyzingFileIds, setAnalyzingFileIds] = useState<Set<number>>(new Set());
  const [batchAnalyzing, setBatchAnalyzing] = useState(false);

  const downloadedFiles = files.filter(isFileDownloaded);
  const failedFiles = files.filter((file) => !isFileDownloaded(file) && file.download_status === 'failed');
  const analyzedFiles = files.filter((file) => file.has_ai_analysis);
  const pendingAnalysisFiles = files.filter((file) => isFileDownloaded(file) && !file.has_ai_analysis);

  const loadFiles = useCallback(async (targetPage: number) => {
    try {
      setLoading(true);
      const status = statusFilter === 'all' ? undefined : statusFilter;
      const data: PaginatedResponse<FileItem> = await apiClient.getFiles(
        groupId,
        targetPage,
        20,
        status,
        searchQuery || undefined,
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
  }, [groupId, searchQuery, statusFilter]);

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

  const pollFileTask = useCallback((fileId: number, taskId: string, attempt: number = 0) => {
    window.setTimeout(async () => {
      try {
        const task = await apiClient.getTask(taskId);
        setFileTasks(prev => {
          const next = new Map(prev);
          next.set(fileId, {
            taskId,
            status: task.status,
            message: task.message,
          });
          return next;
        });

        if (['completed', 'failed', 'cancelled'].includes(task.status)) {
          setDownloadingFiles(prev => {
            const next = new Set(prev);
            next.delete(fileId);
            return next;
          });
          await loadFiles(page);
          return;
        }

        if (attempt < 120) {
          pollFileTask(fileId, taskId, attempt + 1);
          return;
        }

        setDownloadingFiles(prev => {
          const next = new Set(prev);
          next.delete(fileId);
          return next;
        });
        setFileTasks(prev => {
          const next = new Map(prev);
          next.set(fileId, {
            taskId,
            status: 'failed',
            message: '任务状态刷新超时，请手动刷新',
          });
          return next;
        });
      } catch (error) {
        console.error('轮询文件下载任务失败:', error);
        if (attempt < 12) {
          pollFileTask(fileId, taskId, attempt + 1);
          return;
        }

        setDownloadingFiles(prev => {
          const next = new Set(prev);
          next.delete(fileId);
          return next;
        });
      }
    }, 1500);
  }, [loadFiles, page]);

  const handleDownloadFile = async (file: FileItem) => {
    if (downloadingFiles.has(file.file_id)) {
      return;
    }

    try {
      setDownloadingFiles(prev => new Set(prev).add(file.file_id));
      const response = await apiClient.downloadSingleFile(
        String(groupId),
        file.file_id,
        file.name,
        file.size,
      ) as { task_id?: string };
      toast.success(response.task_id ? `文件下载任务已创建: ${response.task_id}` : '文件下载任务已创建');

      if (response.task_id) {
        setFileTasks(prev => {
          const next = new Map(prev);
          next.set(file.file_id, {
            taskId: response.task_id || '',
            status: 'pending',
            message: '下载任务已创建',
          });
          return next;
        });
        pollFileTask(file.file_id, response.task_id);
      } else {
        await loadFiles(page);
        setDownloadingFiles(prev => {
          const next = new Set(prev);
          next.delete(file.file_id);
          return next;
        });
      }
    } catch (error) {
      toast.error(`文件下载失败: ${error instanceof Error ? error.message : '未知错误'}`);
      setDownloadingFiles(prev => {
        const next = new Set(prev);
        next.delete(file.file_id);
        return next;
      });
    }
  };

  const handleBatchAnalyzeCurrentPage = async () => {
    if (pendingAnalysisFiles.length === 0 || batchAnalyzing) {
      return;
    }

    setBatchAnalyzing(true);
    toast.info(`开始分析当前页 ${pendingAnalysisFiles.length} 个文件`);

    let successCount = 0;
    for (const file of pendingAnalysisFiles) {
      try {
        setAnalyzingFileIds(prev => new Set(prev).add(file.file_id));
        await apiClient.analyzeFile(groupId, file.file_id, false);
        successCount += 1;
      } catch (error) {
        toast.error(`${file.name} 分析失败: ${error instanceof Error ? error.message : '未知错误'}`);
      } finally {
        setAnalyzingFileIds(prev => {
          const next = new Set(prev);
          next.delete(file.file_id);
          return next;
        });
      }
    }

    toast.success(`当前页批量分析完成：成功 ${successCount}/${pendingAnalysisFiles.length}`);
    await loadFiles(page);
    setBatchAnalyzing(false);
  };

  const openAnalysisDialog = async (file: FileItem, force: boolean = false) => {
    try {
      setSelectedFile(file);
      setAnalysis(null);
      setAnalysisOpen(true);
      setAnalysisLoading(true);
      setAnalyzingFileIds(prev => new Set(prev).add(file.file_id));

      if (!force && file.has_ai_analysis) {
        const cached = await apiClient.getFileAIAnalysis(groupId, file.file_id);
        if (cached.analysis) {
          setAnalysis(cached.analysis);
          setAnalysisLoading(false);
          return;
        }
      }

      const result = await apiClient.analyzeFile(groupId, file.file_id, force);
      setAnalysis(result.analysis);
      toast.success(force ? '文件已重新分析' : '文件分析完成');
      await loadFiles(page);
    } catch (error) {
      toast.error(`文件 AI 分析失败: ${error instanceof Error ? error.message : '未知错误'}`);
      setAnalysis({
        file_id: file.file_id,
        status: 'failed',
        error_message: error instanceof Error ? error.message : '未知错误',
      });
    } finally {
      setAnalysisLoading(false);
      setAnalyzingFileIds(prev => {
        const next = new Set(prev);
        next.delete(file.file_id);
        return next;
      });
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <div className="rounded-lg border border-gray-200 bg-white p-3">
          <div className="text-xs text-muted-foreground">当前结果</div>
          <div className="mt-1 text-xl font-semibold">{files.length}</div>
        </div>
        <div className="rounded-lg border border-gray-200 bg-white p-3">
          <div className="text-xs text-muted-foreground">已下载</div>
          <div className="mt-1 text-xl font-semibold text-green-700">{downloadedFiles.length}</div>
        </div>
        <div className="rounded-lg border border-gray-200 bg-white p-3">
          <div className="text-xs text-muted-foreground">下载失败</div>
          <div className="mt-1 text-xl font-semibold text-red-700">{failedFiles.length}</div>
        </div>
        <div className="rounded-lg border border-gray-200 bg-white p-3">
          <div className="text-xs text-muted-foreground">已分析</div>
          <div className="mt-1 text-xl font-semibold text-blue-700">{analyzedFiles.length}</div>
        </div>
        <div className="rounded-lg border border-gray-200 bg-white p-3">
          <div className="text-xs text-muted-foreground">待分析</div>
          <div className="mt-1 text-xl font-semibold text-amber-700">{pendingAnalysisFiles.length}</div>
        </div>
      </div>

      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="text-sm text-muted-foreground">
          当前群文件数：{totalFiles}
        </div>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <div className="flex min-w-0 gap-2 sm:w-80">
            <Input
              value={searchInput}
              placeholder="搜索文件名..."
              onChange={(event) => setSearchInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  handleSearch();
                }
              }}
            />
            <Button variant="outline" size="sm" onClick={handleSearch} disabled={loading}>
              <Search className="h-4 w-4 mr-2" />
              搜索
            </Button>
          </div>
          <Select value={statusFilter} onValueChange={handleStatusFilterChange}>
            <SelectTrigger className="w-full sm:w-36">
              <SelectValue placeholder="文件状态" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部状态</SelectItem>
              <SelectItem value="pending">未下载</SelectItem>
              <SelectItem value="completed">已完成</SelectItem>
              <SelectItem value="failed">失败</SelectItem>
              <SelectItem value="skipped">已存在</SelectItem>
            </SelectContent>
          </Select>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void loadFiles(page)}
            disabled={loading || batchAnalyzing}
          >
            <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            刷新
          </Button>
          <Button
            size="sm"
            onClick={() => void handleBatchAnalyzeCurrentPage()}
            disabled={pendingAnalysisFiles.length === 0 || batchAnalyzing}
          >
            {batchAnalyzing ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <Sparkles className="h-4 w-4 mr-2" />
            )}
            分析当前页待分析
          </Button>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-auto">
        {loading ? (
          <div className="rounded-lg border border-dashed p-10 text-center text-muted-foreground">文件列表加载中...</div>
        ) : files.length === 0 ? (
          <div className="rounded-lg border border-dashed p-10 text-center text-muted-foreground">
            {searchQuery || statusFilter !== 'all'
              ? '没有匹配的文件记录'
              : '当前群还没有文件记录，请先采集包含附件的话题'}
          </div>
        ) : (
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
                              onClick={() => void openAnalysisDialog(file, false)}
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
                              onClick={() => void handleDownloadFile(file)}
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
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </div>

      {totalPages > 1 && (
        <div className="flex flex-shrink-0 items-center justify-center gap-3 border-t border-gray-200 pt-4">
          <Button
            variant="outline"
            size="sm"
            onClick={() => void loadFiles(Math.max(1, page - 1))}
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
            onClick={() => void loadFiles(Math.min(totalPages, page + 1))}
            disabled={page === totalPages || loading}
          >
            下一页
          </Button>
        </div>
      )}

      <Dialog open={analysisOpen} onOpenChange={setAnalysisOpen}>
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
                  onClick={() => void openAnalysisDialog(selectedFile, true)}
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
    </div>
  );
}
