'use client';

import { ArrowDown, ArrowUp, Minus } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import type { AShareAnalysisRankingItem } from '@/lib/api';

interface AShareRankingRowsProps {
  rows: AShareAnalysisRankingItem[];
  windowDays: number;
}

function RankTrendBadge({ item }: { item: AShareAnalysisRankingItem }) {
  if (item.trend === 'new') {
    return <Badge className="bg-blue-100 text-blue-800">新进</Badge>;
  }
  if (item.trend === 'up') {
    return (
      <Badge className="gap-1 bg-red-100 text-red-800">
        <ArrowUp className="h-3 w-3" />
        {Math.abs(item.rank_change ?? 0)}
      </Badge>
    );
  }
  if (item.trend === 'down') {
    return (
      <Badge className="gap-1 bg-green-100 text-green-800">
        <ArrowDown className="h-3 w-3" />
        {Math.abs(item.rank_change ?? 0)}
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className="gap-1 bg-white text-gray-600">
      <Minus className="h-3 w-3" />
      持平
    </Badge>
  );
}

export default function AShareRankingRows({
  rows,
  windowDays,
}: AShareRankingRowsProps) {
  return (
    <div className="max-h-[760px] overflow-y-auto pr-1">
      <div className="grid grid-cols-[52px_minmax(0,1fr)_80px_84px] gap-3 border-b border-green-100 pb-2 text-xs font-medium text-muted-foreground">
        <span>排名</span>
        <span>股票</span>
        <span className="text-right">提及</span>
        <span className="text-right">变化</span>
      </div>
      {rows.map((item, index) => (
        <div
          key={`${windowDays}-${item.company}`}
          className="grid grid-cols-[52px_minmax(0,1fr)_80px_84px] items-center gap-3 border-b border-dashed py-2 text-sm last:border-b-0"
        >
          <span className="font-medium tabular-nums text-gray-900">{item.rank ?? index + 1}</span>
          <span className="truncate" title={item.company}>
            {item.company}
          </span>
          <span className="text-right font-medium tabular-nums">{item.count}</span>
          <span className="flex justify-end">
            <RankTrendBadge item={item} />
          </span>
        </div>
      ))}
    </div>
  );
}
