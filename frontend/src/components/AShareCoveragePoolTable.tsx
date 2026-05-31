'use client';

import { ArrowDown, ArrowUp, Minus } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import type { AShareAnalysisCoverageItem } from '@/lib/api';

const COVERAGE_FILTERS = [
  { key: 'all', label: '全部' },
  { key: 'core', label: '核心1-50' },
  { key: 'main', label: '主池51-100' },
  { key: 'extended', label: '扩展101-200' },
  { key: 'long_tail', label: '长尾201-300' },
  { key: 'short_active', label: '短周期补充' },
  { key: 'short_tags', label: '7/14日活跃' },
];

interface AShareCoveragePoolTableProps {
  activeFilter: string;
  onFilterChange: (value: string) => void;
  rows: AShareAnalysisCoverageItem[];
}

function formatRank(value?: number | null) {
  return value ? `#${value}` : '-';
}

function CoverageLayerBadge({ item }: { item: AShareAnalysisCoverageItem }) {
  const styles: Record<string, string> = {
    core: 'bg-red-100 text-red-800',
    main: 'bg-orange-100 text-orange-800',
    extended: 'bg-blue-100 text-blue-800',
    long_tail: 'bg-gray-100 text-gray-700',
    short_active: 'bg-emerald-100 text-emerald-800',
  };
  return <Badge className={styles[item.layer] || 'bg-gray-100 text-gray-700'}>{item.layer_label}</Badge>;
}

function CoverageTrendBadge({ item }: { item: AShareAnalysisCoverageItem }) {
  if (item.trend_30 === 'new') {
    return <Badge className="bg-blue-100 text-blue-800">新进</Badge>;
  }
  if (item.trend_30 === 'up') {
    return (
      <Badge className="gap-1 bg-red-100 text-red-800">
        <ArrowUp className="h-3 w-3" />
        {Math.abs(item.rank_change_30 ?? 0)}
      </Badge>
    );
  }
  if (item.trend_30 === 'down') {
    return (
      <Badge className="gap-1 bg-green-100 text-green-800">
        <ArrowDown className="h-3 w-3" />
        {Math.abs(item.rank_change_30 ?? 0)}
      </Badge>
    );
  }
  if (item.trend_30 === 'flat') {
    return (
      <Badge variant="outline" className="gap-1 bg-white text-gray-600">
        <Minus className="h-3 w-3" />
        持平
      </Badge>
    );
  }
  return <Badge className="bg-emerald-100 text-emerald-800">短期</Badge>;
}

export default function AShareCoveragePoolTable({
  activeFilter,
  onFilterChange,
  rows,
}: AShareCoveragePoolTableProps) {
  const filteredRows = rows.filter((item) => {
    if (activeFilter === 'all') {
      return true;
    }
    if (activeFilter === 'short_tags') {
      return Boolean(item.rank_7 || item.rank_14);
    }
    return item.layer === activeFilter;
  });

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {COVERAGE_FILTERS.map((filter) => (
          <Button
            key={filter.key}
            type="button"
            size="sm"
            variant={activeFilter === filter.key ? 'default' : 'outline'}
            onClick={() => onFilterChange(filter.key)}
          >
            {filter.label}
          </Button>
        ))}
      </div>
      <div className="text-xs text-muted-foreground">
        当前显示 {filteredRows.length} / {rows.length} 只
      </div>
      <div className="overflow-x-auto">
        <div className="max-h-[760px] min-w-[860px] overflow-y-auto pr-1">
          <div className="grid grid-cols-[90px_minmax(0,1fr)_70px_70px_70px_92px_minmax(120px,1.2fr)] gap-3 border-b border-green-100 pb-2 text-xs font-medium text-muted-foreground">
            <span>层级</span>
            <span>股票</span>
            <span className="text-right">30日</span>
            <span className="text-right">7日</span>
            <span className="text-right">14日</span>
            <span className="text-right">变化</span>
            <span>标签</span>
          </div>
          {filteredRows.map((item) => (
            <div
              key={item.company}
              className="grid grid-cols-[90px_minmax(0,1fr)_70px_70px_70px_92px_minmax(120px,1.2fr)] items-center gap-3 border-b border-dashed py-2 text-sm last:border-b-0"
            >
              <span>
                <CoverageLayerBadge item={item} />
              </span>
              <span className="truncate font-medium" title={item.company}>
                {item.company}
              </span>
              <span className="text-right tabular-nums">{formatRank(item.rank_30)}</span>
              <span className="text-right tabular-nums">{formatRank(item.rank_7)}</span>
              <span className="text-right tabular-nums">{formatRank(item.rank_14)}</span>
              <span className="flex justify-end">
                <CoverageTrendBadge item={item} />
              </span>
              <span className="flex flex-wrap gap-1">
                {item.tags.length > 0 ? (
                  item.tags.map((tag) => (
                    <Badge key={`${item.company}-${tag}`} variant="outline" className="bg-white text-gray-700">
                      {tag}
                    </Badge>
                  ))
                ) : (
                  <span className="text-xs text-muted-foreground">-</span>
                )}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
