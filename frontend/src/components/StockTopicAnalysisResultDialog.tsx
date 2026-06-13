'use client';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { ScrollArea } from '@/components/ui/scroll-area';
import { StockTopicAnalysisStatusBadge } from '@/components/StockTopicAnalysisStatusBadge';
import type { StockTopicAnalysisResponse } from '@/lib/api';

interface StockTopicAnalysisResultDialogProps {
  onOpenChange: (open: boolean) => void;
  selectedResult: StockTopicAnalysisResponse | null;
}

function formatDateTime(value?: string | null) {
  if (!value) {
    return '-';
  }
  try {
    return new Date(value).toLocaleString('zh-CN');
  } catch {
    return value;
  }
}

function formatStockCode(result: StockTopicAnalysisResponse) {
  if (!result.stock_code) {
    return '-';
  }
  return result.market ? `${result.market}.${result.stock_code}` : result.stock_code;
}

export default function StockTopicAnalysisResultDialog({
  onOpenChange,
  selectedResult,
}: StockTopicAnalysisResultDialogProps) {
  return (
    <Dialog open={Boolean(selectedResult)} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] w-[calc(100vw-32px)] max-w-[1200px] grid-rows-[auto_auto_auto_minmax(0,1fr)] overflow-hidden sm:max-w-[1200px]">
        {selectedResult && (
          <>
            <DialogHeader>
              <DialogTitle className="text-xl">{selectedResult.stock_name} AI 总结</DialogTitle>
              <DialogDescription>
                {formatStockCode(selectedResult)} · 话题 {selectedResult.topic_count} · 待处理话题 {selectedResult.new_topic_count ?? 0} · 推荐 {selectedResult.recommendation_count} · {formatDateTime(selectedResult.updated_at)}
              </DialogDescription>
            </DialogHeader>
            <div className="grid gap-3 text-sm sm:grid-cols-4">
              <div className="rounded-md border p-3">
                <div className="text-muted-foreground">状态</div>
                <div className="mt-1"><StockTopicAnalysisStatusBadge result={selectedResult} /></div>
              </div>
              <div className="rounded-md border p-3">
                <div className="text-muted-foreground">话题数</div>
                <div className="mt-1 font-semibold">{selectedResult.topic_count}</div>
              </div>
              <div className="rounded-md border p-3">
                <div className="text-muted-foreground">推荐次数</div>
                <div className="mt-1 font-semibold">{selectedResult.recommendation_count}</div>
              </div>
              <div className="rounded-md border p-3">
                <div className="text-muted-foreground">模型</div>
                <div className="mt-1 truncate font-medium">{selectedResult.model || '-'}</div>
              </div>
            </div>
            {selectedResult.concepts.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {selectedResult.concepts.map((concept) => (
                  <Badge key={concept} variant="secondary">{concept}</Badge>
                ))}
              </div>
            )}
            <ScrollArea className="min-h-0 h-[62vh] rounded-md border p-6">
              {selectedResult.summary_markdown ? (
                <div className="markdown-body">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{selectedResult.summary_markdown}</ReactMarkdown>
                </div>
              ) : (
                <div className="text-sm text-muted-foreground">
                  {selectedResult.error || '暂无 AI 总结，请先点击一键分析。'}
                </div>
              )}
            </ScrollArea>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
