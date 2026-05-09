'use client';

import { Archive, ArrowLeft, FileText, MoreHorizontal, Search } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';

interface GroupTopBarProps {
  searchTerm: string;
  onSearchTermChange: (value: string) => void;
  topicsLoading: boolean;
  onRefreshTopics: () => void;
  showTopicSearch: boolean;
  taskDockVisible: boolean;
  currentTaskId: string | null;
  onToggleTaskLog: () => void;
  cacheInfo?: {
    total_files: number;
    total_size_mb: number;
  } | null;
  clearingCache: boolean;
  onClearImageCache: () => void;
  onBack: () => void;
}

export default function GroupTopBar({
  searchTerm,
  onSearchTermChange,
  topicsLoading,
  onRefreshTopics,
  showTopicSearch,
  taskDockVisible,
  currentTaskId,
  onToggleTaskLog,
  cacheInfo,
  clearingCache,
  onClearImageCache,
  onBack,
}: GroupTopBarProps) {
  return (
    <div className="flex-shrink-0 p-4">
      <div className="flex items-center gap-4">
        <Button
          variant="ghost"
          onClick={onBack}
          className="flex items-center gap-2"
        >
          <ArrowLeft className="h-4 w-4" />
          返回群组列表
        </Button>

        <div className="flex flex-1 items-center justify-center gap-3">
          {showTopicSearch && (
            <>
              <div className="relative w-full max-w-xl">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
                <Input
                  placeholder="搜索话题..."
                  value={searchTerm}
                  onChange={(event) => onSearchTermChange(event.target.value)}
                  className="pl-10"
                />
              </div>
              <Button onClick={onRefreshTopics} disabled={topicsLoading}>
                {topicsLoading ? '加载中...' : '刷新'}
              </Button>
            </>
          )}
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant={taskDockVisible ? 'default' : 'outline'}
            size="sm"
            className="flex items-center gap-2"
            onClick={onToggleTaskLog}
          >
            <FileText className="h-4 w-4" />
            <span className="hidden xl:inline">任务日志</span>
            {currentTaskId && (
              <span className="h-2 w-2 rounded-full bg-green-500" />
            )}
          </Button>

          <Dialog>
            <DialogTrigger asChild>
              <Button variant="outline" size="sm" className="h-9 w-9 p-0">
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-[425px]">
              <DialogHeader>
                <DialogTitle>群组工具</DialogTitle>
                <DialogDescription>
                  管理当前群组的本地缓存和低频维护操作。
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-4 py-4">
                <div className="flex items-center justify-between rounded-lg border border-gray-200 p-3">
                  <div>
                    <div className="text-sm font-medium text-gray-900">图片缓存</div>
                    <div className="mt-1 text-xs text-gray-500">
                      {cacheInfo ? `${cacheInfo.total_files} 个文件，${cacheInfo.total_size_mb}MB` : '加载中...'}
                    </div>
                  </div>
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={onClearImageCache}
                    disabled={clearingCache}
                    className="flex items-center gap-2"
                  >
                    <Archive className="h-4 w-4" />
                    {clearingCache ? '清空中...' : '清空'}
                  </Button>
                </div>
              </div>
              <DialogFooter>
                <DialogTrigger asChild>
                  <Button variant="outline">关闭</Button>
                </DialogTrigger>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </div>
    </div>
  );
}
