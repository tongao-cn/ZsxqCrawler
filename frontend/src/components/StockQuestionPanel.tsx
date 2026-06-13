'use client';

import { useCallback, useMemo, useState } from 'react';
import { HelpCircle, Loader2, Search, Sparkles } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { toast } from 'sonner';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Textarea } from '@/components/ui/textarea';
import { useTaskStatus } from '@/hooks/useTaskStatus';
import { apiClient, StockQuestionResponse } from '@/lib/api';
import { formatStockAnalysisDateTime } from '@/lib/stock-analysis-format';

interface StockQuestionPanelProps {
  groupId: number | string;
  onTaskCreated?: (taskId: string) => void;
}

export default function StockQuestionPanel({ groupId, onTaskCreated }: StockQuestionPanelProps) {
  const [question, setQuestion] = useState('');
  const [result, setResult] = useState<StockQuestionResponse | null>(null);
  const [searching, setSearching] = useState(false);
  const [creatingTask, setCreatingTask] = useState(false);
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);

  const normalizedQuestion = question.trim();
  const canSubmit = normalizedQuestion.length > 0;
  const answerSummary = useMemo(() => result?.summary_markdown?.trim() || '', [result]);

  const handleSearch = useCallback(async () => {
    if (!canSubmit) {
      toast.error('请输入问题');
      return;
    }
    try {
      setSearching(true);
      const data = await apiClient.searchStockQuestionTopics(groupId, normalizedQuestion);
      setResult(data);
      toast.success(`已命中 ${data.topic_count} 条相关话题`);
    } catch (error) {
      toast.error(`搜索失败: ${error instanceof Error ? error.message : '未知错误'}`);
    } finally {
      setSearching(false);
    }
  }, [canSubmit, groupId, normalizedQuestion]);

  const handleAnalyze = useCallback(async () => {
    if (!canSubmit) {
      toast.error('请输入问题');
      return;
    }
    try {
      setCreatingTask(true);
      const response = await apiClient.analyzeStockQuestion(groupId, normalizedQuestion);
      setActiveTaskId(response.task_id);
      onTaskCreated?.(response.task_id);
      toast.success(`A股问答任务已创建: ${response.task_id}`);
    } catch (error) {
      toast.error(`创建A股问答任务失败: ${error instanceof Error ? error.message : '未知错误'}`);
    } finally {
      setCreatingTask(false);
    }
  }, [canSubmit, groupId, normalizedQuestion, onTaskCreated]);

  useTaskStatus(activeTaskId, {
    enabled: Boolean(activeTaskId),
    onTerminal: (task) => {
      if (task.status === 'completed' && task.result) {
        setResult(task.result as StockQuestionResponse);
        toast.success('A股问答总结完成');
      } else {
        toast.error(task.message || 'A股问答任务未完成');
      }
      setActiveTaskId(null);
    },
  });

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
      <div className="space-y-4">
        <Card>
          <CardHeader>
            <CardTitle>A股问答</CardTitle>
            <CardDescription>输入问题，先按关键词搜索当前群组话题，再用 AI 基于命中内容总结</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Textarea
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="例如：最近群里怎么看固态电池？哪些公司被反复提到？"
              className="min-h-24 resize-y"
            />
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="text-sm text-muted-foreground">
                {result ? `关键词：${result.keywords.join('、') || '-'}` : '会自动从问题中提取关键词'}
              </div>
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" onClick={() => void handleSearch()} disabled={searching || !canSubmit}>
                  {searching ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Search className="mr-2 h-4 w-4" />}
                  搜索话题
                </Button>
                <Button onClick={() => void handleAnalyze()} disabled={creatingTask || Boolean(activeTaskId) || !canSubmit}>
                  {activeTaskId || creatingTask ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Sparkles className="mr-2 h-4 w-4" />}
                  {activeTaskId ? '总结中...' : 'AI总结'}
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>AI 回答</CardTitle>
            <CardDescription>回答只使用当前命中的话题内容</CardDescription>
          </CardHeader>
          <CardContent>
            {answerSummary ? (
              <ScrollArea className="h-[420px] rounded-md border p-5">
                <div className="prose max-w-none text-base leading-7">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{answerSummary}</ReactMarkdown>
                </div>
              </ScrollArea>
            ) : (
              <div className="flex min-h-48 items-center justify-center rounded-md border border-dashed text-sm text-muted-foreground">
                搜索后可预览话题，点击 AI总结 后在这里查看回答
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>命中话题</CardTitle>
            <CardDescription>按话题发布时间倒序展示关键词命中</CardDescription>
          </CardHeader>
          <CardContent>
            {!result || result.topics.length === 0 ? (
              <div className="flex min-h-40 items-center justify-center rounded-md border border-dashed text-sm text-muted-foreground">
                暂无命中话题
              </div>
            ) : (
              <div className="overflow-hidden rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>话题</TableHead>
                      <TableHead>关键词</TableHead>
                      <TableHead className="text-right">互动</TableHead>
                      <TableHead>时间</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {result.topics.map((topic) => (
                      <TableRow key={topic.topic_id}>
                        <TableCell className="max-w-xl">
                          <div className="font-medium">{topic.title || topic.topic_id}</div>
                          <div className="mt-1 line-clamp-2 text-xs text-muted-foreground">{topic.content_preview}</div>
                          <div className="mt-1 font-mono text-[11px] text-muted-foreground">topic_id: {topic.topic_id}</div>
                        </TableCell>
                        <TableCell>
                          <div className="flex max-w-52 flex-wrap gap-1">
                            {topic.matched_keywords.length > 0 ? topic.matched_keywords.map((keyword) => (
                              <Badge key={`${topic.topic_id}-${keyword}`} variant="secondary">{keyword}</Badge>
                            )) : <span className="text-muted-foreground">-</span>}
                          </div>
                        </TableCell>
                        <TableCell className="whitespace-nowrap text-right text-xs text-muted-foreground">
                          赞 {topic.likes_count} / 评 {topic.comments_count} / 读 {topic.reading_count}
                        </TableCell>
                        <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                          {formatStockAnalysisDateTime(topic.create_time)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <Card className="h-fit">
        <CardHeader>
          <CardTitle>问答统计</CardTitle>
          <CardDescription>当前问题的检索状态</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">关键词</span>
            <span className="font-medium">{result?.keywords.length ?? 0}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">命中话题</span>
            <span className="font-medium">{result?.topic_count ?? 0}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">模型</span>
            <span className="max-w-40 truncate font-medium">{result?.model || '-'}</span>
          </div>
          {activeTaskId && (
            <div className="rounded-md border border-blue-100 bg-blue-50 p-3 text-xs text-blue-700">
              A股问答任务运行中，完成后会自动回填回答。
            </div>
          )}
          <div className="rounded-md border bg-gray-50 p-3 text-xs leading-5 text-muted-foreground">
            <div className="mb-1 flex items-center gap-2 font-medium text-gray-700">
              <HelpCircle className="h-3.5 w-3.5" />
              边界
            </div>
            这里不会爬取新内容，也不会读取外部行情，只基于当前群组已入库话题回答。
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
