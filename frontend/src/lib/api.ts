/**
 * API客户端 - 与后端FastAPI服务通信
 */

export * from './api/client';
export * from './api/types';

import { API_BASE_URL } from './api/client';
import { ColumnsApiClient } from './api/columns';

class ApiClient extends ColumnsApiClient {
  constructor(baseUrl: string = API_BASE_URL) {
    super(baseUrl);
  }
}

export const apiClient = new ApiClient();
export default apiClient;
