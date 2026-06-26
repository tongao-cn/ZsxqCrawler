'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Radar, RefreshCw, Search, Sparkles } from 'lucide-react';
import { toast } from 'sonner';

import { ApiClientError, apiClient } from '@/lib/api';
import type { ResearchRadarLogicItem, ResearchRadarRun } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { DatePickerButton } from '@/components/ui/date-picker-button';
import { Label } from '@/components/ui/label';
import { formatDateTime, getTodayText } from '@/components/DailyTopicAnalysisPanelUtils';
import { useTaskLauncher } from '@/hooks/useTaskLauncher';

interface ResearchRadarPanelProps {
  groupId: number;
  onTaskCreated?: (taskId: string) => void;
}

function getTierLabel(tier: string) {
  if (tier === 'strong') {
    return '强逻辑';
  }
  if (tier === 'medium') {
    return '中等逻辑';
  }
  return '弱线索';
}

function getTierBadgeClassName(tier: string) {
  if (tier === 'strong') {
    return 'bg-emerald-100 text-emerald-800';
  }
  if (tier === 'medium') {
    return 'bg-blue-100 text-blue-800';
  }
  return 'bg-amber-100 text-amber-800';
}

function formatConfidence(value?: number) {
  if (value === undefined || value === null || Number.isNaN(value)) {
    return '-';
  }
  const percent = value <= 1 ? value * 100 : value;
  return `${Math.round(percent)}%`;
}

function collectDirections(radar: ResearchRadarRun | null) {
  if (!radar) {
    return [];
  }
  return Array.from(
    new Set(radar.logic_items.map((item) => item.direction).filter(Boolean))
  );
}

function collectStocks(radar: ResearchRadarRun | null) {
  if (!radar) {
    return [];
  }
  const stocks = new Map<string, string>();
  radar.logic_items.forEach((item) => {
    item.stocks.forEach((stock) => {
      const label = stock.code ? `${stock.name} ${stock.code}` : stock.name;
      stocks.set(label, label);
    });
  });
  return Array.from(stocks.values());
}

function LogicItemCard({ item }: { item: ResearchRadarLogicItem }) {
  return (
    <Card className="border border-gray-200 shadow-none">
      <CardHeader>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <CardTitle className="flex min-w-0 items-center gap-2 text-base leading-6">
              <span className="text-sm text-muted-foreground">#{item.rank}</span>
              <span className="min-w-0 break-words">{item.title}</span>
            </CardTitle>
            <CardDescription className="mt-1 break-words">
              {item.direction || '未标注方向'}
            </CardDescription>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge className={getTierBadgeClassName(item.tier)}>{getTierLabel(item.tier)}</Badge>
            <Badge variant="outline">置信度 {formatConfidence(item.confidence)}</Badge>
            <Badge variant="secondary">证据 {item.evidence_count}</Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <p className="text-sm leading-6 text-gray-700">{item.summary || '暂无摘要'}</p>

        {item.concepts.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {item.concepts.map((concept) => (
              <Badge key={concept} variant="secondary">
                {concept}
              </Badge>
            ))}
          </div>
        )}

        {item.catalysts.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {item.catalysts.map((catalyst) => (
              <Badge key={catalyst} className="bg-purple-100 text-purple-800">
                {catalyst}
              </Badge>
            ))}
          </div>
        )}

        {item.stocks.length > 0 && (
          <div className="rounded-md border border-gray-200 p-3">
            <div className="mb-2 text-xs font-medium text-muted-foreground">相关股票</div>
            <div className="flex flex-wrap gap-2">
              {item.stocks.map((stock) => (
                <Badge key={`${stock.name}-${stock.code || stock.market || 'stock'}`} variant="outline">
                  {stock.name}
                  {stock.code ? ` ${stock.code}` : ''}
                  {stock.confidence !== undefined ? ` ${formatConfidence(stock.confidence)}` : ''}
                </Badge>
              ))}
            </div>
          </div>
        )}

        {item.evidence.length > 0 && (
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-2 text-sm font-medium">
              <Search className="h-4 w-4" />
              证据
            </div>
            <div className="grid gap-2">
              {item.evidence.map((evidence, index) => (
                <div
                  key={evidence.id ?? `${evidence.source_type}-${evidence.source_id}-${index}`}
                  className="rounded-md border border-gray-200 bg-gray-50 p-3"
                >
                  <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    <Badge variant="outline">{evidence.source_type}</Badge>
                    <span>话题 {evidence.topic_id}</span>
                    <span>{formatDateTime(evidence.source_time)}</span>
                  </div>
                  <p className="break-words text-sm leading-6 text-gray-700">{evidence.excerpt}</p>
                  {evidence.support_reason && (
                    <p className="mt-2 break-words text-xs leading-5 text-muted-foreground">
                      {evidence.support_reason}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {item.risks.length > 0 && (
          <div className="rounded-md border border-gray-200 bg-gray-50 p-3 text-xs leading-5 text-muted-foreground">
            风险：{item.risks.join('；')}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function ResearchRadarPanel({
  groupId,
  onTaskCreated,
}: ResearchRadarPanelProps) {
  const [reportDate, setReportDate] = useState(getTodayText);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [radar, setRadar] = useState<ResearchRadarRun | null>(null);
  const latestLoadIdRef = useRef(0);
  const { handleTaskCreateError, notifyTaskLaunch } = useTaskLauncher({
    onTaskCreated,
  });

  const loadRadar = useCallback(async (signal?: AbortSignal) => {
    const loadId = latestLoadIdRef.current + 1;
    latestLoadIdRef.current = loadId;
    setLoading(true);
    setLoadError(null);
    try {
      const response = await apiClient.getResearchRadar(groupId, reportDate, { signal });
      if (signal?.aborted || latestLoadIdRef.current !== loadId) {
        return;
      }
      setRadar(response);
    } catch (error) {
      if (signal?.aborted || latestLoadIdRef.current !== loadId) {
        return;
      }
      setRadar(null);
      if (error instanceof ApiClientError && error.status === 404) {
        return;
      }
      const message = error instanceof Error ? error.message : '未知错误';
      const nextLoadError = `加载研究雷达失败: ${message}`;
      setLoadError(nextLoadError);
      toast.error(nextLoadError);
    } finally {
      if (!signal?.aborted && latestLoadIdRef.current === loadId) {
        setLoading(false);
      }
    }
  }, [groupId, reportDate]);

  useEffect(() => {
    const controller = new AbortController();
    void loadRadar(controller.signal);
    return () => controller.abort();
  }, [loadRadar]);

  const handleGenerate = async () => {
    try {
      setGenerating(true);
      const response = await apiClient.createResearchRadar(groupId, {
        date: reportDate,
        commentsPerTopic: 8,
      });
      notifyTaskLaunch(response, (taskId) => `研究雷达任务已创建: ${taskId}`);
    } catch (error) {
      handleTaskCreateError(error, '创建研究雷达任务失败');
    } finally {
      setGenerating(false);
    }
  };

  const visibleLogicItems = useMemo(
    () => radar?.logic_items.filter((item) => item.tier !== 'weak') ?? [],
    [radar]
  );
  const weakLogicItems = useMemo(
    () => radar?.logic_items.filter((item) => item.tier === 'weak') ?? [],
    [radar]
  );
  const directions = useMemo(() => collectDirections(radar), [radar]);
  const stocks = useMemo(() => collectStocks(radar), [radar]);

  return (
    <div className="grid gap-4 p-1 xl:grid-cols-[minmax(0,1fr)_320px] xl:items-start">
      <div className="flex min-w-0 flex-col gap-4">
        <Card className="border border-gray-200 shadow-none">
          <CardHeader>
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <CardTitle className="flex items-center gap-2">
                  <Radar className="h-5 w-5" />
                  研究雷达
                </CardTitle>
                <CardDescription>
                  {radar ? `更新时间：${formatDateTime(radar.updated_at)}` : '暂无已生成研究雷达'}
                </CardDescription>
              </div>
              <Badge variant={radar?.status === 'completed' ? 'default' : 'secondary'}>
                {radar?.status || '暂无'}
              </Badge>
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid gap-3 md:grid-cols-4">
              <div className="rounded-md border border-gray-200 p-3">
                <div className="text-xs text-muted-foreground">逻辑</div>
                <div className="mt-1 font-semibold">{radar?.summary.logic_count ?? radar?.logic_items.length ?? '-'}</div>
              </div>
              <div className="rounded-md border border-gray-200 p-3">
                <div className="text-xs text-muted-foreground">方向</div>
                <div className="mt-1 font-semibold">{radar?.summary.direction_count ?? directions.length}</div>
              </div>
              <div className="rounded-md border border-gray-200 p-3">
                <div className="text-xs text-muted-foreground">股票</div>
                <div className="mt-1 font-semibold">{radar?.summary.stock_count ?? stocks.length}</div>
              </div>
              <div className="rounded-md border border-gray-200 p-3">
                <div className="text-xs text-muted-foreground">日期</div>
                <div className="mt-1 font-semibold">{radar?.report_date || reportDate}</div>
              </div>
            </div>
          </CardContent>
        </Card>

        {loading ? (
          <div className="flex h-40 items-center justify-center rounded-md border border-dashed border-gray-300 text-sm text-muted-foreground">
            正在加载研究雷达...
          </div>
        ) : loadError ? (
          <div className="flex h-56 flex-col items-center justify-center gap-3 rounded-md border border-red-200 bg-red-50 px-4 text-center text-sm text-red-700">
            <div className="break-words">{loadError}</div>
            <Button variant="outline" onClick={() => void loadRadar()} disabled={loading}>
              <RefreshCw className="h-4 w-4" />
              重试
            </Button>
          </div>
        ) : radar ? (
          <>
            <div className="flex flex-col gap-3">
              {visibleLogicItems.map((item) => (
                <LogicItemCard key={item.id ?? `${item.rank}-${item.title}`} item={item} />
              ))}
            </div>

            {weakLogicItems.length > 0 && (
              <div className="flex flex-col gap-3">
                <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
                  <Sparkles className="h-4 w-4" />
                  弱线索
                </div>
                {weakLogicItems.map((item) => (
                  <LogicItemCard key={item.id ?? `${item.rank}-${item.title}`} item={item} />
                ))}
              </div>
            )}
          </>
        ) : (
          <div className="flex h-56 items-center justify-center rounded-md border border-dashed border-gray-300 px-4 text-center text-sm text-muted-foreground">
            还没有这一天的研究雷达，点击右侧按钮创建任务
          </div>
        )}
      </div>

      <aside className="xl:sticky xl:top-4">
        <Card className="border border-gray-200 shadow-none">
          <CardHeader>
            <CardTitle className="text-base">雷达操作</CardTitle>
            <CardDescription>选择日期，刷新或生成研究雷达</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="research-radar-date">报告日期</Label>
              <DatePickerButton
                value={reportDate}
                onChange={(value) => setReportDate(value || getTodayText())}
              />
            </div>

            <div className="grid grid-cols-2 gap-2">
              <Button variant="outline" onClick={() => void loadRadar()} disabled={loading}>
                <RefreshCw className={loading ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} />
                刷新
              </Button>
              <Button onClick={handleGenerate} disabled={generating}>
                {generating ? (
                  <RefreshCw className="h-4 w-4 animate-spin" />
                ) : (
                  <Sparkles className="h-4 w-4" />
                )}
                生成
              </Button>
            </div>

            <div className="grid grid-cols-2 gap-2 text-sm">
              <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
                <div className="text-xs text-muted-foreground">强逻辑</div>
                <div className="mt-1 font-semibold">{radar?.summary.strong_count ?? '-'}</div>
              </div>
              <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
                <div className="text-xs text-muted-foreground">中等逻辑</div>
                <div className="mt-1 font-semibold">{radar?.summary.medium_count ?? '-'}</div>
              </div>
              <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
                <div className="text-xs text-muted-foreground">弱线索</div>
                <div className="mt-1 font-semibold">{radar?.summary.weak_count ?? '-'}</div>
              </div>
              <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
                <div className="text-xs text-muted-foreground">窗口</div>
                <div className="mt-1 font-semibold">{radar?.window_days ? `${radar.window_days} 天` : '-'}</div>
              </div>
            </div>

            {directions.length > 0 && (
              <div className="flex flex-col gap-2 border-t border-gray-200 pt-4">
                <div className="text-xs font-medium text-muted-foreground">方向</div>
                <div className="flex flex-wrap gap-2">
                  {directions.map((direction) => (
                    <Badge key={direction} variant="secondary">
                      {direction}
                    </Badge>
                  ))}
                </div>
              </div>
            )}

            {stocks.length > 0 && (
              <div className="flex flex-col gap-2 border-t border-gray-200 pt-4">
                <div className="text-xs font-medium text-muted-foreground">股票</div>
                <div className="flex flex-wrap gap-2">
                  {stocks.slice(0, 30).map((stock) => (
                    <Badge key={stock} variant="outline">
                      {stock}
                    </Badge>
                  ))}
                </div>
              </div>
            )}

            {radar && (
              <div className="rounded-md bg-gray-50 p-3 text-xs leading-5 text-muted-foreground">
                模型：{radar.model || '暂无'}
                <br />
                更新时间：{formatDateTime(radar.updated_at)}
              </div>
            )}
          </CardContent>
        </Card>
      </aside>
    </div>
  );
}
