'use client';

import { useState, useEffect } from 'react';
import dynamic from 'next/dynamic';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';

import { apiClient, DatabaseStats } from '@/lib/api';

const LazyPanelFallback = () => (
  <div className="flex min-h-48 items-center justify-center text-sm text-muted-foreground">
    加载中...
  </div>
);

const ConfigPanel = dynamic(() => import('@/components/ConfigPanel'), {
  loading: LazyPanelFallback,
  ssr: false,
});
const GroupSelector = dynamic(() => import('@/components/GroupSelector'), {
  loading: LazyPanelFallback,
  ssr: false,
});
export default function Home() {
  const [stats, setStats] = useState<DatabaseStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadStats();
  }, []);



  const loadStats = async () => {
    try {
      setLoading(true);
      const data = await apiClient.getDatabaseStats();
      setStats(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载统计信息失败');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <Progress value={undefined} className="w-64 mb-4" />
          <p className="text-muted-foreground">加载中...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Card className="w-96">
          <CardHeader>
            <CardTitle className="text-red-600">连接错误</CardTitle>
            <CardDescription>无法连接到后端API服务</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground mb-4">{error}</p>
            <Button onClick={loadStats} className="w-full">
              重试连接
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  // 检查是否已配置
  if (stats && stats.configured === false) {
    return <ConfigPanel onConfigSaved={loadStats} />;
  }

  // 如果已配置，显示群组选择界面
  if (stats && stats.configured !== false) {
    return <GroupSelector />;
  }

  return null;
}
