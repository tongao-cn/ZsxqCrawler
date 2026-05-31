'use client';

import type { ReactNode, RefObject } from 'react';

import { ScrollArea } from '@/components/ui/scroll-area';
import TopicCard, { type TopicCardProps } from '@/components/TopicCard';
import TopicPagination from '@/components/TopicPagination';

interface GroupTopicsTabProps {
  contextActionPanel: ReactNode;
  currentPage: number;
  deferredSearchTerm: string;
  deletingTopics: TopicCardProps['deletingTopics'];
  downloadingFiles: TopicCardProps['downloadingFiles'];
  expandedComments: TopicCardProps['expandedComments'];
  expandedContent: TopicCardProps['expandedContent'];
  fetchingComments: TopicCardProps['fetchingComments'];
  fileStatuses: TopicCardProps['fileStatuses'];
  formatDateTime: TopicCardProps['formatDateTime'];
  formatImportedTime: TopicCardProps['formatImportedTime'];
  groupId: number;
  loadTopicDetail: NonNullable<TopicCardProps['onLoadTopicDetail']>;
  onDeleteTopic: TopicCardProps['onDeleteTopic'];
  onDownloadFile: TopicCardProps['onDownloadFile'];
  onFetchMoreComments: TopicCardProps['onFetchMoreComments'];
  onGetFileStatus: TopicCardProps['onGetFileStatus'];
  onPageChange: (page: number) => void;
  onRefreshTopic: TopicCardProps['onRefreshTopic'];
  onToggleComments: TopicCardProps['onToggleComments'];
  onToggleContent: TopicCardProps['onToggleContent'];
  refreshingTopics: TopicCardProps['refreshingTopics'];
  scrollAreaRef: RefObject<HTMLDivElement>;
  searchTerm: string;
  topicDetails: ReadonlyMap<string, TopicCardProps['topicDetail']>;
  topics: TopicCardProps['topic'][];
  topicsLoading: boolean;
  totalPages: number;
}

export default function GroupTopicsTab({
  contextActionPanel,
  currentPage,
  deferredSearchTerm,
  deletingTopics,
  downloadingFiles,
  expandedComments,
  expandedContent,
  fetchingComments,
  fileStatuses,
  formatDateTime,
  formatImportedTime,
  groupId,
  loadTopicDetail,
  onDeleteTopic,
  onDownloadFile,
  onFetchMoreComments,
  onGetFileStatus,
  onPageChange,
  onRefreshTopic,
  onToggleComments,
  onToggleContent,
  refreshingTopics,
  scrollAreaRef,
  searchTerm,
  topicDetails,
  topics,
  topicsLoading,
  totalPages,
}: GroupTopicsTabProps) {
  return (
    <div className="flex h-full min-h-0 gap-4">
      <div className="flex-1 flex flex-col min-h-0">
        {topicsLoading ? (
          <div className="flex-1 flex items-center justify-center">
            <p className="text-muted-foreground">加载中...</p>
          </div>
        ) : topics.length === 0 ? (
          <div className="flex-1 flex items-center justify-center">
            <p className="text-muted-foreground">
              {searchTerm ? '没有找到匹配的话题' : '暂无话题数据，请先进行数据采集'}
            </p>
          </div>
        ) : (
          <>
            <ScrollArea ref={scrollAreaRef} className="flex-1 w-full">
              <div className="topic-cards-container space-y-3 pr-4 max-w-full" style={{ width: '100%', maxWidth: '100%', boxSizing: 'border-box' }}>
                {topics.map((topic) => {
                  const topicId = String(topic.topic_id || '');
                  return (
                    <div key={topicId} style={{ width: '100%', maxWidth: '100%', boxSizing: 'border-box' }}>
                      <TopicCard
                        topic={topic}
                        searchTerm={deferredSearchTerm}
                        topicDetail={topicDetails.get(topicId)}
                        groupId={groupId}
                        expandedContent={expandedContent}
                        expandedComments={expandedComments}
                        refreshingTopics={refreshingTopics}
                        deletingTopics={deletingTopics}
                        fetchingComments={fetchingComments}
                        fileStatuses={fileStatuses}
                        downloadingFiles={downloadingFiles}
                        onRefreshTopic={onRefreshTopic}
                        onDeleteTopic={onDeleteTopic}
                        onToggleContent={onToggleContent}
                        onFetchMoreComments={onFetchMoreComments}
                        onToggleComments={onToggleComments}
                        onLoadTopicDetail={loadTopicDetail}
                        onGetFileStatus={onGetFileStatus}
                        onDownloadFile={onDownloadFile}
                        formatDateTime={formatDateTime}
                        formatImportedTime={formatImportedTime}
                      />
                    </div>
                  );
                })}
              </div>
            </ScrollArea>

            <TopicPagination
              currentPage={currentPage}
              totalPages={totalPages}
              onPageChange={onPageChange}
            />
          </>
        )}
      </div>
      {contextActionPanel}
    </div>
  );
}
