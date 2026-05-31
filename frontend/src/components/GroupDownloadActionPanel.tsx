'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
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
import { DatePickerButton } from '@/components/ui/date-picker-button';
import { Calendar, Edit, FileText, Settings, Trash2, TrendingUp } from 'lucide-react';

import type { GroupActionPanelProps, GroupDownloadOption } from '@/components/GroupActionPanel';

interface GroupDownloadActionPanelProps {
  actions: GroupActionPanelProps['actions'];
  download: GroupActionPanelProps['download'];
  hasLocalFiles: boolean;
  onSelectDownload: (option: GroupDownloadOption) => void;
  sourceFileCount: number | string;
}

function clampPositiveDays(value: string) {
  const days = Number.parseInt(value, 10);
  if (!Number.isFinite(days)) {
    return 1;
  }
  return Math.max(1, days);
}

export default function GroupDownloadActionPanel({
  actions,
  download,
  hasLocalFiles,
  onSelectDownload,
  sourceFileCount,
}: GroupDownloadActionPanelProps) {
  return (
    <div className="space-y-3">
      <div>
        <div className="flex items-center gap-2 text-sm font-medium text-gray-900">
          <FileText className="h-4 w-4" />
          下载文件
        </div>
        <div className="mt-1 text-xs text-gray-500">
          这里只启动长任务；单文件下载、重试和 AI 分析在中间工作台完成。
        </div>
      </div>
      <div className="space-y-2">
        <div
          className={`rounded-lg border p-3 text-xs ${
            !hasLocalFiles
              ? 'border-amber-200 bg-amber-50 text-amber-800'
              : 'border-blue-200 bg-blue-50 text-blue-800'
          }`}
        >
          <div className="flex items-center justify-between gap-2">
            <div className="font-medium">文件记录</div>
            <Badge variant="secondary" className="text-[10px]">
              {download.localFileStats.total} 条
            </Badge>
          </div>
          {!hasLocalFiles ? (
            <div className="mt-2">当前还没有文件记录。采集包含附件的话题后，文件会自动同步到这里。</div>
          ) : (
            <div className="mt-2 grid grid-cols-3 gap-2">
              <div className="rounded border border-blue-100 bg-white/70 p-2">
                <div className="text-[10px] text-blue-500">已下载</div>
                <div className="font-semibold text-blue-900">{download.localFileStats.downloaded}</div>
              </div>
              <div className="rounded border border-blue-100 bg-white/70 p-2">
                <div className="text-[10px] text-blue-500">未下载</div>
                <div className="font-semibold text-blue-900">{download.localFileStats.pending}</div>
              </div>
              <div className="rounded border border-blue-100 bg-white/70 p-2">
                <div className="text-[10px] text-blue-500">失败</div>
                <div className="font-semibold text-blue-900">{download.localFileStats.failed}</div>
              </div>
            </div>
          )}
        </div>

        <div className="pt-1 text-xs font-medium text-gray-500">任务启动器</div>

        <div
          className={`border rounded-lg p-3 cursor-pointer transition-all ${
            download.selectedOption === 'time'
              ? 'bg-purple-50 border-purple-200'
              : !hasLocalFiles
                ? 'border-gray-200 bg-gray-50 opacity-70 cursor-not-allowed'
                : 'border-gray-200 hover:bg-gray-50'
          }`}
          onClick={() => onSelectDownload('time')}
        >
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <Calendar
                className={`h-3 w-3 ${
                  download.selectedOption === 'time' ? 'text-purple-600' : 'text-gray-400'
                }`}
              />
              <span
                className={`text-xs font-medium ${
                  download.selectedOption === 'time' ? 'text-purple-700' : 'text-gray-600'
                }`}
              >
                按时间下载
              </span>
            </div>
            {!hasLocalFiles && (
              <Badge variant="secondary" className="text-[10px]">
                无记录
              </Badge>
            )}
          </div>
          {download.selectedOption === 'time' && (
            <AlertDialog open={download.dialogOpen} onOpenChange={download.onDialogOpenChange}>
              <Button
                size="sm"
                className="w-full h-7 text-xs bg-purple-600 hover:bg-purple-700"
                onClick={() => download.onDialogOpenChange(true)}
                disabled={!!download.loading || !hasLocalFiles}
              >
                {download.loading === 'download-time' ? '执行中...' : '开始'}
              </Button>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>按时间下载文件</AlertDialogTitle>
                  <AlertDialogDescription>
                    默认下载最近 N 天的文件；也可以指定开始和结束日期。
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <div className="space-y-3">
                  <div className="text-xs text-gray-600">快速选择：最近N天</div>
                  <div className="flex items-center gap-2">
                    <Input
                      type="number"
                      min={1}
                      value={download.quickLastDays}
                      onChange={(event) => download.onQuickLastDaysChange(clampPositiveDays(event.target.value))}
                      className="h-7 text-xs w-24"
                    />
                    <span className="text-xs text-gray-500">天</span>
                    <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => download.onQuickLastDaysChange(3)}>
                      3天
                    </Button>
                    <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => download.onQuickLastDaysChange(7)}>
                      7天
                    </Button>
                    <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => download.onQuickLastDaysChange(30)}>
                      30天
                    </Button>
                  </div>
                  <div className="text-[10px] text-gray-400">或 自定义日期范围</div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="flex flex-col gap-2">
                      <div className="text-[10px] text-gray-500">开始日期</div>
                      <DatePickerButton
                        value={download.rangeStartDate}
                        onChange={download.onRangeStartDateChange}
                      />
                    </div>
                    <div className="flex flex-col gap-2">
                      <div className="text-[10px] text-gray-500">结束日期</div>
                      <DatePickerButton
                        value={download.rangeEndDate}
                        onChange={download.onRangeEndDateChange}
                        align="end"
                      />
                    </div>
                  </div>
                </div>
                <AlertDialogFooter>
                  <AlertDialogCancel
                    onClick={(event) => {
                      event.stopPropagation();
                      download.onDialogOpenChange(false);
                    }}
                  >
                    取消
                  </AlertDialogCancel>
                  <AlertDialogAction
                    onClick={actions.onDownloadByTime}
                    className="bg-purple-600 hover:bg-purple-700 focus:ring-purple-600"
                  >
                    开始下载
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          )}
        </div>

        <div
          className={`border rounded-lg p-3 cursor-pointer transition-all ${
            download.selectedOption === 'count'
              ? 'bg-indigo-50 border-indigo-200'
              : !hasLocalFiles
                ? 'border-gray-200 bg-gray-50 opacity-70 cursor-not-allowed'
                : 'border-gray-200 hover:bg-gray-50'
          }`}
          onClick={() => onSelectDownload('count')}
        >
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <TrendingUp
                className={`h-3 w-3 ${
                  download.selectedOption === 'count' ? 'text-indigo-600' : 'text-gray-400'
                }`}
              />
              <span
                className={`text-xs font-medium ${
                  download.selectedOption === 'count' ? 'text-indigo-700' : 'text-gray-600'
                }`}
              >
                按热度下载
              </span>
            </div>
            {!hasLocalFiles && (
              <Badge variant="secondary" className="text-[10px]">
                无记录
              </Badge>
            )}
          </div>
          {download.selectedOption === 'count' && (
            <Button
              size="sm"
              className="w-full h-7 text-xs bg-indigo-600 hover:bg-indigo-700"
              onClick={actions.onDownloadByCount}
              disabled={!!download.loading || !hasLocalFiles}
            >
              {download.loading === 'download-count' ? '执行中...' : '开始'}
            </Button>
          )}
        </div>

        <div className="pt-1 text-xs font-medium text-gray-500">任务参数</div>

        <div className="border rounded-lg p-3 border-gray-200">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Settings className="h-3 w-3 text-gray-400" />
              <span className="text-xs font-medium text-gray-600">下载间隔设置</span>
            </div>
            <Button
              size="sm"
              variant="outline"
              className="h-6 px-2 text-xs"
              onClick={() => download.onSettingsOpenChange(true)}
            >
              <Edit className="h-3 w-3 mr-1" />
              修改
            </Button>
          </div>
          <div className="mt-2 text-xs text-gray-500 space-y-1">
            <div>
              下载间隔: {download.downloadIntervalMin}-{download.downloadIntervalMax}秒 |
              长休眠: {Math.floor(download.longSleepIntervalMin / 60)}-{Math.floor(download.longSleepIntervalMax / 60)}分钟 |
              批次: {download.filesPerBatch}个文件
            </div>
            <div className="text-gray-400">
              {download.useRandomInterval
                ? '随机间隔模式'
                : `固定间隔模式 (取中间值: ${Math.round((download.downloadIntervalMin + download.downloadIntervalMax) / 2)}秒)`}{' '}
              - 点击修改按钮可调整下载间隔和批次设置
            </div>
          </div>
        </div>

        <details className="rounded-lg border border-red-200 bg-red-50/50 p-3">
          <summary className="cursor-pointer text-xs font-medium text-red-600">
            危险操作
          </summary>
          <div className="mt-3 space-y-2">
            <div className="flex items-center justify-between text-xs text-red-700">
              <div className="flex items-center gap-2">
                <Trash2 className="h-3 w-3 text-red-400" />
                删除文件数据库
              </div>
              <span className="text-gray-500">
                {download.localFileCount}/{sourceFileCount}
              </span>
            </div>
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button size="sm" variant="destructive" className="w-full h-7 text-xs" disabled={!!download.loading}>
                  {download.loading === 'clear' ? '执行中...' : '删除数据库'}
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle className="text-red-600">确认删除文件数据库</AlertDialogTitle>
                  <AlertDialogDescription className="text-red-700">
                    此操作将删除当前群组的所有文件数据库，包括文件记录、下载状态等，此操作不可撤销。
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>取消</AlertDialogCancel>
                  <AlertDialogAction
                    onClick={actions.onClearFileDatabase}
                    className="bg-red-600 hover:bg-red-700 focus:ring-red-600"
                  >
                    确认删除
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        </details>
      </div>
    </div>
  );
}
