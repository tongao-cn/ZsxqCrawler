'use client';

import React, { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

interface DownloadSettingsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  downloadInterval: number;
  longSleepInterval: number;
  filesPerBatch: number;
  downloadIntervalMin: number;
  downloadIntervalMax: number;
  longSleepIntervalMin: number;
  longSleepIntervalMax: number;
  useRandomInterval: boolean;
  onSettingsChange: (settings: {
    downloadInterval: number;
    longSleepInterval: number;
    filesPerBatch: number;
    downloadIntervalMin?: number;
    downloadIntervalMax?: number;
    longSleepIntervalMin?: number;
    longSleepIntervalMax?: number;
  }) => void;
}

export default function DownloadSettingsDialog({
  open,
  onOpenChange,
  downloadInterval,
  longSleepInterval,
  filesPerBatch,
  downloadIntervalMin,
  downloadIntervalMax,
  longSleepIntervalMin,
  longSleepIntervalMax,
  useRandomInterval,
  onSettingsChange,
}: DownloadSettingsDialogProps) {
  const [localFilesPerBatch, setLocalFilesPerBatch] = useState<number | ''>(filesPerBatch);

  const [localDownloadIntervalMin, setLocalDownloadIntervalMin] = useState<number | ''>(downloadIntervalMin);
  const [localDownloadIntervalMax, setLocalDownloadIntervalMax] = useState<number | ''>(downloadIntervalMax);
  const [localLongSleepIntervalMin, setLocalLongSleepIntervalMin] = useState<number | ''>(longSleepIntervalMin);
  const [localLongSleepIntervalMax, setLocalLongSleepIntervalMax] = useState<number | ''>(longSleepIntervalMax);
  const [localUseRandomInterval, setLocalUseRandomInterval] = useState(useRandomInterval);
  const [selectedPreset, setSelectedPreset] = useState<'fast' | 'standard' | 'safe' | null>('fast');

  // 当对话框打开时，同步当前设置值
  useEffect(() => {
    if (open) {
      setLocalFilesPerBatch(filesPerBatch);
      setLocalDownloadIntervalMin(downloadIntervalMin);
      setLocalDownloadIntervalMax(downloadIntervalMax);
      setLocalLongSleepIntervalMin(longSleepIntervalMin);
      setLocalLongSleepIntervalMax(longSleepIntervalMax);
      setLocalUseRandomInterval(useRandomInterval);
      setSelectedPreset(null);

      // 如果是第一次打开，默认设置为快速配置
      if (downloadInterval === 1.0 && longSleepInterval === 60.0 && filesPerBatch === 10) {
        setPreset('fast');
      }
    }
  }, [
    open,
    downloadInterval,
    longSleepInterval,
    filesPerBatch,
    downloadIntervalMin,
    downloadIntervalMax,
    longSleepIntervalMin,
    longSleepIntervalMax,
    useRandomInterval,
  ]);

  const handleSave = () => {
    // 确保所有值都有默认值
    const finalDownloadIntervalMin = Number(localDownloadIntervalMin || 15);
    const finalDownloadIntervalMax = Number(localDownloadIntervalMax || 30);
    const finalLongSleepIntervalMin = Number(localLongSleepIntervalMin || 30);
    const finalLongSleepIntervalMax = Number(localLongSleepIntervalMax || 60);
    const finalFilesPerBatch = Number(localFilesPerBatch || 10);

    onSettingsChange({
      downloadInterval: localUseRandomInterval
        ? (finalDownloadIntervalMin + finalDownloadIntervalMax) / 2
        : Math.round((finalDownloadIntervalMin + finalDownloadIntervalMax) / 2),
      longSleepInterval: localUseRandomInterval
        ? (finalLongSleepIntervalMin + finalLongSleepIntervalMax) / 2
        : Math.round((finalLongSleepIntervalMin + finalLongSleepIntervalMax) / 2),
      filesPerBatch: finalFilesPerBatch,
      downloadIntervalMin: localUseRandomInterval ? finalDownloadIntervalMin : undefined,
      downloadIntervalMax: localUseRandomInterval ? finalDownloadIntervalMax : undefined,
      longSleepIntervalMin: localUseRandomInterval ? finalLongSleepIntervalMin : undefined,
      longSleepIntervalMax: localUseRandomInterval ? finalLongSleepIntervalMax : undefined,
    });
    onOpenChange(false);
  };

  const handleCancel = () => {
    // 重置为原始值
    setLocalFilesPerBatch(filesPerBatch);
    setLocalDownloadIntervalMin(downloadIntervalMin);
    setLocalDownloadIntervalMax(downloadIntervalMax);
    setLocalLongSleepIntervalMin(longSleepIntervalMin);
    setLocalLongSleepIntervalMax(longSleepIntervalMax);
    setLocalUseRandomInterval(useRandomInterval);
    onOpenChange(false);
  };

  const setPreset = (preset: 'fast' | 'standard' | 'safe') => {
    setLocalUseRandomInterval(true);
    setSelectedPreset(preset);
    switch (preset) {
      case 'fast':
        setLocalDownloadIntervalMin(15);
        setLocalDownloadIntervalMax(30);
        setLocalLongSleepIntervalMin(30);
        setLocalLongSleepIntervalMax(60);
        setLocalFilesPerBatch(30);
        break;
      case 'standard':
        setLocalDownloadIntervalMin(30);
        setLocalDownloadIntervalMax(60);
        setLocalLongSleepIntervalMin(60);
        setLocalLongSleepIntervalMax(180);
        setLocalFilesPerBatch(15);
        break;
      case 'safe':
        setLocalDownloadIntervalMin(60);
        setLocalDownloadIntervalMax(180);
        setLocalLongSleepIntervalMin(180);
        setLocalLongSleepIntervalMax(300);
        setLocalFilesPerBatch(5);
        break;
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>下载间隔设置</DialogTitle>
          <DialogDescription>
            调整文件下载的间隔时间和批次设置，以避免触发反爬虫机制。
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* 间隔模式选择 */}
          <div className="space-y-2">
            <Label>间隔模式</Label>
            <div className="flex gap-2">
              <Button
                type="button"
                variant={localUseRandomInterval ? "default" : "outline"}
                size="sm"
                onClick={() => setLocalUseRandomInterval(true)}
                className="flex-1"
              >
                随机间隔 (推荐)
              </Button>
              <Button
                type="button"
                variant={!localUseRandomInterval ? "default" : "outline"}
                size="sm"
                onClick={() => setLocalUseRandomInterval(false)}
                className="flex-1"
              >
                固定间隔
              </Button>
            </div>
          </div>

          {/* 下载间隔范围 */}
          <div className="space-y-2">
            <Label>下载间隔范围 (秒)</Label>
            <div className="flex gap-2 items-center">
              <Input
                type="number"
                min="1"
                max="300"
                value={localDownloadIntervalMin}
                onChange={(e) => {
                  const value = e.target.value;
                  if (value === '') {
                    setLocalDownloadIntervalMin('');
                  } else {
                    const num = parseInt(value);
                    if (!isNaN(num)) {
                      setLocalDownloadIntervalMin(num);
                    }
                  }
                }}
                onBlur={(e) => {
                  if (e.target.value === '') {
                    setLocalDownloadIntervalMin(15);
                  }
                }}
                placeholder="15"
                className="flex-1"
              />
              <span className="text-sm text-gray-500">-</span>
              <Input
                type="number"
                min="1"
                max="300"
                value={localDownloadIntervalMax}
                onChange={(e) => {
                  const value = e.target.value;
                  if (value === '') {
                    setLocalDownloadIntervalMax('');
                  } else {
                    const num = parseInt(value);
                    if (!isNaN(num)) {
                      setLocalDownloadIntervalMax(num);
                    }
                  }
                }}
                onBlur={(e) => {
                  if (e.target.value === '') {
                    setLocalDownloadIntervalMax(30);
                  }
                }}
                placeholder="30"
                className="flex-1"
              />
            </div>
            <p className="text-xs text-gray-500">
              {localUseRandomInterval
                ? '每次下载文件后的随机等待时间范围'
                : `每次下载文件后的固定等待时间 (取中间值: ${Math.round((Number(localDownloadIntervalMin || 15) + Number(localDownloadIntervalMax || 30)) / 2)}秒)`
              }
            </p>
          </div>

          {/* 长休眠间隔范围 */}
          <div className="space-y-2">
            <Label>长休眠间隔范围 (秒)</Label>
            <div className="flex gap-2 items-center">
              <Input
                type="number"
                min="10"
                max="3600"
                value={localLongSleepIntervalMin}
                onChange={(e) => {
                  const value = e.target.value;
                  if (value === '') {
                    setLocalLongSleepIntervalMin('');
                  } else {
                    const num = parseInt(value);
                    if (!isNaN(num)) {
                      setLocalLongSleepIntervalMin(num);
                    }
                  }
                }}
                onBlur={(e) => {
                  if (e.target.value === '') {
                    setLocalLongSleepIntervalMin(30);
                  }
                }}
                placeholder="30"
                className="flex-1"
              />
              <span className="text-sm text-gray-500">-</span>
              <Input
                type="number"
                min="10"
                max="3600"
                value={localLongSleepIntervalMax}
                onChange={(e) => {
                  const value = e.target.value;
                  if (value === '') {
                    setLocalLongSleepIntervalMax('');
                  } else {
                    const num = parseInt(value);
                    if (!isNaN(num)) {
                      setLocalLongSleepIntervalMax(num);
                    }
                  }
                }}
                onBlur={(e) => {
                  if (e.target.value === '') {
                    setLocalLongSleepIntervalMax(60);
                  }
                }}
                placeholder="60"
                className="flex-1"
              />
            </div>
            <p className="text-xs text-gray-500">
              {localUseRandomInterval
                ? '达到批次大小后的随机长时间休眠范围'
                : `达到批次大小后的固定长时间休眠 (取中间值: ${Math.round((Number(localLongSleepIntervalMin || 30) + Number(localLongSleepIntervalMax || 60)) / 2)}秒)`
              }
            </p>
          </div>

          {/* 批次大小 */}
          <div className="space-y-2">
            <Label htmlFor="filesPerBatch">批次大小 (个文件)</Label>
            <Input
              id="filesPerBatch"
              type="number"
              min="1"
              max="100"
              step="1"
              value={localFilesPerBatch}
              onChange={(e) => {
                const value = e.target.value;
                if (value === '') {
                  setLocalFilesPerBatch('');
                } else {
                  const num = parseInt(value);
                  if (!isNaN(num)) {
                    setLocalFilesPerBatch(num);
                  }
                }
              }}
              onBlur={(e) => {
                if (e.target.value === '') {
                  setLocalFilesPerBatch(10);
                }
              }}
              placeholder="10"
            />
            <p className="text-xs text-gray-500">下载多少个文件后触发长休眠</p>
          </div>

          {/* 快速配置 */}
          <div className="space-y-2">
            <Label>快速配置</Label>
            <div className="flex gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setPreset('fast')}
                className={`flex-1 ${
                  selectedPreset === 'fast'
                    ? 'bg-green-100 text-green-800 border-green-300 hover:bg-green-200'
                    : 'bg-gray-50 text-gray-500 border-gray-200 hover:bg-gray-100'
                }`}
              >
                快速
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setPreset('standard')}
                className={`flex-1 ${
                  selectedPreset === 'standard'
                    ? 'bg-blue-100 text-blue-800 border-blue-300 hover:bg-blue-200'
                    : 'bg-gray-50 text-gray-500 border-gray-200 hover:bg-gray-100'
                }`}
              >
                标准
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setPreset('safe')}
                className={`flex-1 ${
                  selectedPreset === 'safe'
                    ? 'bg-orange-100 text-orange-800 border-orange-300 hover:bg-orange-200'
                    : 'bg-gray-50 text-gray-500 border-gray-200 hover:bg-gray-100'
                }`}
              >
                安全
              </Button>
            </div>
            <div className="text-xs text-gray-500 space-y-1">
              <div>• 快速: 15-30秒间隔, 30秒-1分钟长休眠, 30个文件/批次</div>
              <div>• 标准: 30秒-1分钟间隔, 1-3分钟长休眠, 15个文件/批次</div>
              <div>• 安全: 1-3分钟间隔, 3-5分钟长休眠, 5个文件/批次</div>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={handleCancel}>
            取消
          </Button>
          <Button type="button" onClick={handleSave}>
            保存设置
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
