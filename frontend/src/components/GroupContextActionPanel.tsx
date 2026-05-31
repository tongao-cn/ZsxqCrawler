'use client';

import { toast } from 'sonner';

import GroupActionPanel, { type GroupActionPanelProps } from '@/components/GroupActionPanel';
import type { useCrawlActions } from '@/hooks/useCrawlActions';
import type { useDownloadActions } from '@/hooks/useDownloadActions';

type CrawlActions = ReturnType<typeof useCrawlActions>;
type DownloadActions = ReturnType<typeof useDownloadActions>;

interface GroupContextActionPanelProps {
  activeTab: string;
  crawlActions: CrawlActions;
  downloadActions: DownloadActions;
  localFileCount: number;
  localFileStats: GroupActionPanelProps['download']['localFileStats'];
  sourceFileCount?: number | string;
  topicsCount: number;
}

export default function GroupContextActionPanel({
  activeTab,
  crawlActions,
  downloadActions,
  localFileCount,
  localFileStats,
  sourceFileCount,
  topicsCount,
}: GroupContextActionPanelProps) {
  return (
    <GroupActionPanel
      mode={{
        activeMode: activeTab === 'files' ? 'download' : 'crawl',
      }}
      crawl={{
        selectedOption: crawlActions.selectedCrawlOption || 'all',
        onSelectedOptionChange: crawlActions.setSelectedCrawlOption,
        loading: crawlActions.crawlLoading,
        topicsCount,
        singleTopicId: crawlActions.singleTopicId,
        onSingleTopicIdChange: crawlActions.setSingleTopicId,
        fetchingSingle: crawlActions.fetchingSingle,
        quickLastDays: crawlActions.quickLastDays,
        onQuickLastDaysChange: crawlActions.setQuickLastDays,
        crawlMonth: crawlActions.crawlMonth,
        onCrawlMonthChange: crawlActions.setCrawlMonth,
        topicSource: crawlActions.topicSource,
        onTopicSourceChange: crawlActions.setTopicSource,
        latestDialogOpen: crawlActions.latestDialogOpen,
        onLatestDialogOpenChange: crawlActions.setLatestDialogOpen,
        settingsOpen: crawlActions.crawlSettingsOpen,
        onSettingsOpenChange: crawlActions.setCrawlSettingsOpen,
        crawlInterval: crawlActions.crawlInterval,
        longSleepInterval: crawlActions.crawlLongSleepInterval,
        pagesPerBatch: crawlActions.crawlPagesPerBatch,
        onSettingsChange: crawlActions.handleCrawlSettingsChange,
      }}
      download={{
        selectedOption: downloadActions.selectedDownloadOption || 'time',
        onSelectedOptionChange: downloadActions.setSelectedDownloadOption,
        loading: downloadActions.fileLoading,
        localFileCount,
        localFileStats,
        sourceFileCount,
        dialogOpen: downloadActions.downloadDialogOpen,
        onDialogOpenChange: downloadActions.setDownloadDialogOpen,
        quickLastDays: downloadActions.downloadQuickLastDays,
        onQuickLastDaysChange: downloadActions.setDownloadQuickLastDays,
        rangeStartDate: downloadActions.downloadRangeStartDate,
        onRangeStartDateChange: downloadActions.setDownloadRangeStartDate,
        rangeEndDate: downloadActions.downloadRangeEndDate,
        onRangeEndDateChange: downloadActions.setDownloadRangeEndDate,
        settingsOpen: downloadActions.showSettingsDialog,
        onSettingsOpenChange: downloadActions.setShowSettingsDialog,
        downloadInterval: downloadActions.downloadInterval,
        longSleepInterval: downloadActions.longSleepInterval,
        filesPerBatch: downloadActions.filesPerBatch,
        downloadIntervalMin: downloadActions.downloadIntervalMin,
        downloadIntervalMax: downloadActions.downloadIntervalMax,
        longSleepIntervalMin: downloadActions.longSleepIntervalMin,
        longSleepIntervalMax: downloadActions.longSleepIntervalMax,
        useRandomInterval: downloadActions.useRandomInterval,
        onSettingsChange: downloadActions.handleSettingsChange,
      }}
      actions={{
        onFetchSingleTopic: crawlActions.handleFetchSingleTopic,
        onCrawlAll: crawlActions.handleCrawlAll,
        onCrawlLatest: crawlActions.handleCrawlLatest,
        onCrawlLastDays: crawlActions.handleCrawlLastDays,
        onCrawlMonth: crawlActions.handleCrawlMonth,
        onIncrementalCrawl: crawlActions.handleIncrementalCrawl,
        onDeleteTopics: crawlActions.handleDeleteTopics,
        onDownloadByTime: downloadActions.handleDownloadByTime,
        onDownloadByCount: downloadActions.handleDownloadByCount,
        onClearFileDatabase: downloadActions.handleClearFileDatabase,
        onEmptyTopicsBlocked: () => toast.error('数据库为空，请先执行全量爬取'),
        onEmptyFilesBlocked: () => toast.error('当前没有可下载的文件记录，请先采集包含附件的话题'),
      }}
    />
  );
}
