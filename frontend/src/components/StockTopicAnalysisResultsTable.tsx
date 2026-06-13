'use client';

import { Eye, Sparkles } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import {
  formatStockTopicAnalysisDateTime,
  StockTopicAnalysisStatusBadge,
} from '@/components/StockTopicAnalysisDisplay';
import type { StockTopicAnalysisResponse } from '@/lib/api';

interface StockTopicAnalysisResultsTableProps {
  active: boolean;
  allResultsSelected: boolean;
  analyzing: boolean;
  getResultKey: (result: StockTopicAnalysisResponse) => string;
  onAnalyzeOne: (result: StockTopicAnalysisResponse) => void;
  onOpenResult: (result: StockTopicAnalysisResponse) => void;
  onToggleAllResults: (checked: boolean) => void;
  onToggleResult: (result: StockTopicAnalysisResponse, checked: boolean) => void;
  results: StockTopicAnalysisResponse[];
  selectedStockNames: Set<string>;
}

export default function StockTopicAnalysisResultsTable({
  active,
  allResultsSelected,
  analyzing,
  getResultKey,
  onAnalyzeOne,
  onOpenResult,
  onToggleAllResults,
  onToggleResult,
  results,
  selectedStockNames,
}: StockTopicAnalysisResultsTableProps) {
  if (results.length === 0) {
    return (
      <div className="flex min-h-48 items-center justify-center rounded-md border border-dashed text-sm text-muted-foreground">
        输入股票后点击搜索，查看话题命中和已保存分析
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-10">
              <input
                type="checkbox"
                aria-label="选择当前结果全部股票"
                checked={allResultsSelected}
                onChange={(event) => onToggleAllResults(event.target.checked)}
                className="h-4 w-4 rounded border-gray-300 align-middle"
              />
            </TableHead>
            <TableHead>股票</TableHead>
            <TableHead className="text-right">话题数</TableHead>
            <TableHead className="text-right">待处理话题</TableHead>
            <TableHead>概念</TableHead>
            <TableHead className="text-right">推荐次数</TableHead>
            <TableHead>状态</TableHead>
            <TableHead>保存时间</TableHead>
            <TableHead className="text-right">操作</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {results.map((result) => (
            <TableRow key={`${result.stock_name}-${result.stock_code || 'no-code'}`}>
              <TableCell>
                <input
                  type="checkbox"
                  aria-label={`选择 ${result.stock_name}`}
                  checked={selectedStockNames.has(getResultKey(result))}
                  onChange={(event) => onToggleResult(result, event.target.checked)}
                  className="h-4 w-4 rounded border-gray-300 align-middle"
                />
              </TableCell>
              <TableCell className="font-medium">{result.stock_name}</TableCell>
              <TableCell className="text-right">{result.topic_count}</TableCell>
              <TableCell className="text-right">{result.new_topic_count ?? '-'}</TableCell>
              <TableCell>
                {result.concepts.length === 0 ? (
                  <span className="text-muted-foreground">-</span>
                ) : (
                  <div className="flex max-w-64 flex-wrap gap-1">
                    {result.concepts.slice(0, 4).map((concept) => (
                      <Badge key={concept} variant="secondary">{concept}</Badge>
                    ))}
                    {result.concepts.length > 4 && <Badge variant="outline">+{result.concepts.length - 4}</Badge>}
                  </div>
                )}
              </TableCell>
              <TableCell className="text-right">{result.recommendation_count}</TableCell>
              <TableCell><StockTopicAnalysisStatusBadge result={result} /></TableCell>
              <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                {formatStockTopicAnalysisDateTime(result.updated_at)}
              </TableCell>
              <TableCell className="text-right">
                <div className="flex justify-end gap-2 whitespace-nowrap">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => onAnalyzeOne(result)}
                    disabled={analyzing || active}
                  >
                    <Sparkles className="mr-2 h-4 w-4" />
                    分析
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => onOpenResult(result)}>
                    <Eye className="mr-2 h-4 w-4" />
                    查看
                  </Button>
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
