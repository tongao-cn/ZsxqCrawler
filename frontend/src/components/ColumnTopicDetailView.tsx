'use client';

import Image from 'next/image';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import ImageGallery from '@/components/ImageGallery';
import SafeImage from '@/components/SafeImage';
import { apiClient, ColumnTopicDetail } from '@/lib/api';
import { formatColumnDuration, formatColumnFileSize, formatColumnTime } from '@/lib/column-formatters';
import { createSafeHtml } from '@/lib/zsxq-content-renderer';
import { BookOpen, Clock, File, FileImage, Heart, MessageCircle, Play, RefreshCw, Users } from 'lucide-react';

interface ColumnTopicDetailViewProps {
  groupId: string;
  selectedTopic: ColumnTopicDetail | null;
  detailLoading: boolean;
  loadingComments: boolean;
  onFetchMoreComments: () => void;
}

function countVisibleComments(topic: ColumnTopicDetail): number {
  let total = 0;
  topic.comments?.forEach(comment => {
    total += 1;
    if (comment.replied_comments) {
      total += comment.replied_comments.length;
    }
  });
  return total;
}

export default function ColumnTopicDetailView({
  groupId,
  selectedTopic,
  detailLoading,
  loadingComments,
  onFetchMoreComments,
}: ColumnTopicDetailViewProps) {
  if (detailLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-gray-500">加载中...</div>
      </div>
    );
  }

  if (!selectedTopic) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center text-gray-400">
          <BookOpen className="h-12 w-12 mx-auto mb-4 opacity-50" />
          <p>选择一篇文章查看详情</p>
        </div>
      </div>
    );
  }

  const visibleComments = countVisibleComments(selectedTopic);

  return (
    <ScrollArea className="h-full">
      <div className="p-6 max-w-3xl mx-auto">
        <h1 className="text-2xl font-bold text-gray-900 mb-4">
          {selectedTopic.title || '无标题'}
        </h1>

        <div className="flex items-center gap-4 mb-6 pb-4 border-b border-gray-200">
          {selectedTopic.owner && (
            <div className="flex items-center gap-2">
              <SafeImage
                src={apiClient.getProxyImageUrl(selectedTopic.owner.avatar_url || '', groupId)}
                alt={selectedTopic.owner.name}
                className="w-8 h-8 rounded-full object-cover"
                fallbackClassName="w-8 h-8 rounded-full"
                fallbackText={selectedTopic.owner.name.slice(0, 1)}
              />
              <span className="text-sm font-medium text-gray-700">
                {selectedTopic.owner.name}
              </span>
            </div>
          )}
          <div className="flex items-center gap-4 text-sm text-gray-500">
            <span className="flex items-center gap-1">
              <Clock className="h-4 w-4" />
              {formatColumnTime(selectedTopic.create_time)}
            </span>
            <span className="flex items-center gap-1">
              <Heart className="h-4 w-4" />
              {selectedTopic.likes_count}
            </span>
            <span className="flex items-center gap-1">
              <MessageCircle className="h-4 w-4" />
              {selectedTopic.comments_count}
            </span>
            <span className="flex items-center gap-1">
              <Users className="h-4 w-4" />
              {selectedTopic.readers_count}
            </span>
          </div>
        </div>

        {selectedTopic.type === 'q&a' && selectedTopic.question && (
          <div className="mb-6 space-y-4">
            <div className="w-full max-w-full overflow-hidden">
              <div className="text-sm text-gray-600 mb-2">
                <span className="font-medium">
                  {selectedTopic.question.owner?.name || '用户'} 提问：
                </span>
              </div>

              <div className="bg-gray-50 border-l-4 border-gray-300 pl-4 py-3 rounded-r-lg w-full max-w-full overflow-hidden">
                {selectedTopic.question.text && (
                  <div
                    className="text-sm text-gray-500 whitespace-pre-wrap break-words leading-relaxed prose prose-sm max-w-none prose-p:my-1 prose-a:text-blue-500"
                    dangerouslySetInnerHTML={createSafeHtml(selectedTopic.question.text)}
                  />
                )}
                {selectedTopic.question.images && selectedTopic.question.images.length > 0 && (
                  <div className="mt-3">
                    <ImageGallery
                      images={selectedTopic.question.images}
                      size="small"
                      groupId={groupId}
                    />
                  </div>
                )}
              </div>
            </div>

            {selectedTopic.answer && selectedTopic.answer.text && (
              <div className="w-full max-w-full overflow-hidden">
                <div
                  className="text-sm text-gray-800 whitespace-pre-wrap break-words leading-relaxed prose prose-sm max-w-none prose-p:my-1 prose-strong:text-gray-900 prose-a:text-blue-600"
                  dangerouslySetInnerHTML={createSafeHtml(selectedTopic.answer.text)}
                />
                {selectedTopic.answer.images && selectedTopic.answer.images.length > 0 && (
                  <div className="mt-3">
                    <ImageGallery
                      images={selectedTopic.answer.images}
                      size="small"
                      groupId={groupId}
                    />
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {selectedTopic.full_text && selectedTopic.type !== 'q&a' && (
          <div
            className="prose prose-gray max-w-none mb-6"
            dangerouslySetInnerHTML={createSafeHtml(selectedTopic.full_text)}
          />
        )}

        {selectedTopic.images && selectedTopic.images.length > 0 && (
          <div className="mb-6">
            <h3 className="text-lg font-semibold text-gray-800 mb-3 flex items-center gap-2">
              <FileImage className="h-5 w-5" />
              图片 ({selectedTopic.images.length})
            </h3>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              {selectedTopic.images.map((image) => (
                <a
                  key={image.image_id}
                  href={apiClient.getProxyImageUrl(image.original?.url || '', groupId)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block aspect-video rounded-lg overflow-hidden bg-gray-100 hover:opacity-80 transition-opacity"
                >
                  <Image
                    src={apiClient.getProxyImageUrl(image.large?.url || image.thumbnail?.url || '', groupId)}
                    alt=""
                    width={320}
                    height={180}
                    sizes="(min-width: 768px) 33vw, 50vw"
                    unoptimized
                    className="w-full h-full object-cover"
                    loading="lazy"
                  />
                </a>
              ))}
            </div>
          </div>
        )}

        {selectedTopic.files && selectedTopic.files.length > 0 && (
          <div className="mb-6">
            <h3 className="text-lg font-semibold text-gray-800 mb-3 flex items-center gap-2">
              <File className="h-5 w-5" />
              文件 ({selectedTopic.files.length})
            </h3>
            <div className="space-y-2">
              {selectedTopic.files.map((file) => (
                <div
                  key={file.file_id}
                  className={`flex items-center gap-3 p-3 rounded-lg border ${
                    file.download_status === 'completed'
                      ? 'bg-green-50 border-green-200'
                      : 'bg-gray-50 border-gray-200'
                  }`}
                >
                  <File className="h-5 w-5 text-gray-500 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-gray-900 truncate">
                      {file.name}
                    </div>
                    <div className="text-xs text-gray-500">
                      {formatColumnFileSize(file.size)}
                      {file.download_status === 'completed' && (
                        <span className="text-green-600 ml-2">✓ 已下载</span>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {selectedTopic.videos && selectedTopic.videos.length > 0 && (
          <div className="mb-6">
            <h3 className="text-lg font-semibold text-gray-800 mb-3 flex items-center gap-2">
              <Play className="h-5 w-5" />
              视频 ({selectedTopic.videos.length})
            </h3>
            <div className="space-y-3">
              {selectedTopic.videos.map((video) => (
                <div
                  key={video.video_id}
                  className={`rounded-lg border overflow-hidden ${
                    video.download_status === 'completed'
                      ? 'border-green-200 bg-green-50'
                      : 'border-gray-200 bg-gray-50'
                  }`}
                >
                  <div className="relative aspect-video bg-black">
                    {video.download_status === 'completed' && video.local_path ? (
                      <video
                        controls
                        className="w-full h-full"
                        poster={video.cover?.local_path
                          ? apiClient.getLocalImageUrl(groupId, video.cover.local_path)
                          : video.cover?.url
                            ? apiClient.getProxyImageUrl(video.cover.url, groupId)
                            : undefined
                        }
                      >
                        <source
                          src={apiClient.getLocalVideoUrl(groupId, `video_${video.video_id}.mp4`)}
                          type="video/mp4"
                        />
                        Your browser does not support the video tag.
                      </video>
                    ) : (
                      <>
                        {video.cover?.url && (
                          <Image
                            src={video.cover.local_path
                              ? apiClient.getLocalImageUrl(groupId, video.cover.local_path)
                              : apiClient.getProxyImageUrl(video.cover.url, groupId)
                            }
                            alt="视频封面"
                            width={640}
                            height={360}
                            sizes="100vw"
                            unoptimized
                            className="w-full h-full object-contain"
                          />
                        )}
                        <div className="absolute inset-0 flex items-center justify-center">
                          <div className="text-center">
                            <div className="w-16 h-16 mx-auto rounded-full bg-black/50 flex items-center justify-center mb-2">
                              <Play className="h-8 w-8 text-white/50 ml-1" fill="white" fillOpacity={0.5} />
                            </div>
                            <span className="text-white/80 text-sm bg-black/50 px-3 py-1 rounded">
                              {video.download_status === 'pending' && '等待下载'}
                              {video.download_status === 'pending_manual' && '需手动下载'}
                              {video.download_status === 'failed' && '下载失败'}
                              {video.download_status === 'downloading' && '下载中...'}
                              {!video.download_status && '未下载'}
                            </span>
                          </div>
                        </div>
                      </>
                    )}
                  </div>
                  <div className="p-3">
                    <div className="flex items-center gap-4 text-sm text-gray-600">
                      <span>大小: {formatColumnFileSize(video.size)}</span>
                      <span>时长: {formatColumnDuration(video.duration)}</span>
                      <span className={
                        video.download_status === 'completed' ? 'text-green-600' :
                        video.download_status === 'pending_manual' ? 'text-yellow-600' :
                        video.download_status === 'failed' ? 'text-red-600' :
                        'text-gray-500'
                      }>
                        {video.download_status === 'completed' && '✓ 已下载，可播放'}
                        {video.download_status === 'pending' && '待下载'}
                        {video.download_status === 'pending_manual' && '需手动下载'}
                        {video.download_status === 'failed' && '下载失败'}
                        {video.download_status === 'downloading' && '下载中...'}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {(selectedTopic.comments && selectedTopic.comments.length > 0) || selectedTopic.comments_count > 0 ? (
          <div>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-lg font-semibold text-gray-800 flex items-center gap-2">
                <MessageCircle className="h-5 w-5" />
                评论 ({visibleComments}/{selectedTopic.comments_count})
              </h3>
              {selectedTopic.comments_count > visibleComments && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={onFetchMoreComments}
                  disabled={loadingComments}
                  className="text-xs"
                >
                  <RefreshCw className={`h-3 w-3 mr-1 ${loadingComments ? 'animate-spin' : ''}`} />
                  {loadingComments ? '获取中...' : '获取完整评论'}
                </Button>
              )}
            </div>
            <div className="space-y-2">
              {selectedTopic.comments?.map((comment) => (
                <div key={comment.comment_id} className="bg-gray-50 rounded-lg p-2">
                  <div className="flex items-center gap-2 mb-1">
                    {comment.owner && (
                      <SafeImage
                        src={apiClient.getProxyImageUrl(comment.owner.avatar_url || '', groupId)}
                        alt={comment.owner.name}
                        className="w-4 h-4 rounded-full object-cover block"
                        fallbackClassName="w-4 h-4 rounded-full"
                        fallbackText={comment.owner.name.slice(0, 1)}
                      />
                    )}
                    <span className="text-xs font-medium text-gray-700">
                      {comment.owner?.name || '未知用户'}
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
                      {formatColumnTime(comment.create_time)}
                    </span>
                  </div>
                  <div
                    className="text-xs text-gray-600 ml-6 break-words prose prose-xs max-w-none prose-a:text-blue-600"
                    dangerouslySetInnerHTML={createSafeHtml(comment.text || '')}
                  />

                  {comment.images && comment.images.length > 0 && (
                    <div className="ml-6 mt-2">
                      <ImageGallery
                        images={comment.images}
                        className="comment-images"
                        size="small"
                        groupId={groupId}
                      />
                    </div>
                  )}

                  {comment.replied_comments && comment.replied_comments.length > 0 && (
                    <div className="ml-6 mt-2 space-y-2 border-l-2 border-gray-200 pl-3">
                      {comment.replied_comments.map((reply) => (
                        <div key={reply.comment_id} className="bg-white rounded p-2">
                          <div className="flex items-center gap-2 mb-1">
                            {reply.owner && (
                              <SafeImage
                                src={apiClient.getProxyImageUrl(reply.owner.avatar_url || '', groupId)}
                                alt={reply.owner.name}
                                className="w-3 h-3 rounded-full object-cover block"
                                fallbackClassName="w-3 h-3 rounded-full"
                                fallbackText={reply.owner.name.slice(0, 1)}
                              />
                            )}
                            <span className="text-xs font-medium text-gray-600">
                              {reply.owner?.name || '未知用户'}
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
                              {formatColumnTime(reply.create_time)}
                            </span>
                          </div>
                          <div
                            className="text-xs text-gray-500 ml-5 break-words prose prose-xs max-w-none prose-a:text-blue-600"
                            dangerouslySetInnerHTML={createSafeHtml(reply.text || '')}
                          />
                          {reply.images && reply.images.length > 0 && (
                            <div className="ml-5 mt-1">
                              <ImageGallery
                                images={reply.images}
                                className="reply-images"
                                size="small"
                                groupId={groupId}
                              />
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </ScrollArea>
  );
}
