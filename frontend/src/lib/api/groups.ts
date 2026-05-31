import { FilesApiClient } from './files';
import type { Account, AccountSelf, FetchMoreCommentsResponse, Group, GroupStats, PaginatedResponse, Topic, TopicDetail } from './types';

export class GroupsApiClient extends FilesApiClient {
  async crawlHistorical(groupId: number, pages: number = 10, perPage: number = 20, crawlSettings?: {
    topicSource?: 'legacy' | 'official';
    crawlIntervalMin?: number;
    crawlIntervalMax?: number;
    longSleepIntervalMin?: number;
    longSleepIntervalMax?: number;
    pagesPerBatch?: number;
  }) {
    return this.request(`/api/crawl/historical/${groupId}`, {
      method: 'POST',
      body: JSON.stringify({
        pages,
        per_page: perPage,
        ...crawlSettings
      }),
    });
  }

  async crawlAll(groupId: number, crawlSettings?: {
    topicSource?: 'legacy' | 'official';
    crawlIntervalMin?: number;
    crawlIntervalMax?: number;
    longSleepIntervalMin?: number;
    longSleepIntervalMax?: number;
    pagesPerBatch?: number;
  }) {
    return this.request(`/api/crawl/all/${groupId}`, {
      method: 'POST',
      body: JSON.stringify(crawlSettings || {}),
    });
  }

  async crawlIncremental(groupId: number, pages: number = 10, perPage: number = 20, crawlSettings?: {
    topicSource?: 'legacy' | 'official';
    crawlIntervalMin?: number;
    crawlIntervalMax?: number;
    longSleepIntervalMin?: number;
    longSleepIntervalMax?: number;
    pagesPerBatch?: number;
  }) {
    return this.request(`/api/crawl/incremental/${groupId}`, {
      method: 'POST',
      body: JSON.stringify({
        pages,
        per_page: perPage,
        ...crawlSettings
      }),
    });
  }

  async crawlLatestUntilComplete(groupId: number, crawlSettings?: {
    topicSource?: 'legacy' | 'official';
    crawlIntervalMin?: number;
    crawlIntervalMax?: number;
    longSleepIntervalMin?: number;
    longSleepIntervalMax?: number;
    pagesPerBatch?: number;
  }) {
    return this.request(`/api/crawl/latest-until-complete/${groupId}`, {
      method: 'POST',
      body: JSON.stringify(crawlSettings || {}),
    });
  }

  async crawlByTimeRange(
    groupId: number,
    params: {
      startTime?: string;
      endTime?: string;
      lastDays?: number;
      perPage?: number;
      topicSource?: 'legacy' | 'official';
      crawlIntervalMin?: number;
      crawlIntervalMax?: number;
      longSleepIntervalMin?: number;
      longSleepIntervalMax?: number;
      pagesPerBatch?: number;
    }
  ) {
    return this.request(`/api/crawl/range/${groupId}`, {
      method: 'POST',
      body: JSON.stringify(params || {}),
    });
  }

  async getTopicDetail(topicId: number | string, groupId: number): Promise<TopicDetail> {
    const id = String(topicId);
    return this.request(`/api/topics/${id}/${groupId}`);
  }

  async refreshTopic(topicId: number | string, groupId: number) {
    const id = String(topicId);
    return this.request(`/api/topics/${id}/${groupId}/refresh`, {
      method: 'POST',
    });
  }

  async fetchMoreComments(topicId: number | string, groupId: number | string): Promise<FetchMoreCommentsResponse> {
    const id = String(topicId);
    return this.request(`/api/topics/${id}/${groupId}/fetch-comments`, {
      method: 'POST',
    });
  }

  async deleteSingleTopic(groupId: number | string, topicId: number | string) {
    return this.request(`/api/topics/${topicId}/${groupId}`, {
      method: 'DELETE',
    });
  }

  async fetchSingleTopic(groupId: number | string, topicId: number | string, fetchComments: boolean = false) {
    const id = String(topicId);
    const params = new URLSearchParams();
    if (fetchComments) params.append('fetch_comments', 'true');
    const url = `/api/topics/fetch-single/${groupId}/${id}${params.toString() ? '?' + params.toString() : ''}`;
    return this.request(url, { method: 'POST' });
  }

  async clearTopicDatabase(groupId: number | string) {
    return this.request(`/api/topics/clear/${groupId}`, {
      method: 'POST',
    });
  }

  async getTopics(page: number = 1, perPage: number = 20, search?: string): Promise<PaginatedResponse<Topic>> {
    const params = new URLSearchParams({
      page: page.toString(),
      per_page: perPage.toString(),
    });

    if (search) {
      params.append('search', search);
    }

    const response = await this.request<{topics: Topic[], pagination: any}>(`/api/topics?${params}`);
    return {
      data: response.topics,
      pagination: response.pagination,
    };
  }

  async refreshLocalGroups(): Promise<{ success: boolean; count: number; groups: number[]; error?: string }> {
    return this.request('/api/local-groups/refresh', {
      method: 'POST',
    });
  }

  async getGroups(): Promise<{groups: Group[], total: number}> {
    return this.request('/api/groups');
  }

  async getGroupInfo(groupId: number | string) {
    return this.request(`/api/groups/${groupId}/info`);
  }

  async getGroupTopics(groupId: number, page: number = 1, perPage: number = 20, search?: string): Promise<PaginatedResponse<Topic>> {
    const params = new URLSearchParams({
      page: page.toString(),
      per_page: perPage.toString(),
    });

    if (search) {
      params.append('search', search);
    }

    const url = `/api/groups/${groupId}/topics?${params}`;
    const response = await this.request<{topics: Topic[], pagination: any}>(url);
    return {
      data: response.topics,
      pagination: response.pagination,
    };
  }

  async getGroupStats(groupId: number): Promise<GroupStats> {
    return this.request(`/api/groups/${groupId}/stats`);
  }

  async getGroupColumnsSummary(groupId: number): Promise<{
    has_columns: boolean;
    title: string | null;
    error?: string;
  }> {
    return this.request(`/api/groups/${groupId}/columns/summary`);
  }

  async getGroupTags(groupId: number) {
    return this.request(`/api/groups/${groupId}/tags`);
  }

  async getTagTopics(groupId: number, tagId: number, page: number = 1, perPage: number = 20): Promise<PaginatedResponse<Topic>> {
    const params = new URLSearchParams({
      page: page.toString(),
      per_page: perPage.toString(),
    });

    const response = await this.request<{topics: Topic[], pagination: any}>(`/api/groups/${groupId}/tags/${tagId}/topics?${params}`);
    return {
      data: response.topics,
      pagination: response.pagination,
    };
  }

  async listAccounts(): Promise<{ accounts: Account[] }> {
    return this.request('/api/accounts');
  }

  async createAccount(params: { cookie: string; name?: string }) {
    return this.request('/api/accounts', {
      method: 'POST',
      body: JSON.stringify({
        cookie: params.cookie,
        name: params.name,
      }),
    });
  }

  async deleteAccount(accountId: string) {
    return this.request(`/api/accounts/${accountId}`, {
      method: 'DELETE',
    });
  }

  async assignGroupAccount(groupId: number | string, accountId: string) {
    return this.request(`/api/groups/${groupId}/assign-account`, {
      method: 'POST',
      body: JSON.stringify({ account_id: accountId }),
    });
  }

  async getGroupAccount(groupId: number | string): Promise<{ account: Account | null }> {
    return this.request(`/api/groups/${groupId}/account`);
  }

  async getAccountSelf(accountId: string): Promise<{ self: AccountSelf | null }> {
    return this.request(`/api/accounts/${accountId}/self`);
  }

  async refreshAccountSelf(accountId: string): Promise<{ self: AccountSelf | null }> {
    return this.request(`/api/accounts/${accountId}/self/refresh`, {
      method: 'POST',
    });
  }

  async getGroupAccountSelf(groupId: number | string): Promise<{ self: AccountSelf | null }> {
    return this.request(`/api/groups/${groupId}/self`);
  }

  async refreshGroupAccountSelf(groupId: number | string): Promise<{ self: AccountSelf | null }> {
    return this.request(`/api/groups/${groupId}/self/refresh`, {
      method: 'POST',
    });
  }

  async deleteGroup(groupId: number | string) {
    return this.request(`/api/groups/${groupId}`, {
      method: 'DELETE',
    });
  }
}
