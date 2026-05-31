'use client';

import { useCallback, useEffect, useState } from 'react';
import { DatabaseZap, Download, Loader2, ListChecks, RefreshCw, Sparkles } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { apiClient, Topic, FileItem, FileAIAnalysis, PaginatedResponse, Group, Task } from '@/lib/api';
import { useTaskStatus } from '@/hooks/useTaskStatus';
import { toast } from 'sonner';

interface DataPanelProps {
  selectedGroup?: Group | null;
}

interface FileTaskState {
  taskId: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  message: string;
}

interface FileDownloadTaskWatcherProps {
  fileIds: number[];
  onStatus: (taskId: string, fileIds: number[], task: Pick<Task, 'status' | 'message'>) => void;
  onTerminal: (taskId: string, fileIds: number[], task: Pick<Task, 'status' | 'message'>) => void | Promise<void>;
  taskId: string;
}

function FileDownloadTaskWatcher({
  fileIds,
  onStatus,
  onTerminal,
  taskId,
}: FileDownloadTaskWatcherProps) {
  useTaskStatus(taskId, {
    onStatus: (task) => onStatus(taskId, fileIds, task),
    onTerminal: (task) => onTerminal(taskId, fileIds, task),
  });

  return null;
}

export default function DataPanel({ selectedGroup }: DataPanelProps) {
  const [topicsData, setTopicsData] = useState<PaginatedResponse<Topic> | null>(null);
  const [filesData, setFilesData] = useState<PaginatedResponse<FileItem> | null>(null);
  const [loading, setLoading] = useState(false);

  const selectedGroupId = selectedGroup?.group_id;
  
  // 话题查询参数
  const [topicsPage, setTopicsPage] = useState(1);
  const [topicsSearch, setTopicsSearch] = useState('');
  const [topicsSearchQuery, setTopicsSearchQuery] = useState('');
  
  // 文件查询参数
  const [filesPage, setFilesPage] = useState(1);
  const [filesStatus, setFilesStatus] = useState<string>('all');
  const [filesSearch, setFilesSearch] = useState('');
  const [filesSearchQuery, setFilesSearchQuery] = useState('');
  const [syncingFiles, setSyncingFiles] = useState(false);
  const [downloadingFiles, setDownloadingFiles] = useState<Set<number>>(new Set());
  const [selectedFileIds, setSelectedFileIds] = useState<Set<number>>(new Set());
  const [fileTasks, setFileTasks] = useState<Map<number, FileTaskState>>(new Map());
  const [activeFileDownloadTasks, setActiveFileDownloadTasks] = useState<Map<string, number[]>>(new Map());
  const [analysisOpen, setAnalysisOpen] = useState(false);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [selectedFile, setSelectedFile] = useState<FileItem | null>(null);
  const [analysis, setAnalysis] = useState<FileAIAnalysis | null>(null);

  useEffect(() => {
    setTopicsPage(1);
    setFilesPage(1);
    setSelectedFileIds(new Set());
    setDownloadingFiles(new Set());
    setFileTasks(new Map());
    setActiveFileDownloadTasks(new Map());
  }, [selectedGroupId]);

  useEffect(() => {
    const loadTopics = async () => {
      try {
        setLoading(true);
        let data;
        if (selectedGroupId !== undefined) {
          data = await apiClient.getGroupTopics(selectedGroupId, topicsPage, 20, topicsSearchQuery || undefined);
        } else {
          data = await apiClient.getTopics(topicsPage, 20, topicsSearchQuery || undefined);
        }
        setTopicsData(data);
      } catch (error) {
        console.error('加载话题数据失败:', error);
      } finally {
        setLoading(false);
      }
    };

    loadTopics();
  }, [selectedGroupId, topicsPage, topicsSearchQuery]);

  const loadFiles = useCallback(async () => {
    if (selectedGroupId === undefined) {
      setFilesData(null);
      return;
    }

    try {
      setLoading(true);
      const status = filesStatus === 'all' ? undefined : filesStatus;
      const data = await apiClient.getFiles(selectedGroupId, filesPage, 20, status, filesSearchQuery || undefined);
      setFilesData(data);
    } catch (error) {
      console.error('加载文件数据失败:', error);
    } finally {
      setLoading(false);
    }
  }, [filesPage, filesSearchQuery, filesStatus, selectedGroupId]);

  useEffect(() => {
    void loadFiles();
  }, [loadFiles]);

  const handleTopicsSearch = () => {
    setTopicsPage(1);
    setTopicsSearchQuery(topicsSearch.trim());
  };

  const handleFilesStatusChange = (value: string) => {
    setFilesPage(1);
    setFilesStatus(value);
  };

  const handleFilesSearch = () => {
    setFilesPage(1);
    setFilesSearchQuery(filesSearch.trim());
  };

  const isFileDownloaded = (file: FileItem) =>
    Boolean(file.local_exists || file.local_path || ['completed', 'downloaded', 'skipped'].includes(file.download_status));

  const filesOnPage = filesData?.data || [];
  const selectableFilesOnPage = filesOnPage.filter((file) =>
    !isFileDownloaded(file) && !downloadingFiles.has(file.file_id)
  );
  const selectedDownloadableFiles = selectableFilesOnPage.filter((file) => selectedFileIds.has(file.file_id));
  const allSelectableFilesChecked = selectableFilesOnPage.length > 0
    && selectableFilesOnPage.every((file) => selectedFileIds.has(file.file_id));

  const toggleFileSelection = (fileId: number, checked: boolean) => {
    setSelectedFileIds(prev => {
      const next = new Set(prev);
      if (checked) {
        next.add(fileId);
      } else {
        next.delete(fileId);
      }
      return next;
    });
  };

  const toggleSelectableFilesOnPage = (checked: boolean) => {
    setSelectedFileIds(prev => {
      const next = new Set(prev);
      for (const file of selectableFilesOnPage) {
        if (checked) {
          next.add(file.file_id);
        } else {
          next.delete(file.file_id);
        }
      }
      return next;
    });
  };

  const setFileTaskStatus = useCallback((taskId: string, fileIds: number[], task: Pick<Task, 'status' | 'message'>) => {
    setFileTasks(prev => {
      const next = new Map(prev);
      fileIds.forEach((fileId) => {
        next.set(fileId, {
          taskId,
          status: task.status,
          message: task.message,
        });
      });
      return next;
    });
  }, []);

  const registerFileDownloadTask = useCallback((taskId: string, fileIds: number[]) => {
    setActiveFileDownloadTasks(prev => {
      const next = new Map(prev);
      next.set(taskId, fileIds);
      return next;
    });
  }, []);

  const handleFileDownloadTerminal = useCallback(async (
    taskId: string,
    fileIds: number[],
    task: Pick<Task, 'status' | 'message'>,
  ) => {
    setFileTaskStatus(taskId, fileIds, task);
    setDownloadingFiles(prev => {
      const next = new Set(prev);
      fileIds.forEach((fileId) => next.delete(fileId));
      return next;
    });
    setActiveFileDownloadTasks(prev => {
      const next = new Map(prev);
      next.delete(taskId);
      return next;
    });
    await loadFiles();
  }, [loadFiles, setFileTaskStatus]);

  const handleSyncFilesFromTopics = async () => {
    if (selectedGroupId === undefined || syncingFiles) {
      return;
    }

    try {
      setSyncingFiles(true);
      const result = await apiClient.syncFilesFromTopics(selectedGroupId);
      toast.success(`文件记录同步任务已创建: ${result.task_id}`);
    } catch (error) {
      toast.error(`同步文件记录失败: ${error instanceof Error ? error.message : '未知错误'}`);
    } finally {
      setSyncingFiles(false);
    }
  };

  const handleDownloadFile = async (file: FileItem) => {
    if (selectedGroupId === undefined || downloadingFiles.has(file.file_id)) {
      return;
    }

    try {
      setDownloadingFiles(prev => new Set(prev).add(file.file_id));
      const response = await apiClient.downloadSingleFile(
        String(selectedGroupId),
        file.file_id,
        file.name,
        file.size,
      ) as { task_id?: string };
      toast.success(response.task_id ? `文件下载任务已创建: ${response.task_id}` : '文件下载任务已创建');

      if (response.task_id) {
        setFileTasks(prev => {
          const next = new Map(prev);
          next.set(file.file_id, {
            taskId: response.task_id || '',
            status: 'pending',
            message: '下载任务已创建',
          });
          return next;
        });
        registerFileDownloadTask(response.task_id, [file.file_id]);
      } else {
        await loadFiles();
        setDownloadingFiles(prev => {
          const next = new Set(prev);
          next.delete(file.file_id);
          return next;
        });
      }
    } catch (error) {
      toast.error(`文件下载失败: ${error instanceof Error ? error.message : '未知错误'}`);
      setDownloadingFiles(prev => {
        const next = new Set(prev);
        next.delete(file.file_id);
        return next;
      });
    }
  };

  const handleBatchDownloadSelected = async () => {
    if (selectedGroupId === undefined || selectedDownloadableFiles.length === 0) {
      return;
    }

    const filesToDownload = selectedDownloadableFiles.slice();
    const fileIds = filesToDownload.map((file) => file.file_id);
    try {
      setDownloadingFiles(prev => {
        const next = new Set(prev);
        fileIds.forEach((fileId) => next.add(fileId));
        return next;
      });
      const response = await apiClient.downloadSelectedFiles(selectedGroupId, fileIds);
      setFileTasks(prev => {
        const next = new Map(prev);
        fileIds.forEach((fileId) => {
          next.set(fileId, {
            taskId: response.task_id,
            status: 'pending',
            message: '下载任务已创建',
          });
        });
        return next;
      });
      registerFileDownloadTask(response.task_id, fileIds);
      toast.success(`选中文件下载任务已创建: ${response.task_id}`);
    } catch (error) {
      toast.error(`选中文件下载任务创建失败: ${error instanceof Error ? error.message : '未知错误'}`);
      setDownloadingFiles(prev => {
        const next = new Set(prev);
        fileIds.forEach((fileId) => next.delete(fileId));
        return next;
      });
    }

    setSelectedFileIds(prev => {
      const next = new Set(prev);
      for (const file of filesToDownload) {
        next.delete(file.file_id);
      }
      return next;
    });
  };

  const openAnalysisDialog = async (file: FileItem, force: boolean = false) => {
    if (selectedGroupId === undefined) {
      return;
    }

    try {
      setSelectedFile(file);
      setAnalysis(null);
      setAnalysisOpen(true);
      setAnalysisLoading(true);

      if (!force && file.has_ai_analysis) {
        const cached = await apiClient.getFileAIAnalysis(selectedGroupId, file.file_id);
        if (cached.analysis) {
          setAnalysis(cached.analysis);
          setAnalysisLoading(false);
          return;
        }
      }

      const result = await apiClient.analyzeFile(selectedGroupId, file.file_id, force);
      setAnalysis(result.analysis);
      toast.success(force ? '文件已重新分析' : '文件分析完成');
      await loadFiles();
    } catch (error) {
      toast.error(`文件 AI 分析失败: ${error instanceof Error ? error.message : '未知错误'}`);
      setAnalysis({
        file_id: file.file_id,
        status: 'failed',
        error_message: error instanceof Error ? error.message : '未知错误',
      });
    } finally {
      setAnalysisLoading(false);
    }
  };

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const formatDate = (dateString: string) => {
    if (!dateString) return '-';
    return new Date(dateString).toLocaleString('zh-CN');
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'completed':
      case 'downloaded':
        return <Badge className="bg-green-100 text-green-800">已完成</Badge>;
      case 'pending':
        return <Badge className="bg-yellow-100 text-yellow-800">未下载</Badge>;
      case 'skipped':
        return <Badge className="bg-slate-100 text-slate-800">已存在</Badge>;
      case 'failed':
        return <Badge className="bg-red-100 text-red-800">失败</Badge>;
      default:
        return <Badge variant="secondary">{status}</Badge>;
    }
  };

  const getAnalysisTextLabel = (contentType?: string | null) =>
    contentType?.startsWith('audio/') ? '转录原文' : '提取原文';

  return (
    <>
      {Array.from(activeFileDownloadTasks.entries()).map(([taskId, fileIds]) => (
        <FileDownloadTaskWatcher
          key={taskId}
          taskId={taskId}
          fileIds={fileIds}
          onStatus={setFileTaskStatus}
          onTerminal={handleFileDownloadTerminal}
        />
      ))}
      <Tabs defaultValue="topics" className="space-y-4">
      <TabsList className="grid w-full grid-cols-2">
        <TabsTrigger value="topics">话题数据</TabsTrigger>
        <TabsTrigger value="files">文件数据</TabsTrigger>
      </TabsList>

      <TabsContent value="topics">
        <Card className="border border-gray-200 shadow-none">
          <CardHeader>
            <CardTitle>
              {selectedGroup ? `${selectedGroup.name} - 话题列表` : '话题列表'}
            </CardTitle>
            <CardDescription>
              {selectedGroup
                ? `查看 ${selectedGroup.name} 群组的话题数据`
                : '查看已采集的话题数据'
              }
            </CardDescription>
          </CardHeader>
          <CardContent>
            {/* 搜索栏 */}
            <div className="flex gap-2 mb-4">
              <Input
                placeholder="搜索话题标题..."
                value={topicsSearch}
                onChange={(e) => setTopicsSearch(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && handleTopicsSearch()}
              />
              <Button onClick={handleTopicsSearch} disabled={loading}>
                搜索
              </Button>
            </div>

            {/* 话题表格 */}
            {topicsData && (
              <>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>标题</TableHead>
                      <TableHead>创建时间</TableHead>
                      <TableHead>点赞数</TableHead>
                      <TableHead>评论数</TableHead>
                      <TableHead>阅读数</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {topicsData.data.map((topic) => (
                      <TableRow key={topic.topic_id}>
                        <TableCell className="max-w-md">
                          <div className="truncate" title={topic.title}>
                            {topic.title || '无标题'}
                          </div>
                        </TableCell>
                        <TableCell>{formatDate(topic.create_time)}</TableCell>
                        <TableCell>{topic.likes_count}</TableCell>
                        <TableCell>{topic.comments_count}</TableCell>
                        <TableCell>{topic.reading_count}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>

                {/* 分页控制 */}
                <div className="flex items-center justify-between mt-4">
                  <div className="text-sm text-muted-foreground">
                    共 {topicsData.pagination.total} 条记录，第 {topicsData.pagination.page} / {topicsData.pagination.pages} 页
                  </div>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setTopicsPage(Math.max(1, topicsPage - 1))}
                      disabled={topicsPage <= 1 || loading}
                    >
                      上一页
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setTopicsPage(Math.min(topicsData.pagination.pages, topicsPage + 1))}
                      disabled={topicsPage >= topicsData.pagination.pages || loading}
                    >
                      下一页
                    </Button>
                  </div>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </TabsContent>

      <TabsContent value="files">
        <Card className="border border-gray-200 shadow-none">
          <CardHeader>
            <CardTitle>文件列表</CardTitle>
            <CardDescription>查看已同步的文件信息</CardDescription>
          </CardHeader>
          <CardContent>
            {selectedGroupId === undefined && (
              <div className="text-sm text-muted-foreground mb-4">
                请先选择一个群组再查看文件列表
              </div>
            )}
            {/* 状态筛选 */}
            <div className="flex flex-col gap-2 mb-4 lg:flex-row">
              <div className="flex flex-1 gap-2">
                <Input
                  placeholder="搜索文件名..."
                  value={filesSearch}
                  onChange={(e) => setFilesSearch(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      handleFilesSearch();
                    }
                  }}
                  disabled={selectedGroupId === undefined}
                />
                <Button
                  onClick={handleFilesSearch}
                  disabled={selectedGroupId === undefined || loading}
                >
                  搜索
                </Button>
              </div>
              <Select
                value={filesStatus}
                onValueChange={handleFilesStatusChange}
                disabled={selectedGroupId === undefined}
              >
                <SelectTrigger className="w-48">
                  <SelectValue placeholder="选择状态筛选" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">全部状态</SelectItem>
                  <SelectItem value="pending">未下载</SelectItem>
                  <SelectItem value="completed">已完成</SelectItem>
                  <SelectItem value="downloaded">已完成(旧)</SelectItem>
                  <SelectItem value="skipped">已存在</SelectItem>
                  <SelectItem value="failed">失败</SelectItem>
                </SelectContent>
              </Select>
              <Button
                variant="outline"
                onClick={() => void loadFiles()}
                disabled={selectedGroupId === undefined || loading}
              >
                <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
                刷新
              </Button>
              <Button
                variant="outline"
                onClick={() => void handleSyncFilesFromTopics()}
                disabled={selectedGroupId === undefined || syncingFiles}
              >
                <DatabaseZap className={`h-4 w-4 mr-2 ${syncingFiles ? 'animate-pulse' : ''}`} />
                重新同步
              </Button>
            </div>

            {filesData && filesData.data.length > 0 && (
              <div className="mb-4 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-gray-200 bg-gray-50 p-3 text-sm">
                <div className="text-muted-foreground">
                  已选择 {selectedDownloadableFiles.length} 个可下载文件
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => toggleSelectableFilesOnPage(true)}
                    disabled={selectableFilesOnPage.length === 0}
                  >
                    <ListChecks className="h-4 w-4 mr-2" />
                    选择本页未下载
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setSelectedFileIds(new Set())}
                    disabled={selectedFileIds.size === 0}
                  >
                    清除选择
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => void handleBatchDownloadSelected()}
                    disabled={selectedDownloadableFiles.length === 0}
                  >
                    <Download className="h-4 w-4 mr-2" />
                    批量下载/重试
                  </Button>
                </div>
              </div>
            )}

            {/* 文件表格 */}
            {filesData && (
              <>
                {filesData.data.length === 0 ? (
                  <div className="rounded-lg border border-dashed p-10 text-center text-sm text-muted-foreground">
                    {filesSearchQuery || filesStatus !== 'all'
                      ? '没有匹配的文件记录。'
                      : '当前没有文件记录。采集包含附件的话题后，文件会自动同步到这里。'}
                  </div>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-10">
                          <input
                            type="checkbox"
                            aria-label="选择本页可下载文件"
                            checked={allSelectableFilesChecked}
                            disabled={selectableFilesOnPage.length === 0}
                            onChange={(event) => toggleSelectableFilesOnPage(event.target.checked)}
                            className="h-4 w-4 rounded border-gray-300"
                          />
                        </TableHead>
                        <TableHead>文件名</TableHead>
                        <TableHead>大小</TableHead>
                        <TableHead>下载次数</TableHead>
                        <TableHead>创建时间</TableHead>
                        <TableHead>状态</TableHead>
                        <TableHead className="text-right">操作</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {filesData.data.map((file) => {
                        const downloaded = isFileDownloaded(file);
                        const creatingTask = downloadingFiles.has(file.file_id);
                        const fileTask = fileTasks.get(file.file_id);

                        return (
                          <TableRow key={file.file_id}>
                            <TableCell>
                              <input
                                type="checkbox"
                                aria-label={`选择文件 ${file.name}`}
                                checked={selectedFileIds.has(file.file_id)}
                                disabled={downloaded || creatingTask}
                                onChange={(event) => toggleFileSelection(file.file_id, event.target.checked)}
                                className="h-4 w-4 rounded border-gray-300"
                              />
                            </TableCell>
                            <TableCell className="max-w-md">
                              <div className="truncate font-medium" title={file.name}>
                                {file.name}
                              </div>
                              {file.local_path && (
                                <div className="mt-1 truncate text-xs text-muted-foreground" title={file.local_path}>
                                  {file.local_path}
                                </div>
                              )}
                            </TableCell>
                            <TableCell>{formatFileSize(file.size)}</TableCell>
                            <TableCell>{file.download_count}</TableCell>
                            <TableCell>{formatDate(file.create_time)}</TableCell>
                            <TableCell>{getStatusBadge(file.download_status)}</TableCell>
                            <TableCell className="text-right">
                              <div className="flex justify-end gap-2">
                                <Button
                                  size="sm"
                                  variant={downloaded ? 'outline' : 'default'}
                                  disabled={downloaded || creatingTask}
                                  onClick={() => void handleDownloadFile(file)}
                                >
                                  <Download className="h-4 w-4 mr-2" />
                                  {downloaded ? '已下载' : creatingTask ? '创建中' : file.download_status === 'failed' ? '重试' : '下载'}
                                </Button>
                                <Button
                                  size="sm"
                                  variant="outline"
                                  disabled={!downloaded}
                                  onClick={() => void openAnalysisDialog(file, false)}
                                >
                                  <Sparkles className="h-4 w-4 mr-2" />
                                  {file.has_ai_analysis ? '查看分析' : 'AI 分析'}
                                </Button>
                              </div>
                              {fileTask && !downloaded && (
                                <div className={`mt-1 text-xs ${
                                  fileTask.status === 'failed' || fileTask.status === 'cancelled'
                                    ? 'text-red-600'
                                    : fileTask.status === 'completed'
                                      ? 'text-green-600'
                                      : 'text-muted-foreground'
                                }`}>
                                  {fileTask.message}
                                </div>
                              )}
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                )}

                {/* 分页控制 */}
                <div className="flex items-center justify-between mt-4">
                  <div className="text-sm text-muted-foreground">
                    共 {filesData.pagination.total} 条记录，第 {filesData.pagination.page} / {filesData.pagination.pages} 页
                  </div>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setFilesPage(Math.max(1, filesPage - 1))}
                      disabled={filesPage <= 1 || loading}
                    >
                      上一页
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setFilesPage(Math.min(filesData.pagination.pages, filesPage + 1))}
                      disabled={filesPage >= filesData.pagination.pages || loading}
                    >
                      下一页
                    </Button>
                  </div>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </TabsContent>

      <Dialog open={analysisOpen} onOpenChange={setAnalysisOpen}>
        <DialogContent className="sm:max-w-3xl max-h-[85vh] overflow-auto">
          <DialogHeader>
            <DialogTitle>{selectedFile?.name || '文件 AI 分析'}</DialogTitle>
            <DialogDescription>
              基于本地已下载文件内容生成摘要
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div className="flex items-center justify-between gap-3">
              <div className="text-sm text-muted-foreground">
                {selectedFile ? `文件大小：${formatFileSize(selectedFile.size)}` : ''}
              </div>
              {selectedFile && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => void openAnalysisDialog(selectedFile, true)}
                  disabled={analysisLoading}
                >
                  <RefreshCw className={`h-4 w-4 mr-2 ${analysisLoading ? 'animate-spin' : ''}`} />
                  重新分析
                </Button>
              )}
            </div>

            {analysisLoading ? (
              <div className="rounded-lg border border-dashed p-10 text-center text-muted-foreground">
                <Loader2 className="h-5 w-5 animate-spin mx-auto mb-3" />
                AI 正在分析文件内容...
              </div>
            ) : analysis?.status === 'failed' ? (
              <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
                {analysis.error_message || '分析失败'}
              </div>
            ) : (
              <>
                <div className="rounded-lg border border-gray-200 bg-gray-50 p-3 text-sm">
                  <div>模型：{analysis?.model || '未知'}</div>
                  <div>接口：{analysis?.wire_api || '未知'}</div>
                  <div>最近更新时间：{formatDate(analysis?.updated_at || '')}</div>
                </div>

                {analysis?.summary && (
                  <div>
                    <div className="mb-2 text-sm font-medium">摘要</div>
                    <div className="whitespace-pre-wrap rounded-lg border border-gray-200 p-4 text-sm leading-6">
                      {analysis.summary}
                    </div>
                  </div>
                )}

                {(analysis?.extracted_text || analysis?.extracted_text_preview) && (
                  <div>
                    <div className="mb-2 text-sm font-medium">{getAnalysisTextLabel(analysis.content_type)}</div>
                    <div className="max-h-72 overflow-auto whitespace-pre-wrap rounded-lg border border-gray-200 bg-gray-50 p-4 text-xs leading-5">
                      {analysis.extracted_text || analysis.extracted_text_preview}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </DialogContent>
      </Dialog>
      </Tabs>
    </>
  );
}
