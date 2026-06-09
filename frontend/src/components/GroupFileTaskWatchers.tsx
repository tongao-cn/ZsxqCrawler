'use client';

import { useTaskStatus } from '@/hooks/useTaskStatus';

export interface FileTaskState {
  taskId: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  message: string;
}

interface FileTaskWatcherProps {
  fileId: number;
  taskId: string;
  onStatus: (fileId: number, taskId: string, status: FileTaskState['status'], message: string) => void;
  onTerminal: (fileId: number, taskId: string, status: FileTaskState['status'], message: string) => void | Promise<void>;
}

interface TaskStatusWatcherProps {
  taskId: string;
  onTerminal: (status: FileTaskState['status'], message: string) => void | Promise<void>;
}

function FileTaskWatcher({
  fileId,
  taskId,
  onStatus,
  onTerminal,
}: FileTaskWatcherProps) {
  useTaskStatus(taskId, {
    onStatus: (task) => onStatus(fileId, taskId, task.status, task.message),
    onTerminal: (task) => onTerminal(fileId, taskId, task.status, task.message),
  });
  return null;
}

function TaskStatusWatcher({ taskId, onTerminal }: TaskStatusWatcherProps) {
  useTaskStatus(taskId, {
    onTerminal: (task) => onTerminal(task.status, task.message),
  });
  return null;
}

interface GroupFileTaskWatchersProps {
  fileTasks: Map<number, FileTaskState>;
  batchDownloadTaskId: string | null;
  analysisTasks: Map<number, FileTaskState>;
  batchAnalysisTaskId: string | null;
  onFileTaskStatus: FileTaskWatcherProps['onStatus'];
  onFileTaskTerminal: FileTaskWatcherProps['onTerminal'];
  onBatchDownloadTerminal: TaskStatusWatcherProps['onTerminal'];
  onAnalysisTaskStatus: FileTaskWatcherProps['onStatus'];
  onAnalysisTaskTerminal: FileTaskWatcherProps['onTerminal'];
  onBatchAnalysisTerminal: TaskStatusWatcherProps['onTerminal'];
}

export function GroupFileTaskWatchers({
  fileTasks,
  batchDownloadTaskId,
  analysisTasks,
  batchAnalysisTaskId,
  onFileTaskStatus,
  onFileTaskTerminal,
  onBatchDownloadTerminal,
  onAnalysisTaskStatus,
  onAnalysisTaskTerminal,
  onBatchAnalysisTerminal,
}: GroupFileTaskWatchersProps) {
  return (
    <>
      {Array.from(fileTasks.entries()).map(([fileId, task]) => (
        task.status === 'pending' || task.status === 'running' ? (
          <FileTaskWatcher
            key={`${fileId}-${task.taskId}`}
            fileId={fileId}
            taskId={task.taskId}
            onStatus={onFileTaskStatus}
            onTerminal={onFileTaskTerminal}
          />
        ) : null
      ))}
      {batchDownloadTaskId && (
        <TaskStatusWatcher
          taskId={batchDownloadTaskId}
          onTerminal={onBatchDownloadTerminal}
        />
      )}
      {Array.from(analysisTasks.entries()).map(([fileId, task]) => (
        task.status === 'pending' || task.status === 'running' ? (
          <FileTaskWatcher
            key={`analysis-${fileId}-${task.taskId}`}
            fileId={fileId}
            taskId={task.taskId}
            onStatus={onAnalysisTaskStatus}
            onTerminal={onAnalysisTaskTerminal}
          />
        ) : null
      ))}
      {batchAnalysisTaskId && (
        <TaskStatusWatcher
          taskId={batchAnalysisTaskId}
          onTerminal={onBatchAnalysisTerminal}
        />
      )}
    </>
  );
}
