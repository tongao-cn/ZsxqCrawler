'use client';

import { useParams, useRouter } from 'next/navigation';
import dynamic from 'next/dynamic';
import { useState, useRef, useCallback, useDeferredValue } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ArrowLeft, MessageSquare, BarChart3, File, Sparkles, TrendingUp, Search, HelpCircle } from 'lucide-react';
import { apiClient } from '@/lib/api';
import { toast } from 'sonner';
import { ScrollArea } from '@/components/ui/scroll-area';
import GroupSidebar from '@/components/GroupSidebar';
import TopicCard from '@/components/TopicCard';
import GroupActionPanel from '@/components/GroupActionPanel';
import GroupTopBar from '@/components/GroupTopBar';
import TaskDock from '@/components/TaskDock';
import TopicPagination from '@/components/TopicPagination';
import { useTopicDetailsCache } from '@/hooks/useTopicDetailsPrefetch';
import { useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { useTopicFileActions } from '@/hooks/useTopicFileActions';
import { useTopicActions } from '@/hooks/useTopicActions';
import { useGroupDataLoaders } from '@/hooks/useGroupDataLoaders';
import { useCrawlActions } from '@/hooks/useCrawlActions';
import { useDownloadActions } from '@/hooks/useDownloadActions';
import { useGroupTaskBridge } from '@/hooks/useGroupTaskBridge';
import { useGroupAccountAssignment } from '@/hooks/useGroupAccountAssignment';

const LazyPanelFallback = () => (
  <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
    加载中...
  </div>
);

const GroupFileAnalysisPanel = dynamic(() => import('@/components/GroupFileAnalysisPanel'), {
  loading: LazyPanelFallback,
  ssr: false,
});
const AShareAnalysisPanel = dynamic(() => import('@/components/AShareAnalysisPanel'), {
  loading: LazyPanelFallback,
  ssr: false,
});
const DailyTopicAnalysisPanel = dynamic(() => import('@/components/DailyTopicAnalysisPanel'), {
  loading: LazyPanelFallback,
  ssr: false,
});
const StockTopicAnalysisPanel = dynamic(() => import('@/components/StockTopicAnalysisPanel'), {
  loading: LazyPanelFallback,
  ssr: false,
});
const StockQuestionPanel = dynamic(() => import('@/components/StockQuestionPanel'), {
  loading: LazyPanelFallback,
  ssr: false,
});

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

const formatImportedTime = (importedAt: string) => {
  if (!importedAt) return '';
  try {
    const date = new Date(importedAt);
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    });
  } catch {
    return importedAt;
  }
};

export default function GroupDetailPage() {
  const params = useParams();
  const router = useRouter();
  const groupId = parseInt(params.groupId as string);

  const [currentPage, setCurrentPage] = useState(1);
  const handleDebouncedSearchChange = useCallback(() => {
    setCurrentPage(1);
  }, []);
  const { searchTerm, setSearchTerm, debouncedSearchTerm } = useDebouncedSearch({
    onDebouncedChange: handleDebouncedSearchChange,
  });
  const deferredSearchTerm = useDeferredValue(searchTerm);
  // 注意：topic_id 可能超过 JS 安全整数范围，这里统一按字符串处理 ID
  const [clearingCache, setClearingCache] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const {
    activeTab,
    setActiveTab,
    currentTaskId,
    taskDockVisible,
    taskLogExpanded,
    taskDockView,
    setTaskDockView,
    handleTaskCreated,
    selectTaskLog,
    openTaskLog,
    openTaskList,
    toggleTaskLog,
    collapseTaskLog,
    closeTaskDock,
  } = useGroupTaskBridge();
  const {
    fileStatuses,
    downloadingFiles,
    getFileStatus,
    downloadSingleFile,
  } = useTopicFileActions({
    groupId,
    onTaskCreated: handleTaskCreated,
    onTaskConflict: openTaskList,
  });

  const {
    group,
    groupStats,
    topics,
    setTopics,
    loading,
    topicsLoading,
    error,
    retryCount,
    isRetrying,
    totalPages,
    groupInfo,
    localFileCount,
    localFileStats,
    cacheInfo,
    accounts,
    groupAccount,
    selectedAccountId,
    setSelectedAccountId,
    accountSelf,
    hasColumns,
    columnsTitle,
    loadGroupDetail,
    loadGroupStats,
    loadTopics,
    loadLocalFileCount,
    loadGroupAccount,
    loadGroupAccountSelf,
    loadCacheInfo,
  } = useGroupDataLoaders({
    groupId,
    currentPage,
    debouncedSearchTerm,
  });
  const {
    assigningAccount,
    handleAssignAccount,
  } = useGroupAccountAssignment({
    groupId,
    selectedAccountId,
    loadGroupAccount,
    loadGroupAccountSelf,
  });

  // 话题详情缓存：key 使用字符串形式的 topic_id，避免大整数精度问题
  const {
    loadTopicDetail,
    topicDetails,
  } = useTopicDetailsCache({
    groupId,
  });
  const scrollAreaRef = useRef<HTMLDivElement>(null);

  const {
    fileLoading,
    selectedDownloadOption,
    setSelectedDownloadOption,
    downloadInterval,
    longSleepInterval,
    filesPerBatch,
    showSettingsDialog,
    setShowSettingsDialog,
    downloadIntervalMin,
    downloadIntervalMax,
    longSleepIntervalMin,
    longSleepIntervalMax,
    useRandomInterval,
    downloadDialogOpen,
    setDownloadDialogOpen,
    downloadQuickLastDays,
    setDownloadQuickLastDays,
    downloadRangeStartDate,
    setDownloadRangeStartDate,
    downloadRangeEndDate,
    setDownloadRangeEndDate,
    handleDownloadByTime,
    handleDownloadByCount,
    handleClearFileDatabase,
    handleSettingsChange,
  } = useDownloadActions({
    groupId,
    localFileCount,
    onTaskCreated: handleTaskCreated,
    onTaskConflict: openTaskList,
    loadLocalFileCount,
  });
  const {
    selectedCrawlOption,
    setSelectedCrawlOption,
    crawlLoading,
    crawlSettingsOpen,
    setCrawlSettingsOpen,
    crawlInterval,
    crawlLongSleepInterval,
    crawlPagesPerBatch,
    quickLastDays,
    setQuickLastDays,
    crawlMonth,
    setCrawlMonth,
    topicSource,
    setTopicSource,
    latestDialogOpen,
    setLatestDialogOpen,
    singleTopicId,
    setSingleTopicId,
    fetchingSingle,
    handleCrawlLatest,
    handleCrawlAll,
    handleIncrementalCrawl,
    handleCrawlLastDays,
    handleCrawlMonth,
    handleFetchSingleTopic,
    handleDeleteTopics,
    handleCrawlSettingsChange,
  } = useCrawlActions({
    groupId,
    onTaskCreated: handleTaskCreated,
    onTaskConflict: openTaskList,
    loadGroupStats,
    loadTopics,
  });

  const {
    expandedComments,
    expandedContent,
    fetchingComments,
    refreshingTopics,
    deletingTopics,
    toggleComments,
    toggleContent,
    refreshSingleTopic,
    deleteSingleTopicConfirmed,
    fetchMoreComments,
  } = useTopicActions({
    groupId,
    setTopics,
    loadTopics,
    loadGroupStats,
  });

  // 清空图片缓存（使用自定义弹窗，不再重复浏览器确认）
  const clearImageCache = async () => {
    setClearingCache(true);
    try {
      const response = await apiClient.clearImageCache(groupId.toString());
      if (response.success) {
        toast.success(response.message);
        await loadCacheInfo(); // 重新加载缓存信息
      } else {
        toast.error('清空缓存失败');
      }
    } catch (error) {
      toast.error('清空缓存失败');
      console.error('清空缓存失败:', error);
    } finally {
      setClearingCache(false);
    }
  };

  if (loading || isRetrying) {
    return (
      <div className="min-h-screen bg-gray-50 p-4">
        <div className="max-w-4xl mx-auto">
          <div className="text-center py-8">
            <p className="text-muted-foreground">
              {isRetrying ? `正在重试获取群组信息... (第${retryCount}次)` : '加载中...'}
            </p>
            {isRetrying && (
              <p className="text-xs text-gray-400 mt-2">
                检测到API防护机制，正在自动重试获取数据
              </p>
            )}
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gray-50 p-4">
        <div className="max-w-4xl mx-auto">
          <div className="mb-6">
            <Button
              variant="ghost"
              onClick={() => router.push('/')}
              className="flex items-center gap-2"
            >
              <ArrowLeft className="h-4 w-4" />
              返回群组列表
            </Button>
          </div>

          <Card className="max-w-md mx-auto border border-gray-200 shadow-none">
            <CardContent className="pt-6">
              <div className="text-center">
                <p className="text-red-600 mb-4">{error}</p>
                <Button onClick={() => loadGroupDetail()}>重试</Button>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    );
  }

  if (!group) {
    return (
      <div className="min-h-screen bg-gray-50 p-4">
        <div className="max-w-4xl mx-auto">
          <div className="mb-6">
            <Button
              variant="ghost"
              onClick={() => router.push('/')}
              className="flex items-center gap-2"
            >
              <ArrowLeft className="h-4 w-4" />
              返回群组列表
            </Button>
          </div>

          <Card className="max-w-md mx-auto border border-gray-200 shadow-none">
            <CardContent className="pt-6">
              <div className="text-center">
                <p className="text-muted-foreground">未找到群组信息</p>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    );
  }

  const contextActionPanel = (
    <GroupActionPanel
      mode={{
        activeMode: activeTab === 'files' ? 'download' : 'crawl',
      }}
      crawl={{
        selectedOption: selectedCrawlOption || 'all',
        onSelectedOptionChange: setSelectedCrawlOption,
        loading: crawlLoading as any,
        topicsCount: groupStats?.topics_count || 0,
        singleTopicId,
        onSingleTopicIdChange: setSingleTopicId,
        fetchingSingle,
        quickLastDays,
        onQuickLastDaysChange: setQuickLastDays,
        crawlMonth,
        onCrawlMonthChange: setCrawlMonth,
        topicSource,
        onTopicSourceChange: setTopicSource,
        latestDialogOpen,
        onLatestDialogOpenChange: setLatestDialogOpen,
        settingsOpen: crawlSettingsOpen,
        onSettingsOpenChange: setCrawlSettingsOpen,
        crawlInterval,
        longSleepInterval: crawlLongSleepInterval,
        pagesPerBatch: crawlPagesPerBatch,
        onSettingsChange: handleCrawlSettingsChange,
      }}
      download={{
        selectedOption: selectedDownloadOption || 'time',
        onSelectedOptionChange: setSelectedDownloadOption,
        loading: fileLoading as any,
        localFileCount,
        localFileStats,
        sourceFileCount: groupInfo?.statistics?.files?.count,
        dialogOpen: downloadDialogOpen,
        onDialogOpenChange: setDownloadDialogOpen,
        quickLastDays: downloadQuickLastDays,
        onQuickLastDaysChange: setDownloadQuickLastDays,
        rangeStartDate: downloadRangeStartDate,
        onRangeStartDateChange: setDownloadRangeStartDate,
        rangeEndDate: downloadRangeEndDate,
        onRangeEndDateChange: setDownloadRangeEndDate,
        settingsOpen: showSettingsDialog,
        onSettingsOpenChange: setShowSettingsDialog,
        downloadInterval,
        longSleepInterval,
        filesPerBatch,
        downloadIntervalMin,
        downloadIntervalMax,
        longSleepIntervalMin,
        longSleepIntervalMax,
        useRandomInterval,
        onSettingsChange: handleSettingsChange,
      }}
      actions={{
        onFetchSingleTopic: handleFetchSingleTopic,
        onCrawlAll: handleCrawlAll,
        onCrawlLatest: handleCrawlLatest,
        onCrawlLastDays: handleCrawlLastDays,
        onCrawlMonth: handleCrawlMonth,
        onIncrementalCrawl: handleIncrementalCrawl,
        onDeleteTopics: handleDeleteTopics,
        onDownloadByTime: handleDownloadByTime,
        onDownloadByCount: handleDownloadByCount,
        onClearFileDatabase: handleClearFileDatabase,
        onEmptyTopicsBlocked: () => toast.error('数据库为空，请先执行全量爬取'),
        onEmptyFilesBlocked: () => toast.error('当前没有可下载的文件记录，请先采集包含附件的话题'),
      }}
    />
  );

  return (
    <div className="h-screen bg-gray-50 overflow-hidden flex flex-col">
      <GroupTopBar
        searchTerm={searchTerm}
        onSearchTermChange={setSearchTerm}
        topicsLoading={topicsLoading}
        onRefreshTopics={loadTopics}
        showTopicSearch={activeTab === 'topics'}
        taskDockVisible={taskDockVisible}
        currentTaskId={currentTaskId}
        onToggleTaskLog={toggleTaskLog}
        cacheInfo={cacheInfo}
        clearingCache={clearingCache}
        onClearImageCache={clearImageCache}
        onBack={() => router.push('/')}
      />

      {/* 三列布局 - 使用flex布局，左右固定，中间滚动 */}
      <div className="flex-1 flex gap-4 px-4 pb-4 min-h-0">
        {/* 左侧：社群信息 - 固定宽度，使用sticky定位 */}
        <GroupSidebar
          group={group}
          groupStats={groupStats}
          accountSelf={accountSelf}
          accounts={accounts}
          groupAccount={groupAccount}
          selectedAccountId={selectedAccountId}
          onSelectedAccountIdChange={setSelectedAccountId}
          assigningAccount={assigningAccount}
          onAssignAccount={handleAssignAccount}
          hasColumns={hasColumns}
          columnsTitle={columnsTitle}
          onOpenColumns={() => router.push(`/groups/${groupId}/columns`)}
          collapsed={sidebarCollapsed}
          onCollapsedChange={setSidebarCollapsed}
        />

        {/* 中间：群组内容 - 可滚动区域 */}
        <div className="flex-1 flex flex-col min-w-0 min-h-0">
          <Tabs value={activeTab} onValueChange={setActiveTab} className="flex flex-col h-full">
            {/* 固定的标签页头部 */}
            <div className="flex-shrink-0 mb-4">
              <TabsList className="grid w-full grid-cols-7">
                <TabsTrigger value="topics" className="flex items-center gap-2">
                  <MessageSquare className="h-4 w-4" />
                  话题列表
                </TabsTrigger>
                <TabsTrigger value="files" className="flex items-center gap-2">
                  <File className="h-4 w-4" />
                  文件
                </TabsTrigger>
                <TabsTrigger value="analysis" className="flex items-center gap-2">
                  <BarChart3 className="h-4 w-4" />
                  股票推荐池
                </TabsTrigger>
                <TabsTrigger value="daily-analysis" className="flex items-center gap-2">
                  <Sparkles className="h-4 w-4" />
                  每日总结
                </TabsTrigger>
                <TabsTrigger value="stock-concepts" className="flex items-center gap-2">
                  <TrendingUp className="h-4 w-4" />
                  股票概念
                </TabsTrigger>
                <TabsTrigger value="stock-topic-analysis" className="flex items-center gap-2">
                  <Search className="h-4 w-4" />
                  个股分析
                </TabsTrigger>
                <TabsTrigger value="stock-question" className="flex items-center gap-2">
                  <HelpCircle className="h-4 w-4" />
                  A股问答
                </TabsTrigger>
              </TabsList>
            </div>

            {/* 话题内容区域 */}
            <TabsContent value="topics" className="flex-1 min-h-0">
              <div className="flex h-full min-h-0 gap-4">
              {/* 可滚动的话题列表区域 */}
              <div className="flex-1 flex flex-col min-h-0">
                {topicsLoading ? (
                  <div className="flex-1 flex items-center justify-center">
                    <p className="text-muted-foreground">加载中...</p>
                  </div>
                ) : topics.length === 0 ? (
                  <div className="flex-1 flex items-center justify-center">
                    <p className="text-muted-foreground">
                      {searchTerm ? '没有找到匹配的话题' : '暂无话题数据，请先进行数据采集'}
                    </p>
                  </div>
                ) : (
                  <>
                    {/* 使用ScrollArea组件实现美化的滚动条 */}
                    <ScrollArea ref={scrollAreaRef} className="flex-1 w-full">
                      <div className="topic-cards-container space-y-3 pr-4 max-w-full" style={{width: '100%', maxWidth: '100%', boxSizing: 'border-box'}}>
                        {topics.map((topic: any) => (
                          <div key={topic.topic_id} style={{width: '100%', maxWidth: '100%', boxSizing: 'border-box'}}>
                            <TopicCard
                              topic={topic}
                              searchTerm={deferredSearchTerm}
                              // 这里同样使用字符串形式的 topic_id 作为索引
                              topicDetail={topicDetails.get(String((topic as any).topic_id || ''))}
                              groupId={groupId}
                              expandedContent={expandedContent}
                              expandedComments={expandedComments}
                              refreshingTopics={refreshingTopics}
                              deletingTopics={deletingTopics}
                              fetchingComments={fetchingComments}
                              fileStatuses={fileStatuses}
                              downloadingFiles={downloadingFiles}
                              onRefreshTopic={refreshSingleTopic}
                              onDeleteTopic={deleteSingleTopicConfirmed}
                              onToggleContent={toggleContent}
                              onFetchMoreComments={fetchMoreComments}
                              onToggleComments={toggleComments}
                              onLoadTopicDetail={loadTopicDetail}
                              onGetFileStatus={getFileStatus}
                              onDownloadFile={downloadSingleFile}
                              formatDateTime={formatDateTime}
                              formatImportedTime={formatImportedTime}
                            />
                          </div>
                        ))}
                      </div>
                    </ScrollArea>

                    <TopicPagination
                      currentPage={currentPage}
                      totalPages={totalPages}
                      onPageChange={setCurrentPage}
                    />
                  </>
                )}
              </div>
              {contextActionPanel}
              </div>
            </TabsContent>

            <TabsContent value="files" className="flex-1 min-h-0">
              <div className="flex h-full min-h-0 gap-4">
              <div className="flex-1 min-h-0 overflow-auto">
                <GroupFileAnalysisPanel groupId={groupId} />
              </div>
              {contextActionPanel}
              </div>
            </TabsContent>

            <TabsContent value="analysis" className="flex-1 flex flex-col min-h-0">
              <div className="flex-1 min-h-0 overflow-auto">
                <AShareAnalysisPanel
                  selectedGroup={group}
                  onTaskCreated={handleTaskCreated}
                />
              </div>
            </TabsContent>

            <TabsContent value="daily-analysis" className="flex-1 flex flex-col min-h-0">
              <div className="flex-1 min-h-0 overflow-auto">
                <DailyTopicAnalysisPanel
                  groupId={groupId}
                  onTaskCreated={handleTaskCreated}
                  mode="report"
                />
              </div>
            </TabsContent>

            <TabsContent value="stock-concepts" className="flex-1 flex flex-col min-h-0">
              <div className="flex-1 min-h-0 overflow-auto">
                <DailyTopicAnalysisPanel
                  groupId={groupId}
                  onTaskCreated={handleTaskCreated}
                  mode="stock-concepts"
                />
              </div>
            </TabsContent>

            <TabsContent value="stock-topic-analysis" className="flex-1 flex flex-col min-h-0">
              <div className="flex-1 min-h-0 overflow-auto">
                <StockTopicAnalysisPanel
                  groupId={groupId}
                  onTaskCreated={handleTaskCreated}
                />
              </div>
            </TabsContent>

            <TabsContent value="stock-question" className="flex-1 flex flex-col min-h-0">
              <div className="flex-1 min-h-0 overflow-auto">
                <StockQuestionPanel
                  groupId={groupId}
                  onTaskCreated={handleTaskCreated}
                />
              </div>
            </TabsContent>
          </Tabs>
        </div>

      </div>

      {taskDockVisible && (
        <TaskDock
          taskId={currentTaskId}
          expanded={taskLogExpanded}
          view={taskDockView}
          groupId={groupId}
          onOpen={openTaskLog}
          onCollapse={collapseTaskLog}
          onClose={closeTaskDock}
          onViewChange={setTaskDockView}
          onTaskSelect={selectTaskLog}
          onTaskStop={() => {
            setTimeout(() => {
              loadGroupStats();
              loadTopics();
            }, 1000);
          }}
        />
      )}
    </div>
  );
}
