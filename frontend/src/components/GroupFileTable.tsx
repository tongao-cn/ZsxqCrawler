'use client';

import { Download, FileText, Loader2, Sparkles } from 'lucide-react';

import { FileItem } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import type { FileTaskState } from '@/components/GroupFileTaskWatchers';
import { formatDate, formatFileSize, isFileDownloaded } from '@/components/GroupFileAnalysisPanelParts';

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
