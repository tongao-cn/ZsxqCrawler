'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { ColumnInfo, ColumnTopic, ColumnsStats } from '@/lib/api';
import { FileText, FolderOpen, Trash2 } from 'lucide-react';

interface ColumnsNavStatsProps {
  stats: ColumnsStats | null;
}

export function ColumnsNavStats({ stats }: ColumnsNavStatsProps) {
  if (!stats) return null;

  return (
    <div className="flex items-center gap-3 text-xs">
      <span className="text-blue-600 font-medium">{stats.columns_count} 专栏</span>
      <span className="text-gray-300">|</span>
      <span className="text-green-600 font-medium">{stats.details_count} 文章</span>
      <span className="text-gray-300">|</span>
      <span className="text-purple-600 font-medium">{stats.files_downloaded}/{stats.files_count} 文件</span>
      <span className="text-gray-300">|</span>
      <span className="text-rose-600 font-medium">{stats.videos_downloaded}/{stats.videos_count} 视频</span>
      <span className="text-gray-300">|</span>
      <span className="text-orange-600 font-medium">{stats.images_count} 图片</span>
    </div>
  );
}

interface ColumnsListProps {
  columns: ColumnInfo[];
  selectedColumnId?: number;
  onSelectColumn: (column: ColumnInfo) => void;
}

export function ColumnsList({ columns, selectedColumnId, onSelectColumn }: ColumnsListProps) {
  return (
    <div className="space-y-1">
      {columns.map((column) => (
        <button
          key={column.column_id}
          onClick={() => onSelectColumn(column)}
          className={`w-full text-left px-3 py-2 rounded-lg transition-colors flex items-center justify-between ${
            selectedColumnId === column.column_id
              ? 'bg-amber-100 text-amber-800 border border-amber-200'
              : 'hover:bg-gray-100 text-gray-700'
          }`}
        >
          <div className="flex items-center gap-2 min-w-0">
            <FolderOpen className="h-4 w-4 flex-shrink-0" />
            <span className="truncate text-sm">{column.name}</span>
          </div>
          <Badge variant="secondary" className="flex-shrink-0 text-xs">
            {column.topics_count}
          </Badge>
        </button>
      ))}
    </div>
  );
}

interface ColumnTopicListProps {
  topics: ColumnTopic[];
  selectedTopicId?: number;
  loading: boolean;
  formatTime: (time?: string) => string;
  onSelectTopic: (topic: ColumnTopic) => void;
}

export function ColumnTopicList({
  topics,
  selectedTopicId,
  loading,
  formatTime,
  onSelectTopic,
}: ColumnTopicListProps) {
  if (loading) {
    return <div className="text-center text-gray-500 py-8">加载中...</div>;
  }

  if (topics.length === 0) {
    return (
      <div className="text-center text-gray-500 py-8">
        暂无文章，请先采集专栏内容
      </div>
    );
  }

  return (
    <div className="space-y-1">
      {topics.map((topic) => (
        <button
          key={topic.topic_id}
          onClick={() => onSelectTopic(topic)}
          className={`w-full text-left px-3 py-2 rounded-lg transition-colors ${
            selectedTopicId === topic.topic_id
              ? 'bg-blue-50 text-blue-800 border border-blue-200'
              : topic.has_detail
                ? 'hover:bg-gray-50 text-gray-700'
                : 'hover:bg-gray-50 text-gray-400'
          }`}
        >
          <div className="flex items-start gap-2">
            <FileText className={`h-4 w-4 mt-0.5 flex-shrink-0 ${
              topic.has_detail ? '' : 'opacity-50'
            }`} />
            <div className="min-w-0 flex-1">
              <div className={`text-sm font-medium truncate ${
                topic.has_detail ? '' : 'opacity-50'
              }`}>
                {topic.title || '无标题'}
              </div>
              <div className="text-xs text-gray-400 mt-0.5">
                {formatTime(topic.create_time)}
              </div>
            </div>
            {!topic.has_detail && (
              <Badge variant="outline" className="text-xs flex-shrink-0 opacity-50">
                未采集
              </Badge>
            )}
          </div>
        </button>
      ))}
    </div>
  );
}

interface DeleteColumnsDialogProps {
  open: boolean;
  deleting: boolean;
  stats: ColumnsStats | null;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => Promise<void>;
}

export function DeleteColumnsDialog({
  open,
  deleting,
  stats,
  onOpenChange,
  onConfirm,
}: DeleteColumnsDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className="flex items-center gap-2 text-red-600 hover:text-red-700 hover:bg-red-50 border-red-200"
          disabled={deleting || !stats || stats.columns_count === 0}
        >
          <Trash2 className="h-4 w-4" />
          清空数据
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="text-red-600">确认删除所有专栏数据</DialogTitle>
          <DialogDescription asChild>
            <div>
              <span>此操作将删除该群组的所有专栏数据，包括：</span>
              <ul className="mt-2 space-y-1 text-sm">
                <li>• {stats?.columns_count || 0} 个专栏目录</li>
                <li>• {stats?.topics_count || 0} 篇文章列表</li>
                <li>• {stats?.details_count || 0} 篇文章详情</li>
                <li>• {stats?.files_count || 0} 个文件记录</li>
                <li>• {stats?.videos_count || 0} 个视频记录</li>
                <li>• {stats?.images_count || 0} 张图片记录</li>
              </ul>
              <div className="mt-3 text-red-500 font-medium">
                删除后可重新采集，但本地已下载的文件不会被删除。
              </div>
            </div>
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button
            variant="destructive"
            onClick={onConfirm}
            disabled={deleting}
          >
            {deleting ? '删除中...' : '确认删除'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
