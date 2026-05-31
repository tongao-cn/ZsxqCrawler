'use client';

import { useState } from 'react';
import dynamic from 'next/dynamic';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import {
  BarChart3,
  ChevronDown,
  ChevronRight,
  FileText,
  MessageSquare,
  RefreshCw,
  Settings,
  TrendingUp,
} from 'lucide-react';

import { MonthPickerButton } from '@/components/ui/date-picker-button';
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

function clampPositiveDays(value: string) {
  const days = Number.parseInt(value, 10);
  if (!Number.isFinite(days)) {
    return 1;
  }
  return Math.max(1, days);
}

export default function GroupActionPanel({
  className = '',
  mode,
  crawl,
  download,
  actions,
}: GroupActionPanelProps) {
  const [advancedCrawlOpen, setAdvancedCrawlOpen] = useState(false);
  const hasTopics = crawl.topicsCount > 0;
  const hasLocalFiles = download.localFileCount > 0;
  const sourceFileCount = download.sourceFileCount ?? '?';

  const handleSelectIncremental = () => {
    if (!hasTopics) {
      actions.onEmptyTopicsBlocked?.();
      return;
    }
    crawl.onSelectedOptionChange('incremental');
  };

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
                <div className="space-y-3">
                  <div className="flex items-center gap-2 text-sm font-medium text-gray-900">
                    <MessageSquare className="h-4 w-4" />
                    采集话题
                  </div>
                  <div className="space-y-4">
                    <div className="space-y-2">
                      <div className="text-xs font-medium text-gray-500">常用采集</div>
                      <div
                        className={`border rounded-lg p-3 cursor-pointer transition-all ${
                          crawl.selectedOption === 'latest'
                            ? 'bg-blue-50 border-blue-200'
                            : 'border-gray-200 hover:bg-gray-50'
                        }`}
                        onClick={() => {
                          crawl.onSelectedOptionChange('latest');
                          crawl.onLatestDialogOpenChange(true);
                        }}
                      >
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-2">
                            <RefreshCw
                              className={`h-3 w-3 ${
                                crawl.selectedOption === 'latest' ? 'text-blue-600' : 'text-gray-400'
                              }`}
                            />
                            <span
                              className={`text-xs font-medium ${
                                crawl.selectedOption === 'latest' ? 'text-blue-700' : 'text-gray-600'
                              }`}
                            >
                              获取最新
                            </span>
                          </div>
                          {hasTopics && (
                            <Badge variant="secondary" className="text-xs px-1 py-0">
                              推荐
                            </Badge>
                          )}
                        </div>
                        {crawl.selectedOption === 'latest' && (
                          <AlertDialog open={crawl.latestDialogOpen} onOpenChange={crawl.onLatestDialogOpenChange}>
                            <Button
                              size="sm"
                              className="w-full h-7 text-xs bg-blue-600 hover:bg-blue-700"
                              disabled={!!crawl.loading}
                              onClick={() => crawl.onLatestDialogOpenChange(true)}
                            >
                              {crawl.loading === 'latest' ? '执行中...' : '开始'}
                            </Button>
                            <AlertDialogContent>
                              <AlertDialogHeader>
                                <AlertDialogTitle>获取最新或按范围</AlertDialogTitle>
                                <AlertDialogDescription>
                                  默认从最新开始抓取；也可按最近天数或月份采集。
                                </AlertDialogDescription>
                              </AlertDialogHeader>
                              <div className="space-y-3">
                                <div className="text-xs text-gray-600">最近天数</div>
                                <div className="flex items-center gap-2">
                                  <Input
                                    type="number"
                                    min={1}
                                    value={crawl.quickLastDays}
                                    onChange={(event) => crawl.onQuickLastDaysChange(clampPositiveDays(event.target.value))}
                                    className="h-7 text-xs w-24"
                                  />
                                  <span className="text-xs text-gray-500">天</span>
                                  <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => crawl.onQuickLastDaysChange(3)}>
                                    3天
                                  </Button>
                                  <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => crawl.onQuickLastDaysChange(7)}>
                                    7天
                                  </Button>
                                  <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => crawl.onQuickLastDaysChange(30)}>
                                    30天
                                  </Button>
                                </div>
                                <div className="text-xs text-gray-600">选择月份</div>
                                <div className="max-w-[180px]">
                                  <MonthPickerButton
                                    value={crawl.crawlMonth}
                                    onChange={crawl.onCrawlMonthChange}
                                  />
                                </div>
                              </div>
                              <AlertDialogFooter>
                                <AlertDialogCancel
                                  onClick={(event) => {
                                    event.stopPropagation();
                                    crawl.onLatestDialogOpenChange(false);
                                  }}
                                >
                                  取消
                                </AlertDialogCancel>
                                <AlertDialogAction
                                  onClick={actions.onCrawlLatest}
                                  className="bg-blue-600 hover:bg-blue-700 focus:ring-blue-600"
                                >
                                  从最新开始
                                </AlertDialogAction>
                                <AlertDialogAction
                                  onClick={actions.onCrawlLastDays}
                                  className="bg-teal-600 hover:bg-teal-700 focus:ring-teal-600"
                                >
                                  最近N天开始
                                </AlertDialogAction>
                                <AlertDialogAction
                                  onClick={actions.onCrawlMonth}
                                  className="bg-teal-600 hover:bg-teal-700 focus:ring-teal-600"
                                >
                                  按月份开始
                                </AlertDialogAction>
                              </AlertDialogFooter>
                            </AlertDialogContent>
                          </AlertDialog>
                        )}
                      </div>
                    </div>

                    <div className="rounded-lg border border-gray-200 p-3">
                      <div className="mb-2 text-xs font-medium text-gray-600">话题采集来源</div>
                      <Select
                        value={crawl.topicSource}
                        onValueChange={(value) => crawl.onTopicSourceChange(value as 'legacy' | 'official')}
                      >
                        <SelectTrigger size="sm" className="h-8 w-full text-xs">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="official">官方流程</SelectItem>
                          <SelectItem value="legacy">旧 crawler</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

                    <div className="space-y-2 border-t border-gray-200 pt-3">
                      <button
                        type="button"
                        className="flex w-full items-center justify-between text-xs font-medium text-gray-500"
                        onClick={() => setAdvancedCrawlOpen((open) => !open)}
                        aria-expanded={advancedCrawlOpen}
                      >
                        <span>进阶采集</span>
                        {advancedCrawlOpen ? (
                          <ChevronDown className="h-3 w-3" />
                        ) : (
                          <ChevronRight className="h-3 w-3" />
                        )}
                      </button>
                      {advancedCrawlOpen && (
                        <>
                    <div className="border rounded-lg p-3 cursor-pointer transition-all border-blue-200 hover:bg-blue-50">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <FileText className="h-3 w-3 text-blue-600" />
                          <span className="text-xs font-medium text-blue-700">采集单个话题</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <Input
                          placeholder="输入话题ID"
                          value={crawl.singleTopicId}
                          onChange={(event) => crawl.onSingleTopicIdChange(event.target.value)}
                          className="h-7 text-xs"
                        />
                        <Button
                          size="sm"
                          className="h-7 text-xs"
                          onClick={actions.onFetchSingleTopic}
                          disabled={crawl.fetchingSingle}
                        >
                          {crawl.fetchingSingle ? '执行中...' : '采集'}
                        </Button>
                      </div>
                    </div>

                    <div
                      className={`border rounded-lg p-3 cursor-pointer transition-all ${
                        crawl.selectedOption === 'all'
                          ? 'bg-orange-50 border-orange-200'
                          : 'border-gray-200 hover:bg-gray-50'
                      }`}
                      onClick={() => crawl.onSelectedOptionChange('all')}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <BarChart3
                            className={`h-3 w-3 ${
                              crawl.selectedOption === 'all' ? 'text-orange-600' : 'text-gray-400'
                            }`}
                          />
                          <span
                            className={`text-xs font-medium ${
                              crawl.selectedOption === 'all' ? 'text-orange-700' : 'text-gray-600'
                            }`}
                          >
                            全量爬取
                          </span>
                        </div>
                        {!hasTopics && (
                          <Badge variant="secondary" className="text-xs px-1 py-0">
                            首次必选
                          </Badge>
                        )}
                      </div>
                      {crawl.selectedOption === 'all' && (
                        <AlertDialog>
                          <AlertDialogTrigger asChild>
                            <Button
                              size="sm"
                              className="w-full h-7 text-xs bg-orange-600 hover:bg-orange-700"
                              disabled={!!crawl.loading}
                            >
                              {crawl.loading === 'all' ? '执行中...' : '开始'}
                            </Button>
                          </AlertDialogTrigger>
                          <AlertDialogContent>
                            <AlertDialogHeader>
                              <AlertDialogTitle>确认全量爬取</AlertDialogTitle>
                              <AlertDialogDescription>
                                ⚠️ 全量爬取将持续爬取直到没有数据，可能需要很长时间。
                                <br />
                                <br />
                                确认开始全量爬取吗？
                              </AlertDialogDescription>
                            </AlertDialogHeader>
                            <AlertDialogFooter>
                              <AlertDialogCancel>取消</AlertDialogCancel>
                              <AlertDialogAction
                                onClick={actions.onCrawlAll}
                                className="bg-orange-600 hover:bg-orange-700 focus:ring-orange-600"
                              >
                                确认开始
                              </AlertDialogAction>
                            </AlertDialogFooter>
                          </AlertDialogContent>
                        </AlertDialog>
                      )}
                    </div>

                    <div
                      className={`border rounded-lg p-3 cursor-pointer transition-all ${
                        crawl.selectedOption === 'incremental'
                          ? 'bg-green-50 border-green-200'
                          : !hasTopics
                            ? 'border-gray-200 bg-gray-50 opacity-50 cursor-not-allowed'
                            : 'border-gray-200 hover:bg-gray-50'
                      }`}
                      onClick={handleSelectIncremental}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <TrendingUp
                            className={`h-3 w-3 ${
                              crawl.selectedOption === 'incremental' ? 'text-green-600' : 'text-gray-400'
                            }`}
                          />
                          <span
                            className={`text-xs font-medium ${
                              crawl.selectedOption === 'incremental' ? 'text-green-700' : 'text-gray-600'
                            }`}
                          >
                            增量爬取
                          </span>
                        </div>
                      </div>
                      {crawl.selectedOption === 'incremental' && (
                        <Button
                          size="sm"
                          className="w-full h-7 text-xs bg-green-600 hover:bg-green-700"
                          onClick={actions.onIncrementalCrawl}
                          disabled={!!crawl.loading}
                        >
                          {crawl.loading === 'incremental' ? '执行中...' : '开始'}
                        </Button>
                      )}
                    </div>
                        </>
                      )}
                    </div>

                    {hasTopics && (
                      <div className="space-y-2 border-t border-red-100 pt-3">
                        <div className="text-xs font-medium text-red-900 mb-2">数据管理</div>
                        <AlertDialog>
                          <AlertDialogTrigger asChild>
                            <Button size="sm" variant="destructive" className="w-full h-7 text-xs" disabled={!!crawl.loading || !!download.loading}>
                              删除所有话题数据
                            </Button>
                          </AlertDialogTrigger>
                          <AlertDialogContent>
                            <AlertDialogHeader>
                              <AlertDialogTitle className="text-red-600">确认删除话题数据</AlertDialogTitle>
                              <AlertDialogDescription className="text-red-700">
                                ⚠️ 警告：此操作将删除当前群组的所有话题数据！
                                包括话题、评论、用户信息等，此操作不可撤销。
                              </AlertDialogDescription>
                            </AlertDialogHeader>
                            <AlertDialogFooter>
                              <AlertDialogCancel>取消</AlertDialogCancel>
                              <AlertDialogAction
                                onClick={actions.onDeleteTopics}
                                className="bg-red-600 hover:bg-red-700 focus:ring-red-600"
                              >
                                确认删除
                              </AlertDialogAction>
                            </AlertDialogFooter>
                          </AlertDialogContent>
                        </AlertDialog>
                      </div>
                    )}
                  </div>

                  <div className="border rounded-lg p-3 cursor-pointer transition-all border-blue-200 hover:bg-blue-50">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <Settings className="h-3 w-3 text-blue-400" />
                        <span className="text-xs font-medium text-blue-600">爬取间隔设置</span>
                      </div>
                      <span className="text-xs text-gray-500">{crawl.pagesPerBatch}页/批次</span>
                    </div>
                    <Button
                      size="sm"
                      variant="outline"
                      className="w-full h-7 text-xs"
                      onClick={() => crawl.onSettingsOpenChange(true)}
                    >
                      配置间隔参数
                    </Button>
                    <div className="text-xs text-gray-500 mt-2">
                      调整页面爬取间隔和批次设置，避免触发反爬虫机制。
                    </div>
                  </div>
                </div>
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
