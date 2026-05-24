'use client';

import React, { useEffect, useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { MonthPickerButton } from '@/components/ui/date-picker-button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

interface CrawlLatestDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (params: {
    mode: 'latest' | 'range';
    startTime?: string;
    endTime?: string;
    lastDays?: number;
    perPage?: number;
    topicSource?: 'legacy' | 'official';
  }) => void;
  submitting?: boolean;
  defaultLastDays?: number;
  defaultPerPage?: number;
  topicSource?: 'legacy' | 'official';
}

function getCurrentMonth() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
}

function buildMonthRange(month: string) {
  const matched = /^(\d{4})-(\d{2})$/.exec(month);
  if (!matched) return null;

  const year = Number(matched[1]);
  const monthNumber = Number(matched[2]);
  if (monthNumber < 1 || monthNumber > 12) return null;

  const lastDay = new Date(year, monthNumber, 0).getDate();
  return {
    startTime: `${month}-01`,
    endTime: `${month}-${String(lastDay).padStart(2, '0')}`,
  };
}

export default function CrawlLatestDialog({
  open,
  onOpenChange,
  onConfirm,
  submitting = false,
  defaultLastDays = 7,
  defaultPerPage = 20,
  topicSource: controlledTopicSource,
}: CrawlLatestDialogProps) {
  const [mode, setMode] = useState<'latest' | 'range'>('latest');
  const [lastDays, setLastDays] = useState<number | ''>(defaultLastDays);
  const [month, setMonth] = useState(getCurrentMonth);
  const [perPage, setPerPage] = useState<number | ''>(defaultPerPage);
  const [topicSource, setTopicSource] = useState<'legacy' | 'official'>('official');

  useEffect(() => {
    if (open) {
      setMode('latest');
      setLastDays(defaultLastDays);
      setMonth(getCurrentMonth());
      setPerPage(defaultPerPage);
      setTopicSource(controlledTopicSource || 'official');
    }
  }, [open, defaultLastDays, defaultPerPage, controlledTopicSource]);

  const buildLastDaysPayload = () => {
    const payload: {
      mode: 'latest' | 'range';
      lastDays?: number;
      perPage?: number;
      topicSource?: 'legacy' | 'official';
    } = { mode: 'range' };

    if (lastDays !== '' && !Number.isNaN(Number(lastDays))) {
      payload.lastDays = Math.max(1, Number(lastDays));
    }
    if (perPage !== '' && !Number.isNaN(Number(perPage))) {
      payload.perPage = Number(perPage);
    }
    payload.topicSource = topicSource;

    return payload;
  };

  const buildMonthPayload = () => {
    const range = buildMonthRange(month);
    const payload: {
      mode: 'latest' | 'range';
      startTime?: string;
      endTime?: string;
      perPage?: number;
      topicSource?: 'legacy' | 'official';
    } = { mode: 'range' };

    if (range) {
      payload.startTime = range.startTime;
      payload.endTime = range.endTime;
    }
    if (perPage !== '' && !Number.isNaN(Number(perPage))) {
      payload.perPage = Number(perPage);
    }
    payload.topicSource = topicSource;

    return payload;
  };

  const handleLatest = () => onConfirm({ mode: 'latest' });
  const handleLastDays = () => onConfirm(buildLastDaysPayload());
  const handleMonth = () => {
    if (!buildMonthRange(month)) {
      return;
    }
    onConfirm(buildMonthPayload());
  };

  return (
    <Dialog open={open} onOpenChange={(v) => !submitting && onOpenChange(v)}>
      <DialogContent className="sm:max-w-[560px]">
        <DialogHeader>
          <DialogTitle>获取最新话题</DialogTitle>
          <DialogDescription>
            默认从最新开始抓取；也可以按最近天数或月份采集。
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-2">
            <Label>采集方式</Label>
            <div className="flex gap-2">
              <Button
                type="button"
                variant={mode === 'latest' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setMode('latest')}
                className="flex-1"
              >
                从最新开始（默认）
              </Button>
              <Button
                type="button"
                variant={mode === 'range' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setMode('range')}
                className="flex-1"
              >
                按范围
              </Button>
            </div>
          </div>

          {mode === 'range' ? (
            <div className="space-y-4">
              <div className="space-y-2">
                <Label>最近天数</Label>
                <Input
                  type="number"
                  min="1"
                  max="3650"
                  placeholder={`${defaultLastDays}`}
                  value={lastDays}
                  onChange={(e) => {
                    const v = e.target.value;
                    if (v === '') setLastDays('');
                    else {
                      const n = parseInt(v);
                      if (!Number.isNaN(n)) setLastDays(n);
                    }
                  }}
                />
              </div>

              <div className="space-y-2">
                <Label>月份</Label>
                <MonthPickerButton
                  value={month}
                  onChange={setMonth}
                />
              </div>

              <div className="space-y-2">
                <Label>每页数量</Label>
                <Input
                  type="number"
                  min="1"
                  max="100"
                  value={perPage}
                  onChange={(e) => {
                    const v = e.target.value;
                    if (v === '') setPerPage('');
                    else {
                      const n = parseInt(v);
                      if (!Number.isNaN(n)) setPerPage(n);
                    }
                  }}
                  onBlur={(e) => {
                    if (e.target.value === '' || parseInt(e.target.value) < 1) {
                      setPerPage(defaultPerPage);
                    }
                  }}
                />
                <p className="text-xs text-muted-foreground">
                  用于月份采集的每页数量，默认 {defaultPerPage}。
                </p>
              </div>

              <div className="space-y-2">
                <Label>范围采集来源</Label>
                <Select value={topicSource} onValueChange={(value) => setTopicSource(value as 'legacy' | 'official')}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="official">官方流程</SelectItem>
                    <SelectItem value="legacy">旧 crawler</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          ) : (
            <div className="text-xs text-muted-foreground space-y-1">
              <p>• 直接点击“确认开始”将从最新话题向后增量抓取。</p>
              <p>• 如需限定范围，请切换到“按范围”。</p>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={submitting}
          >
            取消
          </Button>
          <Button type="button" variant="default" onClick={handleLatest} disabled={submitting}>
            {submitting ? '创建任务中...' : '从最新开始'}
          </Button>
          <Button type="button" variant="secondary" onClick={handleLastDays} disabled={submitting || lastDays === ''}>
            最近N天开始
          </Button>
          <Button type="button" variant="secondary" onClick={handleMonth} disabled={submitting || !buildMonthRange(month)}>
            按月份开始
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
