'use client';

import type { TopicDetail } from '@/lib/api';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { createSafeHtml, extractPlainText } from '@/lib/zsxq-content-renderer';

interface DailyTopicDetailDialogProps {
  loading: boolean;
  onOpenChange: (open: boolean) => void;
  open: boolean;
  topicDetail: TopicDetail | null;
  topicId: string | null;
}

function formatDateTime(value?: string | null) {
  if (!value) {
    return '暂无';
  }
  return new Date(value).toLocaleString('zh-CN');
}

export default function DailyTopicDetailDialog({
  loading,
  onOpenChange,
  open,
  topicDetail,
  topicId,
}: DailyTopicDetailDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-auto sm:max-w-4xl">
        <DialogHeader>
          <DialogTitle>来源话题 {topicId}</DialogTitle>
          <DialogDescription>从股票概念结果回溯到原始话题内容</DialogDescription>
        </DialogHeader>
        {loading ? (
          <div className="text-sm text-muted-foreground">加载中...</div>
        ) : topicDetail ? (
          <div className="flex flex-col gap-4">
            <div className="grid gap-3 md:grid-cols-3">
              <div className="rounded-md border border-gray-200 p-3">
                <div className="text-sm text-muted-foreground">类型</div>
                <div className="mt-1 font-medium">{topicDetail.type || '未知'}</div>
              </div>
              <div className="rounded-md border border-gray-200 p-3">
                <div className="text-sm text-muted-foreground">创建时间</div>
                <div className="mt-1 font-medium">{formatDateTime(topicDetail.create_time)}</div>
              </div>
              <div className="rounded-md border border-gray-200 p-3">
                <div className="text-sm text-muted-foreground">互动</div>
                <div className="mt-1 font-medium">
                  阅读 {topicDetail.reading_count || 0} / 点赞 {topicDetail.likes_count || 0} / 评论 {topicDetail.comments_count || 0}
                </div>
              </div>
            </div>
            {topicDetail.title && (
              <div>
                <div className="mb-2 text-sm font-medium">标题</div>
                <div className="rounded-md bg-gray-50 p-3 text-sm leading-6">
                  {extractPlainText(topicDetail.title)}
                </div>
              </div>
            )}
            {topicDetail.talk?.text && (
              <div>
                <div className="mb-2 text-sm font-medium">正文</div>
                <div
                  className="rounded-md bg-gray-50 p-3 text-sm leading-6"
                  dangerouslySetInnerHTML={createSafeHtml(topicDetail.talk.text)}
                />
              </div>
            )}
            {topicDetail.question?.text && (
              <div>
                <div className="mb-2 text-sm font-medium">问题</div>
                <div
                  className="rounded-md bg-gray-50 p-3 text-sm leading-6"
                  dangerouslySetInnerHTML={createSafeHtml(topicDetail.question.text)}
                />
              </div>
            )}
            {topicDetail.answer?.text && (
              <div>
                <div className="mb-2 text-sm font-medium">回答</div>
                <div
                  className="rounded-md bg-gray-50 p-3 text-sm leading-6"
                  dangerouslySetInnerHTML={createSafeHtml(topicDetail.answer.text)}
                />
              </div>
            )}
          </div>
        ) : (
          <div className="text-sm text-muted-foreground">暂无话题详情</div>
        )}
      </DialogContent>
    </Dialog>
  );
}
