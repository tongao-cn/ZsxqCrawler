'use client';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { ScrollArea } from '@/components/ui/scroll-area';
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

function getStatusLabel(result: StockTopicAnalysisResponse) {
  if ((result.new_topic_count ?? 0) > 0 && result.summary_markdown) {
    return `有 ${result.new_topic_count} 条待处理话题`;
  }
  if (result.status === 'failed') {
    return '失败';
  }
  if (result.status === 'missing') {
    return result.topic_count > 0 ? '待分析' : '未保存';
  }
  if (result.summary_markdown) {
    return '已处理';
  }
  if (result.status === 'completed' && result.topic_count <= 0) {
    return '无话题';
  }
  if (result.topic_count > 0) {
    return '待分析';
  }
  return '无话题';
}

function getStatusBadge(result: StockTopicAnalysisResponse) {
  const label = getStatusLabel(result);
  if (label.startsWith('有 ')) {
    return <Badge className="bg-blue-100 text-blue-800">{label}</Badge>;
  }
  switch (label) {
    case '已处理':
      return <Badge className="bg-green-100 text-green-800">已处理</Badge>;
    case '待分析':
      return <Badge className="bg-amber-100 text-amber-800">待分析</Badge>;
    case '失败':
      return <Badge className="bg-red-100 text-red-800">失败</Badge>;
    case '无话题':
      return <Badge className="bg-gray-100 text-gray-700">无话题</Badge>;
    default:
      return <Badge variant="secondary">{label}</Badge>;
  }
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
                <div className="mt-1">{getStatusBadge(selectedResult)}</div>
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
