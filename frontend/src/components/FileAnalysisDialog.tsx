'use client';

import { Loader2, RefreshCw } from 'lucide-react';

import { FileAIAnalysis, FileItem } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { formatDate, formatFileSize, getExtractedTextLabel } from '@/components/GroupFileAnalysisPanelParts';

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
