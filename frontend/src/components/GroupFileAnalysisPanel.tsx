'use client';

import { useEffect, useState } from 'react';
import { FileText, Loader2, RefreshCw, Sparkles } from 'lucide-react';
import { apiClient, FileAIAnalysis, FileItem, PaginatedResponse } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { toast } from 'sonner';


interface GroupFileAnalysisPanelProps {
  groupId: number;
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

export default function GroupFileAnalysisPanel({ groupId }: GroupFileAnalysisPanelProps) {
  const [files, setFiles] = useState<FileItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalFiles, setTotalFiles] = useState(0);
  const [analysisOpen, setAnalysisOpen] = useState(false);
  const [selectedFile, setSelectedFile] = useState<FileItem | null>(null);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [analysis, setAnalysis] = useState<FileAIAnalysis | null>(null);

  const isFileDownloaded = (file: FileItem) =>
    Boolean(file.local_exists || file.local_path);

  const loadFiles = async (targetPage: number = page) => {
    try {
      setLoading(true);
      const data: PaginatedResponse<FileItem> = await apiClient.getFiles(groupId, targetPage, 20);
      setFiles(data.data || []);
      setPage(data.pagination.page);
      setTotalPages(data.pagination.pages || 1);
      setTotalFiles(data.pagination.total || 0);
    } catch (error) {
      toast.error(`加载文件列表失败: ${error instanceof Error ? error.message : '未知错误'}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadFiles(1);
  }, [groupId]);

  const openAnalysisDialog = async (file: FileItem, force: boolean = false) => {
    try {
      setSelectedFile(file);
      setAnalysis(null);
      setAnalysisOpen(true);
      setAnalysisLoading(true);

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
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="text-sm text-muted-foreground">
          当前群文件数：{totalFiles}
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => void loadFiles(page)}
          disabled={loading}
        >
          <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
          刷新
        </Button>
      </div>

      {loading ? (
        <div className="rounded-lg border border-dashed p-10 text-center text-muted-foreground">文件列表加载中...</div>
      ) : files.length === 0 ? (
        <div className="rounded-lg border border-dashed p-10 text-center text-muted-foreground">
          当前群还没有文件记录，请先收集或下载文件
        </div>
      ) : (
        <div className="space-y-3">
          {files.map((file) => (
            <Card key={file.file_id} className="border border-gray-200 shadow-none">
              <CardContent className="p-4">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
                      <div className="font-medium truncate" title={file.name}>{file.name}</div>
                      {file.has_ai_analysis && (
                        <Badge variant="secondary">已有分析</Badge>
                      )}
                    </div>
                    <div className="mt-2 flex flex-wrap gap-3 text-xs text-muted-foreground">
                      <span>大小：{formatFileSize(file.size)}</span>
                      <span>下载次数：{file.download_count || 0}</span>
                      <span>创建时间：{formatDate(file.create_time)}</span>
                      <span>状态：{file.download_status || 'unknown'}</span>
                    </div>
                    {file.analysis_updated_at && (
                      <div className="mt-2 text-xs text-muted-foreground">
                        最近分析：{formatDate(file.analysis_updated_at)}
                      </div>
                    )}
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={!isFileDownloaded(file)}
                      onClick={() => void openAnalysisDialog(file, false)}
                    >
                      <Sparkles className="h-4 w-4 mr-2" />
                      {isFileDownloaded(file) ? 'AI分析' : '需先下载'}
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3 pt-2">
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
