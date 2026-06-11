import { API_BASE_URL, ApiClientBase } from './client';
import type { DatabaseStats } from './coreTypes';

export class CoreApiClient extends ApiClientBase {
  async healthCheck() {
    return this.request('/api/health');
  }

  async getConfig() {
    return this.request('/api/config');
  }

  async updateConfig(config: { cookie: string }) {
    return this.request('/api/config', {
      method: 'POST',
      body: JSON.stringify(config),
    });
  }

  async getDatabaseStats(): Promise<DatabaseStats> {
    return this.request('/api/database/stats');
  }

  getProxyImageUrl(originalUrl: string, groupId?: string | number): string {
    if (!originalUrl) return '';
    const params = new URLSearchParams({ url: originalUrl });
    if (groupId !== undefined && groupId !== null && groupId !== '') {
      params.append('group_id', String(groupId));
    }
    return `${API_BASE_URL}/api/proxy-image?${params.toString()}`;
  }

  getLocalImageUrl(groupId: string, localPath: string): string {
    if (!localPath) return '';
    return `${API_BASE_URL}/api/groups/${groupId}/images/${encodeURIComponent(localPath)}`;
  }

  getLocalVideoUrl(groupId: string, videoFilename: string): string {
    if (!videoFilename) return '';
    return `${API_BASE_URL}/api/groups/${groupId}/videos/${encodeURIComponent(videoFilename)}`;
  }

  async getImageCacheInfo(groupId: string) {
    return this.request(`/api/cache/images/info/${groupId}`);
  }

  async clearImageCache(groupId: string) {
    return this.request(`/api/cache/images/${groupId}`, {
      method: 'DELETE',
    });
  }

  async getCrawlerSettings() {
    return this.request('/api/settings/crawler');
  }

  async updateCrawlerSettings(settings: {
    min_delay: number;
    max_delay: number;
    long_delay_interval: number;
    timestamp_offset_ms: number;
    debug_mode: boolean;
  }) {
    return this.request('/api/settings/crawler', {
      method: 'POST',
      body: JSON.stringify(settings),
    });
  }

  async getDownloaderSettings() {
    return this.request('/api/settings/downloader');
  }

  async updateDownloaderSettings(settings: {
    download_interval_min: number;
    download_interval_max: number;
    long_delay_interval: number;
    long_delay_min: number;
    long_delay_max: number;
  }) {
    return this.request('/api/settings/downloader', {
      method: 'POST',
      body: JSON.stringify(settings),
    });
  }

  async getCrawlSettings() {
    return this.request('/api/settings/crawl');
  }

  async updateCrawlSettings(settings: {
    crawl_interval_min: number;
    crawl_interval_max: number;
    long_sleep_interval_min: number;
    long_sleep_interval_max: number;
    pages_per_batch: number;
  }) {
    return this.request('/api/settings/crawl', {
      method: 'POST',
      body: JSON.stringify(settings),
    });
  }
}
