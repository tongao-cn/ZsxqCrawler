import { CoreApiClient } from './core';
import type { Task } from './types';

export class TasksApiClient extends CoreApiClient {
  async getTasks(): Promise<Task[]> {
    return this.request('/api/tasks');
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
