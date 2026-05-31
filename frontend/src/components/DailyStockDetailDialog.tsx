'use client';

import type { DailyStockConcept } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';

export interface StockTrendDay {
  date: string;
  concepts: string[];
  topicCount: number;
  present: boolean;
}

interface DailyStockDetailDialogProps {
  loadingStockTrend: boolean;
  onOpenChange: (open: boolean) => void;
  onOpenTopicDetail: (topicId: string | number) => void;
  open: boolean;
  selectedStock: DailyStockConcept | null;
  stockTrend: StockTrendDay[];
}

function TopicButtons({
  onOpenTopicDetail,
  topicIds,
}: {
  onOpenTopicDetail: (topicId: string | number) => void;
  topicIds: Array<string | number>;
}) {
  return (
    <div className="flex flex-wrap gap-1">
      {topicIds.length > 0 ? (
        topicIds.map((topicId) => (
          <Button
            key={String(topicId)}
            variant="link"
            size="sm"
            className="h-auto px-0 py-0 text-xs"
            onClick={() => onOpenTopicDetail(topicId)}
          >
            {String(topicId)}
          </Button>
        ))
      ) : (
        <span className="text-muted-foreground">-</span>
      )}
    </div>
  );
}

export default function DailyStockDetailDialog({
  loadingStockTrend,
  onOpenChange,
  onOpenTopicDetail,
  open,
  selectedStock,
  stockTrend,
}: DailyStockDetailDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-auto sm:max-w-4xl">
        <DialogHeader>
          <DialogTitle>{selectedStock?.stock_name || '股票详情'}</DialogTitle>
          <DialogDescription>当天概念、来源话题和最近 7 天已提取结果</DialogDescription>
        </DialogHeader>
        {selectedStock && (
          <div className="flex flex-col gap-4">
            <div className="grid gap-3 md:grid-cols-3">
              <div className="rounded-md border border-gray-200 p-3">
                <div className="text-sm text-muted-foreground">代码</div>
                <div className="mt-1 font-medium">
                  {selectedStock.stock_code ? `${selectedStock.stock_code}${selectedStock.market ? `.${selectedStock.market}` : ''}` : '未匹配'}
                </div>
              </div>
              <div className="rounded-md border border-gray-200 p-3">
                <div className="text-sm text-muted-foreground">置信度</div>
                <div className="mt-1 font-medium">{Math.round((selectedStock.confidence || 0) * 100)}%</div>
              </div>
              <div className="rounded-md border border-gray-200 p-3">
                <div className="text-sm text-muted-foreground">来源话题</div>
                <div className="mt-1">
                  <TopicButtons
                    onOpenTopicDetail={onOpenTopicDetail}
                    topicIds={selectedStock.topic_ids}
                  />
                </div>
              </div>
            </div>
            <div>
              <div className="mb-2 text-sm font-medium">当天概念</div>
              <div className="flex flex-wrap gap-1">
                {selectedStock.concepts.map((concept) => (
                  <Badge key={concept} variant="secondary">
                    {concept}
                  </Badge>
                ))}
              </div>
            </div>
            <div>
              <div className="mb-2 text-sm font-medium">提取理由</div>
              <div className="rounded-md bg-gray-50 p-3 text-sm leading-6 text-muted-foreground">
                {selectedStock.reason || '暂无'}
              </div>
            </div>
            <div>
              <div className="mb-2 text-sm font-medium">最近 7 天趋势</div>
              {loadingStockTrend ? (
                <div className="text-sm text-muted-foreground">加载中...</div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>日期</TableHead>
                      <TableHead>是否出现</TableHead>
                      <TableHead>来源话题数</TableHead>
                      <TableHead>概念</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {stockTrend.map((item) => (
                      <TableRow key={item.date}>
                        <TableCell>{item.date}</TableCell>
                        <TableCell>{item.present ? '是' : '否'}</TableCell>
                        <TableCell>{item.topicCount}</TableCell>
                        <TableCell className="whitespace-normal">
                          <div className="flex flex-wrap gap-1">
                            {item.concepts.length > 0 ? (
                              item.concepts.map((concept) => (
                                <Badge key={concept} variant="outline">
                                  {concept}
                                </Badge>
                              ))
                            ) : (
                              <span className="text-muted-foreground">-</span>
                            )}
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
