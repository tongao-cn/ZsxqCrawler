import { CoreApiClient } from './core';
import type { Task } from './taskTypes';

export class TasksApiClient extends CoreApiClient {
  async getTasks(groupId?: string | number | null, taskType?: string): Promise<Task[]> {
    const params = new URLSearchParams();
    if (groupId !== undefined && groupId !== null) {
      params.append('group_id', String(groupId));
    }
    if (taskType) {
      params.append('type', taskType);
    }
    const query = params.toString();
    return this.request(`/api/tasks${query ? `?${query}` : ''}`);
  }

  async getTask(taskId: string): Promise<Task> {
    return this.request(`/api/tasks/${taskId}`);
  }

  async stopTask(taskId: string) {
    return this.request(`/api/tasks/${taskId}/stop`, {
      method: 'POST',
    });
  }
}
