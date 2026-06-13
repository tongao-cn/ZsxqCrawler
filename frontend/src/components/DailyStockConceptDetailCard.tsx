import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import type { ConceptTrendItem } from '@/hooks/useDailyTopicAnalysisData';
import type { ConceptQualityTag, ConceptStat } from '@/components/DailyTopicAnalysisPanelUtils';

interface DailyStockConceptDetailCardProps {
  conceptTrendDates: string[];
  getConceptQualityTags: (stat: ConceptStat) => ConceptQualityTag[];
  onOpenTopicDetail: (topicId: string | number) => void;
  selectedConceptStat: ConceptStat | null;
  selectedConceptTrend: ConceptTrendItem | null;
}

export default function DailyStockConceptDetailCard({
  conceptTrendDates,
  getConceptQualityTags,
  onOpenTopicDetail,
  selectedConceptStat,
  selectedConceptTrend,
}: DailyStockConceptDetailCardProps) {
  if (!selectedConceptStat) {
    return (
      <div className="flex h-40 items-center justify-center rounded-md border border-dashed border-gray-300 text-sm text-muted-foreground">
        从左侧选择一个项目查看详情
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-base font-semibold">{selectedConceptStat.concept}</div>
          <div className="mt-1 text-xs text-muted-foreground">选中项详情</div>
        </div>
        <div className="flex flex-wrap gap-1">
          {getConceptQualityTags(selectedConceptStat).map((tag) => (
            <Badge key={`${selectedConceptStat.concept}-detail-${tag.label}`} className={tag.className}>
              {tag.label}
            </Badge>
          ))}
        </div>
      </div>

      {selectedConceptStat.aliases.length > 1 && (
        <div>
          <div className="mb-2 text-sm font-medium">合并别名</div>
          <div className="flex flex-wrap gap-1">
            {selectedConceptStat.aliases.map((alias) => (
              <Badge key={`${selectedConceptStat.concept}-alias-${alias}`} variant="outline">
                {alias}
              </Badge>
            ))}
          </div>
        </div>
      )}

      <div className="grid gap-3 md:grid-cols-4">
        <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
          <div className="text-xs text-muted-foreground">来源话题</div>
          <div className="mt-1 font-medium">{selectedConceptStat.topicCount}</div>
        </div>
        <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
          <div className="text-xs text-muted-foreground">相关股票</div>
          <div className="mt-1 font-medium">{selectedConceptStat.stockCount}</div>
        </div>
        <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
          <div className="text-xs text-muted-foreground">推荐池命中</div>
          <div className="mt-1 font-medium">{selectedConceptStat.recommendationHitCount}</div>
        </div>
        <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
          <div className="text-xs text-muted-foreground">7 天累计话题</div>
          <div className="mt-1 font-medium">{selectedConceptTrend?.total ?? 0}</div>
        </div>
      </div>

      <div>
        <div className="mb-2 text-sm font-medium">近 7 天趋势</div>
        {selectedConceptTrend ? (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  {conceptTrendDates.map((date) => (
                    <TableHead key={date} className="text-right">
                      {date.slice(5)}
                    </TableHead>
                  ))}
                  <TableHead className="text-right">合计</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                <TableRow>
                  {selectedConceptTrend.counts.map((count, index) => (
                    <TableCell
                      key={`${selectedConceptStat.concept}-trend-${conceptTrendDates[index]}`}
                      className="text-right tabular-nums"
                    >
                      {count ? `${count} (${selectedConceptTrend.stockCounts[index]})` : '-'}
                    </TableCell>
                  ))}
                  <TableCell className="text-right font-medium tabular-nums">
                    {selectedConceptTrend.total} ({selectedConceptTrend.stockTotal})
                  </TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </div>
        ) : (
          <div className="text-sm text-muted-foreground">暂无近 7 天趋势数据</div>
        )}
      </div>

      <div>
        <div className="mb-2 text-sm font-medium">来源话题</div>
        <div className="flex flex-wrap gap-2 rounded-md bg-gray-50 p-3">
          {selectedConceptStat.topicIds.map((topicId) => (
            <Button
              key={String(topicId)}
              variant="link"
              size="sm"
              className="h-auto px-0 py-0"
              onClick={() => onOpenTopicDetail(topicId)}
            >
              {String(topicId)}
            </Button>
          ))}
        </div>
      </div>
    </div>
  );
}
