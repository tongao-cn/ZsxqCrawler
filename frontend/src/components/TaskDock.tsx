'use client';

import dynamic from 'next/dynamic';
import { ChevronDown, ChevronUp, FileText, X } from 'lucide-react';

import { Button } from '@/components/ui/button';

const TaskLogViewer = dynamic(() => import('@/components/TaskLogViewer'), {
  loading: () => (
    <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
      加载中...
    </div>
  ),
  ssr: false,
});

interface TaskDockProps {
  taskId: string | null;
  expanded: boolean;
  onOpen: () => void;
  onCollapse: () => void;
  onClose: () => void;
  onTaskStop: () => void;
}

export default function TaskDock({
  taskId,
  expanded,
  onOpen,
  onCollapse,
  onClose,
  onTaskStop,
}: TaskDockProps) {
  const toggleExpanded = expanded ? onCollapse : onOpen;
  const shortTaskId = taskId ? `${taskId.slice(0, 8)}...` : null;

  return (
    <div className="fixed bottom-20 left-4 right-4 z-50 mx-auto max-w-5xl overflow-hidden rounded-lg border border-gray-200 bg-white shadow-xl lg:left-[22rem] xl:right-[22rem]">
      <div className="flex h-12 items-center justify-between gap-3 border-b border-gray-200 bg-white px-4">
        <button
          type="button"
          className="flex min-w-0 flex-1 items-center gap-3 text-left"
          onClick={toggleExpanded}
        >
          <span className={`relative flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-md ${taskId ? 'bg-blue-50 text-blue-600' : 'bg-gray-100 text-gray-400'}`}>
            <FileText className="h-4 w-4" />
            {taskId && (
              <span className="absolute -right-0.5 -top-0.5 h-2.5 w-2.5 rounded-full border-2 border-white bg-green-500" />
            )}
          </span>
          <span className="min-w-0">
            <span className="flex min-w-0 items-center gap-2">
              <span className="truncate text-sm font-medium text-gray-900">任务日志</span>
              <span className={`flex-shrink-0 rounded-full px-2 py-0.5 text-[11px] leading-4 ${taskId ? 'bg-green-50 text-green-700' : 'bg-gray-100 text-gray-500'}`}>
                {taskId ? '正在跟踪' : '暂无任务'}
              </span>
            </span>
            <span className="block truncate text-xs text-gray-500">
              {shortTaskId ? `当前任务 ${shortTaskId}，正在显示实时日志` : '执行任务后将在这里显示实时日志'}
            </span>
          </span>
        </button>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            className="h-8 gap-1 text-xs"
            onClick={toggleExpanded}
          >
            {expanded ? (
              <ChevronDown className="h-3.5 w-3.5" />
            ) : (
              <ChevronUp className="h-3.5 w-3.5" />
            )}
            {expanded ? '收起' : '展开'}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-8 w-8 p-0 text-gray-500"
            onClick={onClose}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>
      {expanded && (
        <div className="h-[38vh] min-h-[260px] max-h-[520px] bg-gradient-to-br from-slate-50 to-gray-100">
          <TaskLogViewer
            taskId={taskId}
            onClose={onCollapse}
            inline={true}
            onTaskStop={onTaskStop}
          />
        </div>
      )}
    </div>
  );
}
