import { GroupsApiClient } from './groups';
import type { ColumnComment, ColumnInfo, ColumnTopic, ColumnTopicDetail, ColumnsFetchSettings, ColumnsStats } from './columnTypes';

export class ColumnsApiClient extends GroupsApiClient {
  async getGroupColumns(groupId: number | string): Promise<{
    columns: ColumnInfo[];
    stats: ColumnsStats;
  }> {
    return this.request(`/api/groups/${groupId}/columns`);
  }

  // 获取专栏下的文章列表
  async getColumnTopics(groupId: number | string, columnId: number): Promise<{
    column: ColumnInfo;
    topics: ColumnTopic[];
  }> {
    return this.request(`/api/groups/${groupId}/columns/${columnId}/topics`);
  }

  // 获取专栏文章详情
  async getColumnTopicDetail(groupId: number | string, topicId: number): Promise<ColumnTopicDetail> {
    return this.request(`/api/groups/${groupId}/columns/topics/${topicId}`);
  }

  // 获取专栏文章完整评论
  async getColumnTopicFullComments(groupId: number | string, topicId: number): Promise<{
    success: boolean;
    comments: ColumnComment[];
    total: number;
  }> {
    return this.request(`/api/groups/${groupId}/columns/topics/${topicId}/comments`);
  }

  // 采集群组所有专栏内容
  async fetchGroupColumns(groupId: number | string, settings?: ColumnsFetchSettings): Promise<{
    success: boolean;
    task_id: string;
    message: string;
  }> {
    return this.request(`/api/groups/${groupId}/columns/fetch`, {
      method: 'POST',
      body: JSON.stringify(settings || {}),
    });
  }

  // 获取专栏统计信息
  async getColumnsStats(groupId: number | string): Promise<ColumnsStats> {
    return this.request(`/api/groups/${groupId}/columns/stats`);
  }

  // 删除群组所有专栏数据
  async deleteAllColumns(groupId: number | string): Promise<{
    success: boolean;
    message: string;
    deleted: {
      columns_deleted: number;
      topics_deleted: number;
      details_deleted: number;
      images_deleted: number;
      files_deleted: number;
      videos_deleted: number;
      comments_deleted: number;
    };
  }> {
    return this.request(`/api/groups/${groupId}/columns/all`, {
      method: 'DELETE',
    });
  }
}
