import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import type { DailyStockConcept } from '@/lib/api';
import { normalizeCompanyName, normalizeConceptName } from '@/components/DailyTopicAnalysisPanelUtils';

interface DailyStockConceptStockTableProps {
  filteredStocks: DailyStockConcept[];
  onConceptSelect: (concept: string) => void;
  onOpenStockDetail: (stock: DailyStockConcept) => void;
  onOpenTopicDetail: (topicId: string | number) => void;
  recommendedCompanies: Set<string>;
  selectedConcept: string | null;
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

export default function DailyStockConceptStockTable({
  filteredStocks,
  onConceptSelect,
  onOpenStockDetail,
  onOpenTopicDetail,
  recommendedCompanies,
  selectedConcept,
}: DailyStockConceptStockTableProps) {
  return (
    <ScrollArea className="h-[420px] rounded-md border border-gray-200">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>股票</TableHead>
            <TableHead>代码</TableHead>
            <TableHead>推荐池</TableHead>
            <TableHead>概念</TableHead>
            <TableHead>来源话题</TableHead>
            <TableHead>置信度</TableHead>
            <TableHead>理由</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {filteredStocks.map((stock) => (
            <TableRow key={`${stock.stock_name}-${stock.stock_code || 'unknown'}`}>
              <TableCell>
                <Button
                  variant="link"
                  className="h-auto px-0 py-0 font-medium"
                  onClick={() => onOpenStockDetail(stock)}
                >
                  {stock.stock_name}
                </Button>
              </TableCell>
              <TableCell>
                {stock.stock_code ? `${stock.stock_code}${stock.market ? `.${stock.market}` : ''}` : '未匹配'}
              </TableCell>
              <TableCell>
                {recommendedCompanies.has(normalizeCompanyName(stock.stock_name)) ? (
                  <Badge className="bg-emerald-100 text-emerald-800">命中</Badge>
                ) : (
                  <span className="text-muted-foreground">-</span>
                )}
              </TableCell>
              <TableCell className="max-w-xs whitespace-normal">
                <div className="flex flex-wrap gap-1">
                  {stock.concepts.map((concept) => {
                    const normalizedConcept = normalizeConceptName(concept);
                    return (
                      <Badge
                        key={concept}
                        variant={normalizedConcept === selectedConcept ? 'default' : 'secondary'}
                        className="cursor-pointer"
                        onClick={() => onConceptSelect(normalizedConcept)}
                        title={normalizedConcept !== concept ? `已合并到：${normalizedConcept}` : concept}
                      >
                        {concept}
                        {normalizedConcept !== concept ? ` -> ${normalizedConcept}` : ''}
                      </Badge>
                    );
                  })}
                </div>
              </TableCell>
              <TableCell className="max-w-[180px] whitespace-normal">
                <TopicButtons
                  onOpenTopicDetail={onOpenTopicDetail}
                  topicIds={stock.topic_ids}
                />
              </TableCell>
              <TableCell>{Math.round((stock.confidence || 0) * 100)}%</TableCell>
              <TableCell className="max-w-md whitespace-normal text-muted-foreground">
                {stock.reason || '-'}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </ScrollArea>
  );
}
