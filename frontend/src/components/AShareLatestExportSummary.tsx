'use client';

import { Upload } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { formatAShareDateTime } from '@/components/AShareAnalysisDisplay';
import type { AShareAnalysisLatestTdxExport } from '@/lib/api';

interface AShareLatestExportSummaryProps {
  exportingTdx: boolean;
  latestExport?: AShareAnalysisLatestTdxExport | null;
  onExportToTdx: () => void;
}

function formatDateRange(start?: string | null, end?: string | null) {
  if (start && end) {
    return `${start} 至 ${end}`;
  }
  if (start) {
    return start;
  }
  if (end) {
    return end;
  }
  return '全范围';
}

export default function AShareLatestExportSummary({
  exportingTdx,
  latestExport,
  onExportToTdx,
}: AShareLatestExportSummaryProps) {
  return (
    <div className="space-y-3 border-t border-gray-200 pt-4">
      <div className="text-sm font-medium text-gray-900">发布到通达信</div>
      <Button variant="outline" className="w-full" onClick={onExportToTdx} disabled={exportingTdx}>
        <Upload className={`h-4 w-4 ${exportingTdx ? 'animate-pulse' : ''}`} />
        {exportingTdx ? '导入中...' : '导入覆盖三板块'}
      </Button>
      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="rounded border border-gray-200 bg-white p-2">
          <div className="text-muted-foreground">写入总数</div>
          <div className="font-semibold">{latestExport?.total_written ?? 0}</div>
        </div>
        <div className="rounded border border-gray-200 bg-white p-2">
          <div className="text-muted-foreground">未匹配</div>
          <div className="font-semibold">{latestExport?.unresolved_count ?? 0}</div>
        </div>
      </div>
      {latestExport ? (
        <details className="rounded-lg border border-gray-200 bg-gray-50 p-3 text-xs">
          <summary className="cursor-pointer font-medium text-gray-900">最近导入记录</summary>
          <div className="mt-3 space-y-2 text-muted-foreground">
            <div>导入时间：{formatAShareDateTime(latestExport.exported_at)}</div>
            <div>范围：{formatDateRange(latestExport.start_date, latestExport.end_date)}</div>
            <div>股票主数据：{latestExport.stock_basic_source || '未知'}</div>
            <div className="grid grid-cols-1 gap-2">
              {latestExport.blocks.map((block) => (
                <div key={`latest-export-${block.window_days}`} className="rounded border border-gray-200 bg-white p-2">
                  <div className="font-medium text-gray-900">{block.block_name}</div>
                  <div>写入 {block.written_count}，跳过 {block.skipped_count}</div>
                </div>
              ))}
            </div>
            {latestExport.unresolved_companies.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {latestExport.unresolved_companies.slice(0, 8).map((company) => (
                  <Badge key={company} variant="outline" className="bg-white">
                    {company}
                  </Badge>
                ))}
                {latestExport.unresolved_companies.length > 8 ? (
                  <Badge variant="outline" className="bg-white">
                    +{latestExport.unresolved_companies.length - 8}
                  </Badge>
                ) : null}
              </div>
            ) : null}
          </div>
        </details>
      ) : (
        <div className="rounded-lg border border-gray-200 bg-gray-50 p-3 text-xs text-muted-foreground">
          还没有导入记录。
        </div>
      )}
    </div>
  );
}
