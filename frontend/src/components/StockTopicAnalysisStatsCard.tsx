'use client';

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

interface StockTopicAnalysisStatsCardProps {
  active: boolean;
  analyzedCount: number;
  newTopicCount: number;
  parsedStockCount: number;
  resultCount: number;
  selectedCount: number;
  totalTopics: number;
}

export default function StockTopicAnalysisStatsCard({
  active,
  analyzedCount,
  newTopicCount,
  parsedStockCount,
  resultCount,
  selectedCount,
  totalTopics,
}: StockTopicAnalysisStatsCardProps) {
  return (
    <Card className="h-fit">
      <CardHeader>
        <CardTitle>统计</CardTitle>
        <CardDescription>当前输入与结果概览</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <div className="flex items-center justify-between">
          <span className="text-muted-foreground">输入股票</span>
          <span className="font-medium">{parsedStockCount}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-muted-foreground">结果行数</span>
          <span className="font-medium">{resultCount}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-muted-foreground">已勾选</span>
          <span className="font-medium">{selectedCount}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-muted-foreground">命中话题</span>
          <span className="font-medium">{totalTopics}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-muted-foreground">已保存总结</span>
          <span className="font-medium">{analyzedCount}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-muted-foreground">待处理话题</span>
          <span className="font-medium">{newTopicCount}</span>
        </div>
        {active && (
          <div className="rounded-md border border-blue-100 bg-blue-50 p-3 text-xs text-blue-700">
            批量分析任务运行中，完成后会自动刷新表格。
          </div>
        )}
      </CardContent>
    </Card>
  );
}
