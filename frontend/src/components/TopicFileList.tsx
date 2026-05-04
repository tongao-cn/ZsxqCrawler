'use client';

import { memo } from 'react';
import { Archive, Download, File, FileAudio, FileImage, FileText, FileVideo, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { FileStatus } from '@/lib/api';

const FILE_SIZE_UNITS = ['B', 'KB', 'MB', 'GB'];

const getFileIcon = (fileName: string) => {
  const ext = fileName.split('.').pop()?.toLowerCase();
  const iconProps = { className: 'w-6 h-6 text-gray-600' };

  switch (ext) {
    case 'pdf':
      return <FileText {...iconProps} className="w-6 h-6 text-red-600" />;
    case 'doc':
    case 'docx':
      return <FileText {...iconProps} className="w-6 h-6 text-blue-600" />;
    case 'xls':
    case 'xlsx':
      return <FileText {...iconProps} className="w-6 h-6 text-green-600" />;
    case 'ppt':
    case 'pptx':
      return <FileText {...iconProps} className="w-6 h-6 text-orange-600" />;
    case 'zip':
    case 'rar':
    case '7z':
      return <Archive {...iconProps} className="w-6 h-6 text-purple-600" />;
    case 'jpg':
    case 'jpeg':
    case 'png':
    case 'gif':
      return <FileImage {...iconProps} className="w-6 h-6 text-pink-600" />;
    case 'mp4':
    case 'avi':
    case 'mov':
      return <FileVideo {...iconProps} className="w-6 h-6 text-indigo-600" />;
    case 'mp3':
    case 'wav':
    case 'flac':
      return <FileAudio {...iconProps} className="w-6 h-6 text-yellow-600" />;
    case 'txt':
      return <FileText {...iconProps} />;
    default:
      return <File {...iconProps} />;
  }
};

const formatDateTime = (dateString: string) => {
  if (!dateString) return '未知时间';
  try {
    const date = new Date(dateString);
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    });
  } catch {
    return '时间格式错误';
  }
};

const formatFileSize = (bytes: number) => {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${FILE_SIZE_UNITS[i]}`;
};

interface TopicFileListProps {
  files: any[];
  fileStatuses: Map<number, FileStatus>;
  downloadingFiles: Set<number>;
  onGetFileStatus: (fileId: number, fileName?: string, fileSize?: number) => Promise<FileStatus>;
  onDownloadFile: (fileId: number, fileName: string, fileSize?: number) => void;
}

function TopicFileList({
  files,
  fileStatuses,
  downloadingFiles,
  onGetFileStatus,
  onDownloadFile,
}: TopicFileListProps) {
  if (!files || files.length === 0) {
    return null;
  }

  return (
    <div className="space-y-2 w-full max-w-full overflow-hidden" style={{width: '100%', maxWidth: '100%', boxSizing: 'border-box'}}>
      <div className="space-y-2">
        {files.map((file: any) => {
          const fileStatus = fileStatuses.get(file.file_id);
          const isDownloading = downloadingFiles.has(file.file_id);
          const isDownloaded = fileStatus?.is_complete || false;

          return (
            <div key={file.file_id} className={`flex items-center gap-3 p-3 rounded-lg border ${
              isDownloaded
                ? 'bg-green-50 border-green-200'
                : 'bg-gray-50 border-gray-200'
            }`}>
              <div className="flex-shrink-0">
                {getFileIcon(file.name)}
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium text-gray-900 truncate" title={file.name}>
                  {file.name}
                </div>
                <div className="text-xs text-gray-500 flex items-center gap-2">
                  <span>{formatFileSize(file.size)}</span>
                  {file.download_count > 0 && (
                    <span>• 下载 {file.download_count} 次</span>
                  )}
                  {file.create_time && (
                    <span>• {formatDateTime(file.create_time)}</span>
                  )}
                  {fileStatus && (
                    <span className={`• ${
                      fileStatus.download_status === 'not_collected' ? 'text-gray-500' :
                      fileStatus.is_complete ? 'text-green-600' : 'text-orange-600'
                    }`}>
                      {fileStatus.download_status === 'not_collected' ? '未下载' :
                       fileStatus.is_complete ? '已下载' : '未下载'}
                    </span>
                  )}
                </div>
                {fileStatus?.local_path && (
                  <div className="text-xs text-green-600 mt-1 truncate" title={fileStatus.local_path}>
                    📁 {fileStatus.local_path}
                  </div>
                )}
              </div>
              <div className="flex-shrink-0">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={async () => {
                    const latestStatus = await onGetFileStatus(file.file_id, file.name, file.size);

                    if (latestStatus?.is_complete) {
                      toast.info(`文件已存在: ${latestStatus.local_path}`);
                      return;
                    }

                    onDownloadFile(file.file_id, file.name, file.size);
                  }}
                  disabled={isDownloading}
                  className="flex items-center gap-1"
                >
                  {isDownloading ? (
                    <>
                      <RefreshCw className="w-3 h-3 animate-spin" />
                      下载中
                    </>
                  ) : (
                    <>
                      <Download className="w-3 h-3" />
                      下载
                    </>
                  )}
                </Button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default memo(TopicFileList);
