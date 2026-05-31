'use client';

import dynamic from 'next/dynamic';

import { Card, CardContent } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import GroupCrawlActionPanel from '@/components/GroupCrawlActionPanel';
import GroupDownloadActionPanel from '@/components/GroupDownloadActionPanel';

const CrawlSettingsDialog = dynamic(() => import('./CrawlSettingsDialog'), {
  ssr: false,
});

const DownloadSettingsDialog = dynamic(() => import('./DownloadSettingsDialog'), {
  ssr: false,
});

export type GroupActionMode = 'crawl' | 'download';
export type GroupCrawlOption = 'all' | 'latest' | 'range' | 'incremental';
export type GroupDownloadOption = 'time' | 'count';
export type GroupCrawlLoading = 'historical' | 'all' | 'incremental' | 'latest' | 'range' | null;
export type GroupFileLoading = 'download-time' | 'download-count' | 'clear' | null;

export interface GroupLocalFileStats {
  total: number;
  downloaded: number;
  pending: number;
  failed: number;
}

export interface CrawlSettingsValue {
  crawlInterval: number;
  longSleepInterval: number;
  pagesPerBatch: number;
  crawlIntervalMin?: number;
  crawlIntervalMax?: number;
  longSleepIntervalMin?: number;
  longSleepIntervalMax?: number;
}

export interface DownloadSettingsValue {
  downloadInterval: number;
  longSleepInterval: number;
  filesPerBatch: number;
  downloadIntervalMin?: number;
  downloadIntervalMax?: number;
  longSleepIntervalMin?: number;
  longSleepIntervalMax?: number;
}

export interface GroupActionPanelProps {
  className?: string;
  mode: {
    activeMode: GroupActionMode;
  };
  crawl: {
    selectedOption: GroupCrawlOption;
    onSelectedOptionChange: (option: GroupCrawlOption) => void;
    loading: GroupCrawlLoading;
    topicsCount: number;
    singleTopicId: string;
    onSingleTopicIdChange: (topicId: string) => void;
    fetchingSingle: boolean;
    quickLastDays: number;
    onQuickLastDaysChange: (days: number) => void;
    crawlMonth: string;
    onCrawlMonthChange: (month: string) => void;
    topicSource: 'legacy' | 'official';
    onTopicSourceChange: (source: 'legacy' | 'official') => void;
    latestDialogOpen: boolean;
    onLatestDialogOpenChange: (open: boolean) => void;
    settingsOpen: boolean;
    onSettingsOpenChange: (open: boolean) => void;
    crawlInterval: number;
    longSleepInterval: number;
    pagesPerBatch: number;
    onSettingsChange: (settings: CrawlSettingsValue) => void;
  };
  download: {
    selectedOption: GroupDownloadOption;
    onSelectedOptionChange: (option: GroupDownloadOption) => void;
    loading: GroupFileLoading;
    localFileCount: number;
    localFileStats: GroupLocalFileStats;
    sourceFileCount?: number | string;
    dialogOpen: boolean;
    onDialogOpenChange: (open: boolean) => void;
    quickLastDays: number;
    onQuickLastDaysChange: (days: number) => void;
    rangeStartDate: string;
    onRangeStartDateChange: (date: string) => void;
    rangeEndDate: string;
    onRangeEndDateChange: (date: string) => void;
    settingsOpen: boolean;
    onSettingsOpenChange: (open: boolean) => void;
    downloadInterval: number;
    longSleepInterval: number;
    filesPerBatch: number;
    downloadIntervalMin: number;
    downloadIntervalMax: number;
    longSleepIntervalMin: number;
    longSleepIntervalMax: number;
    useRandomInterval: boolean;
    onSettingsChange: (settings: DownloadSettingsValue) => void;
  };
  actions: {
    onFetchSingleTopic: () => void;
    onCrawlAll: () => void;
    onCrawlLatest: () => void;
    onCrawlLastDays: () => void;
    onCrawlMonth: () => void;
    onIncrementalCrawl: () => void;
    onDeleteTopics: () => void;
    onDownloadByTime: () => void;
    onDownloadByCount: () => void;
    onClearFileDatabase: () => void;
    onEmptyTopicsBlocked?: () => void;
    onEmptyFilesBlocked?: () => void;
  };
}

export default function GroupActionPanel({
  className = '',
  mode,
  crawl,
  download,
  actions,
}: GroupActionPanelProps) {
  const hasTopics = crawl.topicsCount > 0;
  const hasLocalFiles = download.localFileCount > 0;
  const sourceFileCount = download.sourceFileCount ?? '?';

  const handleSelectDownload = (option: GroupDownloadOption) => {
    if (!hasLocalFiles) {
      actions.onEmptyFilesBlocked?.();
      return;
    }
    download.onSelectedOptionChange(option);
    if (option === 'time') {
      download.onDialogOpenChange(true);
    }
  };

  return (
    <>
      <div className={`w-80 flex-shrink-0 sticky top-0 h-fit max-h-full ${className}`}>
        <Card className="border border-gray-200 shadow-none h-full">
          <ScrollArea className="h-full">
            <CardContent className="p-4">
              {mode.activeMode === 'crawl' && (
                <GroupCrawlActionPanel
                  actions={actions}
                  crawl={crawl}
                  downloadLoading={download.loading}
                  hasTopics={hasTopics}
                />
              )}

              {mode.activeMode === 'download' && (
                <GroupDownloadActionPanel
                  actions={actions}
                  download={download}
                  hasLocalFiles={hasLocalFiles}
                  onSelectDownload={handleSelectDownload}
                  sourceFileCount={sourceFileCount}
                />
              )}

              {(crawl.loading || download.loading) && (
                <div className="mt-4 p-3 bg-blue-50 border border-blue-200 rounded-lg">
                  <div className="flex items-center gap-2 mb-1">
                    <div className="animate-spin rounded-full h-3 w-3 border-2 border-blue-600 border-t-transparent" />
                    <span className="text-xs font-medium text-blue-900">任务执行中</span>
                  </div>
                  <p className="text-xs text-blue-600">
                    {crawl.loading === 'historical' && '正在增量爬取历史数据...'}
                    {crawl.loading === 'all' && '正在全量爬取所有数据...'}
                    {crawl.loading === 'incremental' && '正在精确增量爬取...'}
                    {crawl.loading === 'latest' && '正在获取最新记录...'}
                    {download.loading === 'download-time' && '正在按时间顺序下载文件...'}
                    {download.loading === 'download-count' && '正在按下载次数下载文件...'}
                    {download.loading === 'clear' && '正在删除文件数据库...'}
                  </p>
                </div>
              )}
            </CardContent>
          </ScrollArea>
        </Card>
      </div>

      {download.settingsOpen && (
        <DownloadSettingsDialog
          open={download.settingsOpen}
          onOpenChange={download.onSettingsOpenChange}
          downloadInterval={download.downloadInterval}
          longSleepInterval={download.longSleepInterval}
          filesPerBatch={download.filesPerBatch}
          downloadIntervalMin={download.downloadIntervalMin}
          downloadIntervalMax={download.downloadIntervalMax}
          longSleepIntervalMin={download.longSleepIntervalMin}
          longSleepIntervalMax={download.longSleepIntervalMax}
          useRandomInterval={download.useRandomInterval}
          onSettingsChange={download.onSettingsChange}
        />
      )}

      {crawl.settingsOpen && (
        <CrawlSettingsDialog
          open={crawl.settingsOpen}
          onOpenChange={crawl.onSettingsOpenChange}
          crawlInterval={crawl.crawlInterval}
          longSleepInterval={crawl.longSleepInterval}
          pagesPerBatch={crawl.pagesPerBatch}
          onSettingsChange={crawl.onSettingsChange}
        />
      )}
    </>
  );
}
