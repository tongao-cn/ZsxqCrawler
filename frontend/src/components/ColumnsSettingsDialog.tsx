'use client';

import { useState } from 'react';
import { Download, Settings } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ColumnsFetchSettings } from '@/lib/api';

interface ColumnsSettingsDialogProps {
  fetchingColumns: boolean;
  onSubmit: (settings: ColumnsFetchSettings) => Promise<void>;
}

export default function ColumnsSettingsDialog({ fetchingColumns, onSubmit }: ColumnsSettingsDialogProps) {
  const [open, setOpen] = useState(false);
  const [crawlIntervalMin, setCrawlIntervalMin] = useState(2);
  const [crawlIntervalMax, setCrawlIntervalMax] = useState(5);
  const [longSleepIntervalMin, setLongSleepIntervalMin] = useState(30);
  const [longSleepIntervalMax, setLongSleepIntervalMax] = useState(60);
  const [itemsPerBatch, setItemsPerBatch] = useState(10);
  const [downloadFiles, setDownloadFiles] = useState(true);
  const [downloadVideos, setDownloadVideos] = useState(true);
  const [cacheImages, setCacheImages] = useState(true);
  const [incrementalMode, setIncrementalMode] = useState(true);

  const handleSubmit = async () => {
    setOpen(false);
    await onSubmit({
      crawlIntervalMin,
      crawlIntervalMax,
      longSleepIntervalMin,
      longSleepIntervalMax,
      itemsPerBatch,
      downloadFiles,
      downloadVideos,
      cacheImages,
      incrementalMode,
    });
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button
          disabled={fetchingColumns}
          className="flex items-center gap-2 bg-amber-500 hover:bg-amber-600 text-white"
        >
          <Download className="h-4 w-4" />
          {fetchingColumns ? '采集中...' : '采集全部专栏'}
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Settings className="h-5 w-5" />
            专栏采集设置
          </DialogTitle>
          <DialogDescription>
            配置专栏采集的间隔参数，避免请求过于频繁
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          <div className="space-y-3">
            <Label className="text-sm font-medium">请求间隔 (秒)</Label>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label className="text-xs text-gray-500">最小</Label>
                <Input
                  type="number"
                  min={1}
                  max={60}
                  step={0.5}
                  value={crawlIntervalMin}
                  onChange={(e) => setCrawlIntervalMin(parseFloat(e.target.value) || 2)}
                />
              </div>
              <div>
                <Label className="text-xs text-gray-500">最大</Label>
                <Input
                  type="number"
                  min={1}
                  max={60}
                  step={0.5}
                  value={crawlIntervalMax}
                  onChange={(e) => setCrawlIntervalMax(parseFloat(e.target.value) || 5)}
                />
              </div>
            </div>
          </div>

          <div className="space-y-3">
            <Label className="text-sm font-medium">长休眠间隔 (秒)</Label>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label className="text-xs text-gray-500">最小</Label>
                <Input
                  type="number"
                  min={10}
                  max={600}
                  step={5}
                  value={longSleepIntervalMin}
                  onChange={(e) => setLongSleepIntervalMin(parseFloat(e.target.value) || 30)}
                />
              </div>
              <div>
                <Label className="text-xs text-gray-500">最大</Label>
                <Input
                  type="number"
                  min={10}
                  max={600}
                  step={5}
                  value={longSleepIntervalMax}
                  onChange={(e) => setLongSleepIntervalMax(parseFloat(e.target.value) || 60)}
                />
              </div>
            </div>
          </div>

          <div className="space-y-3">
            <Label className="text-sm font-medium">每批次请求数</Label>
            <Input
              type="number"
              min={3}
              max={50}
              value={itemsPerBatch}
              onChange={(e) => setItemsPerBatch(parseInt(e.target.value) || 10)}
            />
            <p className="text-xs text-gray-500">
              每完成指定数量的请求后，会进入长休眠
            </p>
          </div>

          <div className="space-y-3">
            <Label className="text-sm font-medium">附件选项</Label>
            <div className="flex items-center gap-6">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={downloadFiles}
                  onChange={(e) => setDownloadFiles(e.target.checked)}
                  className="w-4 h-4 rounded border-gray-300"
                />
                <span className="text-sm">下载文件</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={downloadVideos}
                  onChange={(e) => setDownloadVideos(e.target.checked)}
                  className="w-4 h-4 rounded border-gray-300"
                />
                <span className="text-sm">下载视频</span>
                <span className="text-xs text-gray-400">(需ffmpeg)</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={cacheImages}
                  onChange={(e) => setCacheImages(e.target.checked)}
                  className="w-4 h-4 rounded border-gray-300"
                />
                <span className="text-sm">缓存图片</span>
              </label>
            </div>
          </div>
        </div>

        <div className="p-4 bg-blue-50 rounded-lg border border-blue-200">
          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={incrementalMode}
              onChange={(e) => setIncrementalMode(e.target.checked)}
              className="w-5 h-5 rounded border-gray-300"
            />
            <div>
              <span className="text-sm font-medium text-blue-800">增量采集模式</span>
              <p className="text-xs text-blue-600 mt-0.5">
                开启后将跳过已采集的文章，只获取新内容（推荐）
              </p>
            </div>
          </label>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            取消
          </Button>
          <Button
            onClick={handleSubmit}
            className="bg-amber-500 hover:bg-amber-600 text-white"
          >
            <Download className="h-4 w-4 mr-2" />
            {incrementalMode ? '增量采集' : '全量采集'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
