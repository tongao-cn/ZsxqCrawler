'use client';

import { memo } from 'react';
import { Clock, ExternalLink, Heart, MessageCircle, RotateCcw, Trash2 } from 'lucide-react';

import ImageGallery from '@/components/ImageGallery';
import SafeImage from '@/components/SafeImage';
import TopicComments from '@/components/TopicComments';
import TopicFileList from '@/components/TopicFileList';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { apiClient, FileStatus } from '@/lib/api';
import { createSafeHtmlWithHighlight, extractPlainText } from '@/lib/zsxq-content-renderer';

type TopicId = string | number;

interface UserLike {
  avatar_url?: string;
  location?: string;
  name?: string;
}

interface TopicLike {
  answer_text?: string;
  author?: UserLike;
  comments_count?: number;
  create_time: string;
  digested?: boolean;
  likes_count?: number;
  question_text?: string;
  sticky?: boolean;
  talk_text?: string;
  title?: string;
  topic_id: TopicId;
  type?: string;
  imported_at?: string;
}

interface TopicDetailLike {
  answer?: {
    owner?: UserLike;
    text?: string;
  };
  comments_count?: number;
  latest_likes?: Array<{
    owner: UserLike;
  }>;
  question?: {
    anonymous?: boolean;
    owner?: UserLike;
    owner_location?: string;
    text?: string;
  };
  show_comments?: any[];
  talk?: {
    article?: {
      article_url?: string;
      inline_article_url?: string;
      title?: string;
    };
    files?: any[];
    images?: any[];
    owner?: UserLike;
  };
}

export interface TopicCardProps {
  topic: TopicLike;
  topicDetail?: TopicDetailLike | null;
  groupId: TopicId;
  searchTerm?: string;
  expandedContent: ReadonlySet<string>;
  expandedComments: ReadonlySet<string>;
  refreshingTopics: ReadonlySet<string>;
  deletingTopics: ReadonlySet<string>;
  fetchingComments: ReadonlySet<string>;
  fileStatuses: Map<number, FileStatus>;
  downloadingFiles: Set<number>;
  onRefreshTopic: (topicId: TopicId) => void | Promise<void>;
  onDeleteTopic: (topicId: TopicId) => void | Promise<void>;
  onToggleContent: (topicId: TopicId) => void;
  onFetchMoreComments: (topicId: TopicId) => void | Promise<void>;
  onToggleComments: (topicId: TopicId) => void;
  onGetFileStatus: (fileId: number, fileName?: string, fileSize?: number) => Promise<FileStatus>;
  onDownloadFile: (fileId: number, fileName: string, fileSize?: number) => void;
  formatDateTime: (dateString: string) => string;
  formatImportedTime: (importedAt: string) => string;
}

const shouldShowContentToggle = (text: string) => (
  text.split('\n').length > 4 || text.length > 300
);

function TopicCard({
  topic,
  topicDetail,
  groupId,
  searchTerm,
  expandedContent,
  expandedComments,
  refreshingTopics,
  deletingTopics,
  fetchingComments,
  fileStatuses,
  downloadingFiles,
  onRefreshTopic,
  onDeleteTopic,
  onToggleContent,
  onFetchMoreComments,
  onToggleComments,
  onGetFileStatus,
  onDownloadFile,
  formatDateTime,
  formatImportedTime,
}: TopicCardProps) {
  const topicId = String(topic.topic_id);
  const groupIdValue = groupId.toString();
  const answerText = topic.answer_text || topicDetail?.answer?.text || '';
  const talkText = topic.talk_text || '';
  const titleText = topic.title || '';
  const shouldShowAnswerToggle = shouldShowContentToggle(extractPlainText(answerText));
  const shouldShowTalkToggle = shouldShowContentToggle(extractPlainText(talkText));
  const shouldShowTitleToggle = shouldShowContentToggle(extractPlainText(titleText));
  const isRefreshing = refreshingTopics.has(topicId);
  const isDeleting = deletingTopics.has(topicId);

  return (
    <div className="border border-gray-200 shadow-none w-full max-w-full bg-white rounded-lg" style={{ width: '100%', maxWidth: '100%', boxSizing: 'border-box' }}>
      <div className="p-4 w-full max-w-full" style={{ width: '100%', maxWidth: '100%', boxSizing: 'border-box' }}>
        <div className="space-y-3 w-full">
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-2">
              {topic.type === 'q&a' ? (
                topicDetail?.answer?.owner && (
                  <>
                    <SafeImage
                      src={apiClient.getProxyImageUrl(topicDetail.answer.owner.avatar_url || '', groupIdValue)}
                      alt={topicDetail.answer.owner.name || ''}
                      className="w-8 h-8 rounded-full object-cover block"
                      fallbackClassName="w-8 h-8 rounded-full"
                      fallbackText={(topicDetail.answer.owner.name || '').slice(0, 1)}
                    />
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-gray-900">
                          {topicDetail.answer.owner.name}
                        </span>
                        {topicDetail.answer.owner.location && (
                          <span className="text-xs text-gray-400">
                            来自 {topicDetail.answer.owner.location}
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-gray-500">
                        {formatDateTime(topic.create_time)}
                      </div>
                    </div>
                  </>
                )
              ) : (
                topic.author && (
                  <>
                    <SafeImage
                      src={apiClient.getProxyImageUrl(topic.author.avatar_url || '', groupIdValue)}
                      alt={topic.author.name || ''}
                      className="w-8 h-8 rounded-full object-cover block"
                      fallbackClassName="w-8 h-8 rounded-full"
                      fallbackText={(topic.author.name || '').slice(0, 1)}
                    />
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-gray-900">
                          {topic.author.name}
                        </span>
                        {topicDetail?.talk?.owner?.location && (
                          <span className="text-xs text-gray-400">
                            来自 {topicDetail.talk.owner.location}
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-gray-500">
                        {formatDateTime(topic.create_time)}
                      </div>
                    </div>
                  </>
                )
              )}
            </div>
            <div className="flex flex-col items-end gap-1">
              <div className="flex items-center gap-2">
                <Badge variant="secondary" className="text-xs">
                  {topic.type}
                </Badge>
                {topic.sticky && (
                  <Badge variant="outline" className="text-xs text-red-600 border-red-200">
                    置顶
                  </Badge>
                )}
                {topic.digested && (
                  <Badge variant="outline" className="text-xs text-green-600 border-green-200">
                    精华
                  </Badge>
                )}

                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => onRefreshTopic(topic.topic_id)}
                  disabled={isRefreshing}
                  className="h-auto p-0 flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 hover:bg-transparent disabled:text-gray-400 transition-colors ml-2"
                  title="从服务器重新获取最新数据"
                >
                  <RotateCcw className={`w-3 h-3 ${isRefreshing ? 'animate-spin' : ''}`} />
                  {isRefreshing ? '获取中' : '远程刷新'}
                </Button>

                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      disabled={isDeleting}
                      className="h-auto p-0 flex items-center gap-1 text-xs text-red-600 hover:text-red-800 hover:bg-transparent disabled:text-gray-400 transition-colors ml-2"
                      title="删除该话题（本地数据库）"
                    >
                      <Trash2 className="w-3 h-3" />
                      {isDeleting ? '删除中' : '删除'}
                    </Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle className="text-red-600">确认删除该话题</AlertDialogTitle>
                      <AlertDialogDescription className="text-red-700">
                        此操作将永久删除该话题及其所有关联数据（评论、用户信息等），且不可恢复。确定要继续吗？
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>取消</AlertDialogCancel>
                      <AlertDialogAction
                        onClick={() => onDeleteTopic(topic.topic_id)}
                        className="bg-red-600 hover:bg-red-700 focus:ring-red-600"
                      >
                        确认删除
                      </AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              </div>

              {topic.imported_at && (
                <div className="text-xs text-gray-400 flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  <span>获取于: {formatImportedTime(topic.imported_at)}</span>
                </div>
              )}
            </div>
          </div>

          <div className="space-y-3 w-full overflow-hidden">
            {topic.type === 'q&a' ? (
              <div className="space-y-4">
                {(topic.question_text || topicDetail?.question?.text) && (
                  <div className="w-full max-w-full overflow-hidden" style={{ minWidth: 0 }}>
                    <div className="text-sm text-gray-600 mb-2">
                      <span className="font-medium">
                        {topicDetail?.question?.anonymous ? '匿名用户' :
                          topicDetail?.question?.owner?.name || '用户'} 提问：
                      </span>
                      {topicDetail?.question?.anonymous && topicDetail?.question?.owner_location && (
                        <span className="text-xs text-gray-400 ml-2">
                          来自 {topicDetail.question.owner_location}
                        </span>
                      )}
                    </div>

                    <div className="bg-gray-50 border-l-4 border-gray-300 pl-4 py-3 rounded-r-lg w-full max-w-full overflow-hidden" style={{ minWidth: 0 }}>
                      <div
                        className="text-sm text-gray-500 whitespace-pre-wrap break-words break-all leading-relaxed prose prose-sm max-w-none prose-p:my-1 prose-strong:text-gray-700 prose-a:text-blue-500 prose-a:align-middle"
                        style={{ wordBreak: 'break-all', overflowWrap: 'anywhere' }}
                        dangerouslySetInnerHTML={createSafeHtmlWithHighlight(topic.question_text || topicDetail?.question?.text || '', searchTerm)}
                      />
                    </div>
                  </div>
                )}

                {(topic.answer_text || topicDetail?.answer?.text) && (
                  <div className="w-full">
                    <div className="w-full max-w-full overflow-hidden" style={{ minWidth: 0 }}>
                      <div
                        className={`text-sm text-gray-800 whitespace-pre-wrap break-words break-all leading-relaxed prose prose-sm max-w-none prose-p:my-1 prose-strong:text-gray-900 prose-a:text-blue-600 ${
                          !expandedContent.has(topicId) ? 'line-clamp-8' : ''
                        }`}
                        style={{ wordBreak: 'break-all', overflowWrap: 'anywhere' }}
                        dangerouslySetInnerHTML={createSafeHtmlWithHighlight(answerText, searchTerm)}
                      />
                    </div>
                    {shouldShowAnswerToggle && (
                      <div className="text-center mt-2">
                        <button
                          type="button"
                          onClick={() => onToggleContent(topic.topic_id)}
                          className="text-xs text-blue-600 hover:text-blue-800 font-medium transition-colors"
                        >
                          {expandedContent.has(topicId) ? '收起' : '展开全部'}
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ) : (
              <div className="w-full">
                {talkText ? (
                  <div className="w-full">
                    <div className="bg-gray-50 rounded-lg p-3 w-full max-w-full overflow-hidden" style={{ minWidth: 0 }}>
                      <div
                        className={`text-sm text-gray-800 whitespace-pre-wrap break-words break-all prose prose-sm max-w-none prose-p:my-1 prose-strong:text-gray-900 prose-a:text-blue-600 ${
                          !expandedContent.has(topicId) ? 'line-clamp-8' : ''
                        }`}
                        style={{ wordBreak: 'break-all', overflowWrap: 'anywhere' }}
                        dangerouslySetInnerHTML={createSafeHtmlWithHighlight(talkText, searchTerm)}
                      />
                    </div>
                    {shouldShowTalkToggle && (
                      <div className="text-center mt-2">
                        <button
                          type="button"
                          onClick={() => onToggleContent(topic.topic_id)}
                          className="text-xs text-blue-600 hover:text-blue-800 font-medium transition-colors"
                        >
                          {expandedContent.has(topicId) ? '收起' : '展开全部'}
                        </button>
                      </div>
                    )}
                  </div>
                ) : titleText ? (
                  <div className="w-full">
                    <div className="bg-gray-50 rounded-lg p-3 w-full max-w-full overflow-hidden">
                      <div
                        className={`text-sm text-gray-800 break-words prose prose-sm max-w-none prose-p:my-1 prose-strong:text-gray-900 prose-a:text-blue-600 ${
                          !expandedContent.has(topicId) ? 'line-clamp-8' : ''
                        }`}
                        dangerouslySetInnerHTML={createSafeHtmlWithHighlight(titleText, searchTerm)}
                      />
                    </div>
                    {shouldShowTitleToggle && (
                      <div className="text-center mt-2">
                        <button
                          type="button"
                          onClick={() => onToggleContent(topic.topic_id)}
                          className="text-xs text-blue-600 hover:text-blue-800 font-medium transition-colors"
                        >
                          {expandedContent.has(topicId) ? '收起' : '展开全部'}
                        </button>
                      </div>
                    )}
                  </div>
                ) : null}
              </div>
            )}
          </div>

          {topicDetail?.talk?.article && (
            <div className="bg-blue-50 border border-blue-200 rounded-md p-2 mt-2">
              <a
                href={(topicDetail.talk.article.article_url || topicDetail.talk.article.inline_article_url) as string}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-blue-600 hover:text-blue-800 inline-flex items-center gap-1"
                title={topicDetail.talk.article.title || '查看文章'}
              >
                <ExternalLink className="w-3 h-3" />
                {topicDetail.talk.article.title || '查看文章'}
              </a>
            </div>
          )}

          {topicDetail?.talk?.images && topicDetail.talk.images.length > 0 && (
            <ImageGallery
              images={topicDetail.talk.images}
              className="w-full max-w-full"
              groupId={groupIdValue}
            />
          )}

          {topicDetail?.talk?.files && topicDetail.talk.files.length > 0 && (
            <TopicFileList
              files={topicDetail.talk.files}
              fileStatuses={fileStatuses}
              downloadingFiles={downloadingFiles}
              onGetFileStatus={onGetFileStatus}
              onDownloadFile={onDownloadFile}
            />
          )}

          <TopicComments
            topic={topic}
            topicDetail={topicDetail}
            groupId={groupId}
            searchTerm={searchTerm}
            expandedComments={expandedComments}
            fetchingComments={fetchingComments}
            onFetchMoreComments={onFetchMoreComments}
            onToggleComments={onToggleComments}
            formatDateTime={formatDateTime}
          />

          <div className="flex items-center justify-between text-sm text-gray-500 pt-2 border-t border-gray-100">
            <div className="flex items-center gap-4">
              <span className="flex items-center gap-1">
                <Heart className="w-4 h-4" />
                {topic.likes_count || 0}
              </span>
              <span className="flex items-center gap-1">
                <MessageCircle className="w-4 h-4" />
                {topic.comments_count || 0}
              </span>
            </div>
          </div>

          {topicDetail?.latest_likes && topicDetail.latest_likes.length > 0 && (
            <div className="mt-2 text-xs text-gray-500">
              <span>
                {topicDetail.latest_likes.map((like) => like.owner.name).join('、')}
                {topicDetail.latest_likes.length === 1 ? ' 觉得很赞' : ' 等人觉得很赞'}
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default memo(TopicCard);
