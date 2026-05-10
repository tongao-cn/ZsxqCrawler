import { AnalysisApiClient } from './analysis';
import type { FileAIAnalysis, FileItem, PaginatedResponse } from './types';

export class FilesApiClient extends AnalysisApiClient {
  async downloadFiles(groupId: number | string, maxFiles?: number, sortBy: string = 'download_count',
                     downloadInterval: number = 1.0, longSleepInterval: number = 60.0,
                     filesPerBatch: number = 10, downloadIntervalMin?: number,
                     downloadIntervalMax?: number, longSleepIntervalMin?: number,
                     longSleepIntervalMax?: number) {
    const requestBody: any = {
      max_files: maxFiles,
      sort_by: sortBy,
      download_interval: downloadInterval,
      long_sleep_interval: longSleepInterval,
      files_per_batch: filesPerBatch
    };

    // 如果提供了随机间隔范围参数，则添加到请求中
    if (downloadIntervalMin !== undefined) {
      requestBody.download_interval_min = downloadIntervalMin;
      requestBody.download_interval_max = downloadIntervalMax;
      requestBody.long_sleep_interval_min = longSleepIntervalMin;
      requestBody.long_sleep_interval_max = longSleepIntervalMax;
    }

    return this.request(`/api/files/download/${groupId}`, {
      method: 'POST',
      body: JSON.stringify(requestBody),
    });
  }

  async downloadFilesByTimeRange(groupId: number | string, params: {
    startTime?: string;
    endTime?: string;
    lastDays?: number;
    downloadInterval?: number;
    longSleepInterval?: number;
    filesPerBatch?: number;
    downloadIntervalMin?: number;
    downloadIntervalMax?: number;
    longSleepIntervalMin?: number;
    longSleepIntervalMax?: number;
  }) {
    const requestBody: any = {
      sort_by: 'create_time',
      start_time: params.startTime,
      end_time: params.endTime,
      last_days: params.lastDays,
      download_interval: params.downloadInterval ?? 1.0,
      long_sleep_interval: params.longSleepInterval ?? 60.0,
      files_per_batch: params.filesPerBatch ?? 10,
    };

    if (params.downloadIntervalMin !== undefined) {
      requestBody.download_interval_min = params.downloadIntervalMin;
      requestBody.download_interval_max = params.downloadIntervalMax;
      requestBody.long_sleep_interval_min = params.longSleepIntervalMin;
      requestBody.long_sleep_interval_max = params.longSleepIntervalMax;
    }

    return this.request(`/api/files/download/${groupId}`, {
      method: 'POST',
      body: JSON.stringify(requestBody),
    });
  }

  async collectFiles(groupId: number | string) {
    return this.request(`/api/files/collect/${groupId}`, {
      method: 'POST',
    });
  }

  async collectFilesByTimeRange(groupId: number | string, params: {
    startTime?: string;
    endTime?: string;
    lastDays?: number;
  }) {
    return this.request(`/api/files/collect/${groupId}`, {
      method: 'POST',
      body: JSON.stringify({
        start_time: params.startTime,
        end_time: params.endTime,
        last_days: params.lastDays,
      }),
    });
  }

  async clearFileDatabase(groupId: number | string) {
    return this.request(`/api/files/clear/${groupId}`, {
      method: 'POST',
    });
  }

  async getFileStats(groupId: number | string) {
    return this.request(`/api/files/stats/${groupId}`);
  }

  async syncFilesFromTopics(groupId: number | string): Promise<{
    success: boolean;
    group_id: string;
    stats: {
      scanned: number;
      new_files: number;
      relations: number;
      topic_files: number;
    };
  }> {
    return this.request(`/api/files/sync-from-topics/${groupId}`, {
      method: 'POST',
    });
  }

  async downloadSingleFile(groupId: string, fileId: number, fileName?: string, fileSize?: number) {
    const params = new URLSearchParams();
    if (fileName) params.append('file_name', fileName);
    if (fileSize !== undefined) params.append('file_size', fileSize.toString());

    const url = `/api/files/download-single/${groupId}/${fileId}${params.toString() ? '?' + params.toString() : ''}`;
    return this.request(url, {
      method: 'POST',
    });
  }

  async getFileStatus(groupId: string, fileId: number) {
    return this.request(`/api/files/status/${groupId}/${fileId}`);
  }

  async checkLocalFileStatus(groupId: string, fileName: string, fileSize: number) {
    const params = new URLSearchParams({
      file_name: fileName,
      file_size: fileSize.toString(),
    });
    return this.request(`/api/files/check-local/${groupId}?${params}`);
  }

  async getFiles(groupId: number, page: number = 1, perPage: number = 20, status?: string, search?: string): Promise<PaginatedResponse<FileItem>> {
    const params = new URLSearchParams({
      page: page.toString(),
      per_page: perPage.toString(),
    });

    if (status) {
      params.append('status', status);
    }

    if (search) {
      params.append('search', search);
    }

    const response = await this.request<{files: FileItem[], pagination: any}>(`/api/files/${groupId}?${params}`);
    return {
      data: response.files,
      pagination: response.pagination,
    };
  }

  async getFileAIAnalysis(groupId: number | string, fileId: number): Promise<{ analysis: FileAIAnalysis | null }> {
    return this.request(`/api/files/analysis/${groupId}/${fileId}`);
  }

  async analyzeFile(groupId: number | string, fileId: number, force: boolean = false): Promise<{ analysis: FileAIAnalysis }> {
    return this.request(`/api/files/analysis/${groupId}/${fileId}`, {
      method: 'POST',
      body: JSON.stringify({ force }),
    });
  }
}
