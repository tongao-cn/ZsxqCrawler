'use client';

import { useParams, useRouter } from 'next/navigation';
import dynamic from 'next/dynamic';
import { useState, useRef, useCallback, useDeferredValue } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Input } from '@/components/ui/input';
import { ArrowLeft, MessageSquare, Search, BarChart3, File, FileText, Archive, BookOpen, Sparkles } from 'lucide-react';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { apiClient } from '@/lib/api';
import { toast } from 'sonner';
import { ScrollArea } from '@/components/ui/scroll-area';
import GroupSidebar from '@/components/GroupSidebar';
import TopicCard from '@/components/TopicCard';
import GroupActionPanel from '@/components/GroupActionPanel';
import TopicPagination from '@/components/TopicPagination';
import { useTopicDetailsPrefetch } from '@/hooks/useTopicDetailsPrefetch';
import { useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { useTopicFileActions } from '@/hooks/useTopicFileActions';
import { useTopicActions } from '@/hooks/useTopicActions';
import { useGroupDataLoaders } from '@/hooks/useGroupDataLoaders';
import { useCrawlActions } from '@/hooks/useCrawlActions';

const LazyPanelFallback = () => (
  <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
    加载中...
  </div>
);

const TaskLogViewer = dynamic(() => import('@/components/TaskLogViewer'), {
  loading: LazyPanelFallback,
  ssr: false,
});
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
  const [fileLoading, setFileLoading] = useState<string | null>(null);
  const [currentTaskId, setCurrentTaskId] = useState<string | null>(null);
  const [activeMode, setActiveMode] = useState<'crawl' | 'download'>('crawl');
  const [activeTab, setActiveTab] = useState('topics');
  const [selectedDownloadOption, setSelectedDownloadOption] = useState<'time' | 'count' | null>('time');
  // 注意：topic_id 可能超过 JS 安全整数范围，这里统一按字符串处理 ID
  const [selectedTag, setSelectedTag] = useState<number | null>(null);
  const [clearingCache, setClearingCache] = useState(false);
  const handleTaskCreated = useCallback((taskId: string) => {
    setCurrentTaskId(taskId);
    setActiveTab('logs');
  }, []);
  const {
    fileStatuses,
    downloadingFiles,
    getFileStatus,
    downloadSingleFile,
  } = useTopicFileActions({
    groupId,
    onTaskCreated: handleTaskCreated,
  });

  const [selectedAccountId, setSelectedAccountId] = useState<string>('');
  const [assigningAccount, setAssigningAccount] = useState<boolean>(false);
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
    tags,
    tagsLoading,
    cacheInfo,
    accounts,
    groupAccount,
    accountSelf,
    hasColumns,
    columnsTitle,
    loadGroupDetail,
    loadGroupStats,
    loadTopics,
    loadLocalFileCount,
    loadTags,
    loadGroupAccount,
    loadGroupAccountSelf,
    loadCacheInfo,
  } = useGroupDataLoaders({
    groupId,
    currentPage,
    debouncedSearchTerm,
    selectedTag,
    onSelectedAccountIdChange: setSelectedAccountId,
  });

  // 话题详情缓存：key 使用字符串形式的 topic_id，避免大整数精度问题
  const topicDetails = useTopicDetailsPrefetch({
    active: activeTab === 'topics',
    groupId,
    topics,
  });
  const scrollAreaRef = useRef<HTMLDivElement>(null);

  // 下载间隔控制配置
  const [downloadInterval, setDownloadInterval] = useState<number>(1.0);
  const [longSleepInterval, setLongSleepInterval] = useState<number>(60.0);
  const [filesPerBatch, setFilesPerBatch] = useState<number>(10);
  const [showSettingsDialog, setShowSettingsDialog] = useState<boolean>(false);

  // 随机间隔范围设置
  const [downloadIntervalMin, setDownloadIntervalMin] = useState<number>(15);
  const [downloadIntervalMax, setDownloadIntervalMax] = useState<number>(30);
  const [longSleepIntervalMin, setLongSleepIntervalMin] = useState<number>(30);
  const [longSleepIntervalMax, setLongSleepIntervalMax] = useState<number>(60);
  const [useRandomInterval, setUseRandomInterval] = useState<boolean>(true);

const [downloadDialogOpen, setDownloadDialogOpen] = useState<boolean>(false);
const [downloadQuickLastDays, setDownloadQuickLastDays] = useState<number>(30);
const [downloadRangeStartDate, setDownloadRangeStartDate] = useState<string>('');
const [downloadRangeEndDate, setDownloadRangeEndDate] = useState<string>('');
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
    rangeStartDate,
    setRangeStartDate,
    rangeEndDate,
    setRangeEndDate,
    latestDialogOpen,
    setLatestDialogOpen,
    singleTopicId,
    setSingleTopicId,
    fetchingSingle,
    handleCrawlLatest,
    handleCrawlAll,
    handleIncrementalCrawl,
    handleCrawlLastDays,
    handleCrawlCustomRange,
    handleFetchSingleTopic,
    handleDeleteTopics,
    handleCrawlSettingsChange,
  } = useCrawlActions({
    groupId,
    onTaskCreated: handleTaskCreated,
    loadGroupStats,
    loadTopics,
    loadTags,
    onSelectedTagChange: setSelectedTag,
  });

  // 绑定账号到当前群组
  const handleAssignAccount = async () => {
    if (!selectedAccountId) {
      toast.error('请选择要绑定的账号');
      return;
    }
    setAssigningAccount(true);
    try {
      await apiClient.assignGroupAccount(groupId, selectedAccountId);
      toast.success('已绑定账号到该群组');
      await loadGroupAccount();
      await loadGroupAccountSelf();
    } catch (err) {
      toast.error('绑定失败');
      console.error('绑定账号失败:', err);
    } finally {
      setAssigningAccount(false);
    }
  };

  // 文件操作函数
  const handleDownloadByTime = async () => {
    if (localFileCount === 0) {
      toast.error('当前没有可下载的文件记录，请先采集包含附件的话题');
      return;
    }

    try {
      setFileLoading('download-time');
      const params: any = {
        downloadInterval,
        longSleepInterval,
        filesPerBatch,
        downloadIntervalMin: useRandomInterval ? downloadIntervalMin : undefined,
        downloadIntervalMax: useRandomInterval ? downloadIntervalMax : undefined,
        longSleepIntervalMin: useRandomInterval ? longSleepIntervalMin : undefined,
        longSleepIntervalMax: useRandomInterval ? longSleepIntervalMax : undefined,
      };
      if (downloadRangeStartDate || downloadRangeEndDate) {
        if (downloadRangeStartDate) params.startTime = downloadRangeStartDate;
        if (downloadRangeEndDate) params.endTime = downloadRangeEndDate;
      } else {
        params.lastDays = Math.max(1, downloadQuickLastDays || 1);
      }

      const response = await apiClient.downloadFilesByTimeRange(groupId, params);
      toast.success(`文件下载任务已创建: ${(response as any).task_id}`);
      // 设置当前任务ID以显示日志
      setCurrentTaskId((response as any).task_id);
      // 自动切换到日志标签页
      setActiveTab('logs');
      setDownloadDialogOpen(false);
    } catch (error) {
      toast.error(`文件下载失败: ${error instanceof Error ? error.message : '未知错误'}`);
    } finally {
      setFileLoading(null);
    }
  };

  const handleDownloadByCount = async () => {
    if (localFileCount === 0) {
      toast.error('当前没有可下载的文件记录，请先采集包含附件的话题');
      return;
    }

    try {
      setFileLoading('download-count');
      const response = await apiClient.downloadFiles(
        groupId,
        undefined,
        'download_count',
        downloadInterval,
        longSleepInterval,
        filesPerBatch,
        useRandomInterval ? downloadIntervalMin : undefined,
        useRandomInterval ? downloadIntervalMax : undefined,
        useRandomInterval ? longSleepIntervalMin : undefined,
        useRandomInterval ? longSleepIntervalMax : undefined
      );
      toast.success(`文件下载任务已创建: ${(response as any).task_id}`);
      // 设置当前任务ID以显示日志
      setCurrentTaskId((response as any).task_id);
      // 自动切换到日志标签页
      setActiveTab('logs');
    } catch (error) {
      toast.error(`文件下载失败: ${error instanceof Error ? error.message : '未知错误'}`);
    } finally {
      setFileLoading(null);
    }
  };

  const handleClearFileDatabase = async () => {
    try {
      setFileLoading('clear');
      await apiClient.clearFileDatabase(groupId);
      toast.success(`文件数据库已删除`);
      // 重新加载本地文件数量
      loadLocalFileCount();
    } catch (error) {
      toast.error(`删除文件数据库失败: ${error instanceof Error ? error.message : '未知错误'}`);
    } finally {
      setFileLoading(null);
    }
  };

  const handleSettingsChange = (settings: {
    downloadInterval: number;
    longSleepInterval: number;
    filesPerBatch: number;
    downloadIntervalMin?: number;
    downloadIntervalMax?: number;
    longSleepIntervalMin?: number;
    longSleepIntervalMax?: number;
  }) => {
    setDownloadInterval(settings.downloadInterval);
    setLongSleepInterval(settings.longSleepInterval);
    setFilesPerBatch(settings.filesPerBatch);

    // 更新随机间隔设置
    if (settings.downloadIntervalMin !== undefined) {
      setDownloadIntervalMin(settings.downloadIntervalMin);
      setDownloadIntervalMax(settings.downloadIntervalMax || 30);
      setLongSleepIntervalMin(settings.longSleepIntervalMin || 30);
      setLongSleepIntervalMax(settings.longSleepIntervalMax || 60);
      setUseRandomInterval(true);
    } else {
      setUseRandomInterval(false);
    }

    toast.success('下载设置已更新');
  };

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
    loadTags,
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

  return (
    <div className="h-screen bg-gray-50 overflow-hidden flex flex-col">
      <div className="flex-shrink-0 p-4">
        <div className="flex items-center gap-4">
          <Button
            variant="ghost"
            onClick={() => router.push('/')}
            className="flex items-center gap-2"
          >
            <ArrowLeft className="h-4 w-4" />
            返回群组列表
          </Button>

          <div className="flex items-center gap-4 flex-1 justify-center max-w-2xl mx-auto">
            {/* 专栏入口按钮 - 仅在有专栏时显示 */}
            {hasColumns && (
              <Button
                variant="outline"
                size="sm"
                className="flex items-center gap-2 whitespace-nowrap bg-gradient-to-r from-amber-50 to-orange-50 border-amber-200 hover:border-amber-300 hover:from-amber-100 hover:to-orange-100 text-amber-700"
                onClick={() => router.push(`/groups/${groupId}/columns`)}
              >
                <BookOpen className="h-4 w-4" />
                {columnsTitle || '专栏'}
              </Button>
            )}
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 h-4 w-4" />
              <Input
                placeholder="搜索话题..."
                value={searchTerm}
                onChange={(e) => {
                  setSearchTerm(e.target.value);
                }}
                className="pl-10"
              />
            </div>
            <Button onClick={() => loadTopics()} disabled={topicsLoading}>
              {topicsLoading ? '加载中...' : '刷新'}
            </Button>
          </div>

          {/* 图片缓存管理 */}
          <div className="flex items-center gap-2">
            <Dialog>
              <DialogTrigger asChild>
                <Button variant="destructive" size="sm" className="flex items-center gap-2">
                  <Archive className="h-4 w-4" />
                  清空缓存 {cacheInfo ? `(${cacheInfo.total_files}个文件 ${cacheInfo.total_size_mb}MB)` : '(加载中...)'}
                </Button>
              </DialogTrigger>
              <DialogContent className="sm:max-w-[425px]">
                <DialogHeader>
                  <DialogTitle>确认清空图片缓存</DialogTitle>
                  <DialogDescription>
                    这将删除当前群组的所有本地缓存图片文件。清空后图片将重新下载，确定要继续吗？
                  </DialogDescription>
                </DialogHeader>
                <div className="space-y-4 py-4">
                  <div className="flex items-center justify-center p-4 border rounded-lg bg-red-50">
                    <div className="text-center">
                      <div className="font-medium text-red-800">当前缓存信息</div>
                      <div className="text-sm text-red-600">
                        {cacheInfo ? `${cacheInfo.total_files}个文件 (${cacheInfo.total_size_mb}MB)` : '加载中...'}
                      </div>
                    </div>
                  </div>
                </div>
                <DialogFooter>
                  <DialogTrigger asChild>
                    <Button variant="outline">
                      取消
                    </Button>
                  </DialogTrigger>
                  <Button
                    variant="destructive"
                    onClick={clearImageCache}
                    disabled={clearingCache}
                    className="flex items-center gap-2"
                  >
                    <Archive className="h-4 w-4" />
                    {clearingCache ? '清空中...' : '确认清空'}
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </div>
        </div>
      </div>

      {/* 三列布局 - 使用flex布局，左右固定，中间滚动 */}
      <div className="flex-1 flex gap-4 px-4 pb-4 min-h-0">
        {/* 左侧：社群信息 - 固定宽度，使用sticky定位 */}
        <GroupSidebar
          group={group}
          groupStats={groupStats}
          groupInfo={groupInfo}
          localFileCount={localFileCount}
          localFileStats={localFileStats}
          tags={tags}
          tagsLoading={tagsLoading}
          selectedTag={selectedTag}
          onSelectedTagChange={(tagId) => {
            setSelectedTag(tagId);
            setCurrentPage(1);
          }}
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
        />

        {/* 中间：话题和日志 - 可滚动区域 */}
        <div className="flex-1 flex flex-col min-w-0 min-h-0">
          <Tabs value={activeTab} onValueChange={setActiveTab} className="flex flex-col h-full">
            {/* 固定的标签页头部 */}
            <div className="flex-shrink-0 mb-4">
              <TabsList className="grid w-full grid-cols-5">
                <TabsTrigger value="topics" className="flex items-center gap-2">
                  <MessageSquare className="h-4 w-4" />
                  话题列表
                </TabsTrigger>
                <TabsTrigger value="files" className="flex items-center gap-2">
                  <File className="h-4 w-4" />
                  文件
                </TabsTrigger>
                <TabsTrigger value="logs" className="flex items-center gap-2">
                  <FileText className="h-4 w-4" />
                  任务日志
                </TabsTrigger>
                <TabsTrigger value="analysis" className="flex items-center gap-2">
                  <BarChart3 className="h-4 w-4" />
                  A股分析
                </TabsTrigger>
                <TabsTrigger value="daily-analysis" className="flex items-center gap-2">
                  <Sparkles className="h-4 w-4" />
                  每日总结
                </TabsTrigger>
              </TabsList>
            </div>

            {/* 话题内容区域 */}
            <TabsContent value="topics" className="flex-1 flex flex-col min-h-0">
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
            </TabsContent>

            <TabsContent value="files" className="flex-1 flex flex-col min-h-0">
              <div className="flex-1 min-h-0 overflow-auto">
                <GroupFileAnalysisPanel groupId={groupId} />
              </div>
            </TabsContent>

            {/* 任务日志区域 */}
            <TabsContent value="logs" className="flex-1 flex flex-col min-h-0">
              <div className="flex-1 min-h-0">
                <div className="h-full bg-gradient-to-br from-slate-50 to-gray-100 rounded-lg border border-gray-200 overflow-hidden">
                  <TaskLogViewer
                    taskId={currentTaskId}
                    onClose={() => setCurrentTaskId(null)}
                    inline={true}
                    onTaskStop={() => {
                      setTimeout(() => {
                        loadGroupStats();
                        loadTopics();
                      }, 1000);
                    }}
                  />
                </div>
              </div>
            </TabsContent>

            <TabsContent value="analysis" className="flex-1 flex flex-col min-h-0">
              <div className="flex-1 min-h-0 overflow-auto">
                <AShareAnalysisPanel
                  selectedGroup={group}
                  onTaskCreated={(taskId) => {
                    setCurrentTaskId(taskId);
                    setActiveTab('logs');
                  }}
                />
              </div>
            </TabsContent>

            <TabsContent value="daily-analysis" className="flex-1 flex flex-col min-h-0">
              <div className="flex-1 min-h-0 overflow-auto">
                <DailyTopicAnalysisPanel
                  groupId={groupId}
                  onTaskCreated={(taskId) => {
                    setCurrentTaskId(taskId);
                    setActiveTab('logs');
                  }}
                />
              </div>
            </TabsContent>
          </Tabs>
        </div>



        {/* 右侧：爬取和下载菜单 - 固定宽度，使用sticky定位 */}
        <GroupActionPanel
          mode={{
            activeMode,
            onActiveModeChange: setActiveMode,
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
            rangeStartDate,
            onRangeStartDateChange: setRangeStartDate,
            rangeEndDate,
            onRangeEndDateChange: setRangeEndDate,
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
            onCrawlCustomRange: handleCrawlCustomRange,
            onIncrementalCrawl: handleIncrementalCrawl,
            onDeleteTopics: handleDeleteTopics,
            onDownloadByTime: handleDownloadByTime,
            onDownloadByCount: handleDownloadByCount,
            onClearFileDatabase: handleClearFileDatabase,
            onEmptyTopicsBlocked: () => toast.error('数据库为空，请先执行全量爬取'),
            onEmptyFilesBlocked: () => toast.error('当前没有可下载的文件记录，请先采集包含附件的话题'),
          }}
        />
      </div>

    </div>
  );
}
