'use client';

import { memo } from 'react';
import { RefreshCw } from 'lucide-react';

import SafeImage from '@/components/SafeImage';
import ImageGallery from '@/components/ImageGallery';
import { apiClient } from '@/lib/api';
import { createSafeHtmlWithHighlight, extractPlainText } from '@/lib/zsxq-content-renderer';

type TopicId = string | number;

interface TopicLike {
  topic_id: TopicId;
  comments_count?: number;
}

interface UserLike {
  avatar_url?: string;
  name?: string;
}

interface CommentLike {
  comment_id?: TopicId;
  owner?: UserLike;
  repliee?: UserLike;
  create_time?: string;
  text?: string;
  images?: any[];
  replied_comments?: CommentLike[];
}

interface TopicDetailLike {
  comments_count?: number;
  show_comments?: CommentLike[];
}

interface TopicCommentsProps {
  topic: TopicLike;
  topicDetail?: TopicDetailLike | null;
  groupId: TopicId;
  searchTerm?: string;
  expandedComments: ReadonlySet<string>;
  fetchingComments: ReadonlySet<string>;
  onFetchMoreComments: (topicId: TopicId) => void | Promise<void>;
  onToggleComments: (topicId: TopicId) => void;
  formatDateTime?: (dateString: string) => string;
}

const defaultFormatDateTime = (dateString: string) => {
  if (!dateString) return '未知时间';
  try {
    const date = new Date(dateString);
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return '时间格式错误';
  }
};

const estimateCommentHeight = (comment: CommentLike): number => {
  const baseHeight = 40;
  const textContent = extractPlainText(comment.text || '');
  const lineCount = Math.max(1, textContent.split('\n').length);
  const textHeight = lineCount * 16;
  const imageHeight = comment.images && comment.images.length > 0 ? 72 : 0;
  const padding = 16;

  return baseHeight + textHeight + imageHeight + padding;
};

const calculateVisibleComments = (comments: CommentLike[], maxHeight: number = 180): number => {
  let totalHeight = 0;
  let visibleCount = 0;

  for (let i = 0; i < comments.length; i++) {
    const commentHeight = estimateCommentHeight(comments[i]);
    if (totalHeight + commentHeight <= maxHeight) {
      totalHeight += commentHeight;
      visibleCount++;
    } else {
      break;
    }
  }

  const minComments = Math.min(3, comments.length);
  return Math.max(minComments, visibleCount);
};

function TopicComments({
  topic,
  topicDetail,
  groupId,
  searchTerm = '',
  expandedComments,
  fetchingComments,
  onFetchMoreComments,
  onToggleComments,
  formatDateTime = defaultFormatDateTime,
}: TopicCommentsProps) {
  const comments = topicDetail?.show_comments || [];

  if (comments.length === 0) {
    return null;
  }

  const topicId = topic.topic_id;
  const topicKey = String(topicId);
  const groupIdValue = groupId.toString();
  const isExpanded = expandedComments.has(topicKey);
  const visibleCommentCount = isExpanded ? comments.length : calculateVisibleComments(comments);
  const commentsToShow = comments.slice(0, visibleCommentCount);
  const isFetching = fetchingComments.has(topicKey);
  const commentsCount = topicDetail?.comments_count ?? topic.comments_count ?? 0;
  const hasMoreComments = comments.length > visibleCommentCount;
  const shouldShowToggle = isExpanded || hasMoreComments;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h4 className="text-xs font-medium text-gray-600">
          评论 ({commentsCount})
        </h4>
        {commentsCount > 8 && (
          <button
            type="button"
            onClick={() => onFetchMoreComments(topicId)}
            disabled={isFetching}
            className="text-xs text-blue-600 hover:text-blue-800 disabled:text-gray-400 flex items-center gap-1"
          >
            {isFetching ? (
              <>
                <RefreshCw className="w-3 h-3 animate-spin" />
                获取中...
              </>
            ) : (
              <>
                <RefreshCw className="w-3 h-3" />
                获取更多
              </>
            )}
          </button>
        )}
      </div>

      <div className="space-y-2">
        {commentsToShow.map((comment, index) => {
          const ownerName = comment.owner?.name || '未知用户';

          return (
            <div key={String(comment.comment_id ?? index)} className="bg-gray-50 rounded-lg p-2">
              <div className="flex items-center gap-2 mb-1">
                <SafeImage
                  src={apiClient.getProxyImageUrl(comment.owner?.avatar_url || '', groupIdValue)}
                  alt={ownerName}
                  className="w-4 h-4 rounded-full object-cover block"
                  fallbackClassName="w-4 h-4 rounded-full"
                  fallbackText={ownerName.slice(0, 1)}
                />
                <span className="text-xs font-medium text-gray-700">
                  {ownerName}
                </span>
                {comment.repliee && (
                  <>
                    <span className="text-xs text-gray-400">回复</span>
                    <span className="text-xs font-medium text-blue-600">
                      {comment.repliee.name}
                    </span>
                  </>
                )}
                <span className="text-xs text-gray-500">
                  {formatDateTime(comment.create_time || '')}
                </span>
              </div>
              <div
                className="text-xs text-gray-600 ml-6 break-words prose prose-xs max-w-none prose-a:text-blue-600"
                dangerouslySetInnerHTML={createSafeHtmlWithHighlight(comment.text || '', searchTerm)}
              />

              {comment.images && comment.images.length > 0 && (
                <div className="ml-6 mt-2">
                  <ImageGallery
                    images={comment.images}
                    className="comment-images"
                    size="small"
                    groupId={groupIdValue}
                  />
                </div>
              )}

              {comment.replied_comments && comment.replied_comments.length > 0 && (
                <div className="ml-6 mt-2 space-y-2 border-l-2 border-gray-200 pl-3">
                  {comment.replied_comments.map((reply, replyIndex) => {
                    const replyOwnerName = reply.owner?.name || '未知用户';

                    return (
                      <div key={String(reply.comment_id ?? replyIndex)} className="bg-white rounded p-2">
                        <div className="flex items-center gap-2 mb-1">
                          {reply.owner && (
                            <SafeImage
                              src={apiClient.getProxyImageUrl(reply.owner.avatar_url || '', groupIdValue)}
                              alt={replyOwnerName}
                              className="w-3 h-3 rounded-full object-cover block"
                              fallbackClassName="w-3 h-3 rounded-full"
                              fallbackText={replyOwnerName.slice(0, 1)}
                            />
                          )}
                          <span className="text-xs font-medium text-gray-600">
                            {replyOwnerName}
                          </span>
                          {reply.repliee && (
                            <>
                              <span className="text-xs text-gray-400">回复</span>
                              <span className="text-xs font-medium text-blue-500">
                                {reply.repliee.name}
                              </span>
                            </>
                          )}
                          <span className="text-xs text-gray-400">
                            {formatDateTime(reply.create_time || '')}
                          </span>
                        </div>
                        <div
                          className="text-xs text-gray-500 ml-5 break-words prose prose-xs max-w-none prose-a:text-blue-600"
                          dangerouslySetInnerHTML={createSafeHtmlWithHighlight(reply.text || '', searchTerm)}
                        />
                        {reply.images && reply.images.length > 0 && (
                          <div className="ml-5 mt-1">
                            <ImageGallery
                              images={reply.images}
                              className="reply-images"
                              size="small"
                              groupId={groupIdValue}
                            />
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {shouldShowToggle && (
        <div className="text-center mt-2">
          <button
            type="button"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              onToggleComments(topicId);
            }}
            className="text-xs text-blue-600 hover:text-blue-800 font-medium transition-colors"
          >
            {isExpanded ? '收起' : `展开全部 (${comments.length - visibleCommentCount}条)`}
          </button>
        </div>
      )}
    </div>
  );
}

export default memo(TopicComments);
