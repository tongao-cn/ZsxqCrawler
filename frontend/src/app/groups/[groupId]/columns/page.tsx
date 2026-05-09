'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { 
  ArrowLeft, BookOpen, FileText, RefreshCw,
  FolderOpen
} from 'lucide-react';
import TaskLogViewer from '@/components/TaskLogViewer';
import ColumnTopicDetailView from '@/components/ColumnTopicDetailView';
import ColumnsSettingsDialog from '@/components/ColumnsSettingsDialog';
import { ColumnTopicList, ColumnsList, ColumnsNavStats, DeleteColumnsDialog } from '@/components/ColumnsOverviewPanels';
import { useColumnsActions } from '@/hooks/useColumnsActions';
import { useColumnsDataLoaders } from '@/hooks/useColumnsDataLoaders';
import { formatColumnTime } from '@/lib/column-formatters';

export default function ColumnsPage() {
  const params = useParams();
  const router = useRouter();
  const groupId = params.groupId as string;

  const {
    columns,
    stats,
    selectedColumn,
    columnTopics,
    selectedTopic,
    loading,
    topicsLoading,
    detailLoading,
    loadingComments,
    loadColumns,
    resetColumnsData,
    handleFetchMoreComments,
    handleSelectColumn,
    handleSelectTopic,
  } = useColumnsDataLoaders(groupId);

  const {
    fetchingColumns,
    currentTaskId,
    deleting,
    handleFetchColumns,
    handleDeleteAllColumns,
    clearColumnsTask,
    handleTaskStop,
  } = useColumnsActions({ groupId, loadColumns, resetColumnsData });
  
  // 删除确认对话框
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);

  // 日志面板宽度（可拖拽调整）
  const [logPanelWidth, setLogPanelWidth] = useState(384); // 默认 w-96 = 384px
  const [isResizing, setIsResizing] = useState(false);
  const resizeRef = useRef<HTMLDivElement>(null);

  // 处理拖拽调整宽度
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsResizing(true);
  }, []);

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizing) return;
      
      // 计算新宽度（从右边界开始）
      const newWidth = window.innerWidth - e.clientX;
      // 限制宽度范围：最小 280px，最大 800px
      const clampedWidth = Math.max(280, Math.min(800, newWidth));
      setLogPanelWidth(clampedWidth);
    };

    const handleMouseUp = () => {
      setIsResizing(false);
    };

    if (isResizing) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
      // 拖拽时禁止选择文本
      document.body.style.userSelect = 'none';
      document.body.style.cursor = 'col-resize';
    }

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
    };
  }, [isResizing]);

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-gray-500">加载中...</div>
      </div>
    );
  }

  return (
    <div className="h-screen bg-gray-50 flex flex-col overflow-hidden">
      {/* 顶部导航栏 */}
      <div className="flex-shrink-0 p-4 bg-white border-b border-gray-200">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Button
              variant="ghost"
              onClick={() => router.push(`/groups/${groupId}`)}
              className="flex items-center gap-2"
            >
              <ArrowLeft className="h-4 w-4" />
              返回群组
            </Button>
            <div className="flex items-center gap-2">
              <BookOpen className="h-5 w-5 text-amber-600" />
              <h1 className="text-lg font-semibold text-gray-900">专栏课程</h1>
            </div>
            
            {/* 导航栏中的统计信息 */}
            <ColumnsNavStats stats={stats} />
          </div>
          
          <div className="flex items-center gap-3">
            <Button
              variant="outline"
              size="sm"
              onClick={loadColumns}
              className="flex items-center gap-2"
            >
              <RefreshCw className="h-4 w-4" />
              刷新
            </Button>
            
            <DeleteColumnsDialog
              open={deleteDialogOpen}
              deleting={deleting}
              stats={stats}
              onOpenChange={setDeleteDialogOpen}
              onConfirm={async () => {
                await handleDeleteAllColumns();
                setDeleteDialogOpen(false);
              }}
            />
            
            <ColumnsSettingsDialog
              fetchingColumns={fetchingColumns}
              onSubmit={handleFetchColumns}
            />
          </div>
        </div>
      </div>

      {/* 主体内容 - 动态布局 */}
      <div className="flex-1 flex min-h-0">
        {/* 左侧：专栏目录 */}
        <div className="w-64 flex-shrink-0 border-r border-gray-200 bg-white">
          <div className="h-full flex flex-col">
            <div className="p-4 border-b border-gray-200">
              <h2 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
                <FolderOpen className="h-4 w-4" />
                专栏目录
              </h2>
            </div>
            <ScrollArea className="flex-1">
              <div className="p-2">
                {columns.length === 0 ? (
                  <div className="text-center text-gray-400 py-8 text-sm">
                    暂无专栏数据
                    <br />
                    请先采集专栏内容
                  </div>
                ) : (
                  <ColumnsList
                    columns={columns}
                    selectedColumnId={selectedColumn?.column_id}
                    onSelectColumn={handleSelectColumn}
                  />
                )}
              </div>
            </ScrollArea>
          </div>
        </div>

        {/* 中间：文章列表 */}
        <div className="w-80 flex-shrink-0 border-r border-gray-200 bg-white">
          <div className="h-full flex flex-col">
            <div className="p-4 border-b border-gray-200">
              <h2 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
                <FileText className="h-4 w-4" />
                {selectedColumn?.name || '文章列表'}
                {selectedColumn && (
                  <Badge variant="secondary" className="text-xs">
                    {columnTopics.length}
                  </Badge>
                )}
              </h2>
            </div>
            <ScrollArea className="flex-1">
              <div className="p-2">
                {!selectedColumn ? (
                  <div className="text-center text-gray-400 py-8 text-sm">
                    请选择一个专栏
                  </div>
                ) : (
                  <ColumnTopicList
                    topics={columnTopics}
                    selectedTopicId={selectedTopic?.topic_id}
                    loading={topicsLoading}
                    formatTime={formatColumnTime}
                    onSelectTopic={handleSelectTopic}
                  />
                )}
              </div>
            </ScrollArea>
          </div>
        </div>

        {/* 文章详情区域 */}
        <div className="flex-1 bg-white min-w-0">
          <ColumnTopicDetailView
            groupId={groupId}
            selectedTopic={selectedTopic}
            detailLoading={detailLoading}
            loadingComments={loadingComments}
            onFetchMoreComments={handleFetchMoreComments}
          />
        </div>

        {/* 右侧：任务日志面板 - inline 模式（可拖拽调整宽度） */}
        {currentTaskId && (
          <>
            {/* 拖拽分隔条 */}
            <div
              ref={resizeRef}
              onMouseDown={handleMouseDown}
              className={`w-1 flex-shrink-0 cursor-col-resize hover:bg-blue-400 transition-colors ${
                isResizing ? 'bg-blue-500' : 'bg-gray-300'
              }`}
              title="拖拽调整宽度"
            />
            {/* 日志面板 */}
            <div 
              className="flex-shrink-0 border-l border-gray-200 bg-gradient-to-br from-slate-50 to-gray-100"
              style={{ width: logPanelWidth }}
            >
              <TaskLogViewer
                taskId={currentTaskId}
                onClose={clearColumnsTask}
                inline={true}
                onTaskStop={handleTaskStop}
              />
            </div>
          </>
        )}
      </div>
    </div>
  );
}
