'use client';

import { useCallback, useState, useEffect, useRef, type KeyboardEvent } from 'react';
import { useRouter } from 'next/navigation';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { MessageSquare, Crown, UserCog, RefreshCw, Trash2 } from 'lucide-react';
import { apiClient, Group, GroupStats } from '@/lib/api';
import { toast } from 'sonner';
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from '@/components/ui/alert-dialog';
import SafeImage from './SafeImage';
import '../styles/group-selector.css';

const MAX_AUTO_RETRIES = 5;
const RETRYABLE_LOAD_ERROR_MARKERS = ['未知错误', '空数据', '反爬虫'];

function isRetryableLoadError(message: string) {
  return RETRYABLE_LOAD_ERROR_MARKERS.some((marker) => message.includes(marker));
}

function getGradientByType(type: string) {
  switch (type) {
    case 'private':
      return 'from-purple-400 to-pink-500';
    case 'public':
      return 'from-blue-400 to-cyan-500';
    default:
      return 'from-gray-400 to-gray-600';
  }
}

function isExpiringWithinMonth(expiryTime?: string) {
  if (!expiryTime) return false;
  const expiryDate = new Date(expiryTime);
  const now = new Date();
  const oneMonthFromNow = new Date();
  oneMonthFromNow.setMonth(now.getMonth() + 1);

  return expiryDate <= oneMonthFromNow && expiryDate > now;
}

interface GroupCardProps {
  deleting: boolean;
  group: Group;
  mode: 'account' | 'local';
  onDelete: (groupId: number) => void;
  onOpen: (groupId: number) => void;
  stats?: GroupStats;
}

function GroupTypeBadge({ group, mode }: { group: Group; mode: 'account' | 'local' }) {
  if (mode === 'local') {
    return (
      <Badge variant="secondary" className="text-xs px-1.5 py-0 h-5">
        本地
      </Badge>
    );
  }

  if (group.type !== 'pay') {
    return (
      <Badge variant="secondary" className="text-xs px-1.5 py-0 h-5">
        免费
      </Badge>
    );
  }

  if (group.status === 'expired') {
    return (
      <Badge variant="destructive" className="text-xs px-1.5 py-0 h-5">
        已过期
      </Badge>
    );
  }

  if (isExpiringWithinMonth(group.expiry_time)) {
    return (
      <Badge variant="outline" className="text-xs px-1.5 py-0 h-5 text-yellow-600 border-yellow-200">
        即将过期
      </Badge>
    );
  }

  return (
    <Badge className={`text-xs px-1.5 py-0 h-5 ${group.is_trial ? 'bg-purple-600' : 'bg-green-600'}`}>
      {group.is_trial ? '试用' : '付费'}
    </Badge>
  );
}

function GroupCard({
  deleting,
  group,
  mode,
  onDelete,
  onOpen,
  stats,
}: GroupCardProps) {
  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      onOpen(group.group_id);
    }
  };

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={`打开群组 ${group.name}`}
      className="group-card w-full cursor-pointer overflow-hidden rounded-lg border border-gray-200 bg-white transition-all duration-200 hover:border-gray-300 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      onClick={() => onOpen(group.group_id)}
      onKeyDown={handleKeyDown}
    >
      <div className="aspect-square w-full">
        <SafeImage
          src={group.background_url}
          alt={group.name}
          className="w-full h-full object-cover"
          fallbackClassName="w-full h-full bg-gradient-to-br"
          fallbackText={group.name.slice(0, 2)}
          fallbackGradient={getGradientByType(group.type)}
        />
      </div>

      <div className="p-2.5">
        <h3 className="text-sm font-semibold text-gray-900 line-clamp-1 mb-1.5">
          {group.name}
        </h3>

        <div className="flex items-center justify-between text-xs text-gray-500 mb-1.5">
          {group.owner && (
            <div className="flex items-center gap-1">
              <Crown className="h-3 w-3" />
              <span className="truncate max-w-[80px]">{group.owner.name}</span>
            </div>
          )}

          {stats && (
            <div className="flex items-center gap-1">
              <MessageSquare className="h-3 w-3" />
              <span>{stats.topics_count || 0}</span>
            </div>
          )}
        </div>

        <div className="flex items-center justify-between">
          <GroupTypeBadge group={group} mode={mode} />

          <AlertDialog>
            <AlertDialogTrigger asChild>
              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                }}
                className="p-1 text-gray-400 hover:text-red-600 transition-colors"
                title="删除本地数据"
                disabled={deleting}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </AlertDialogTrigger>
            <AlertDialogContent onClick={(event) => event.stopPropagation()}>
              <AlertDialogHeader>
                <AlertDialogTitle className="text-red-600">确认删除该社群的本地数据</AlertDialogTitle>
                <AlertDialogDescription className="text-red-700">
                  此操作将删除该社群的本地数据库、下载文件与图片缓存，不会影响账号对该社群的访问权限。操作不可恢复。
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel onClick={(event) => event.stopPropagation()}>取消</AlertDialogCancel>
                <AlertDialogAction
                  className="bg-red-600 hover:bg-red-700 focus:ring-red-600"
                  onClick={(event) => {
                    event.stopPropagation();
                    onDelete(group.group_id);
                  }}
                >
                  确认删除
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      </div>
    </div>
  );
}

interface GroupGridProps {
  deletingGroups: Set<number>;
  groupStats: Record<number, GroupStats>;
  groups: Group[];
  mode: 'account' | 'local';
  onDeleteGroup: (groupId: number) => void;
  onOpenGroup: (groupId: number) => void;
}

function GroupGrid({
  deletingGroups,
  groupStats,
  groups,
  mode,
  onDeleteGroup,
  onOpenGroup,
}: GroupGridProps) {
  return (
    <div className="grid grid-cols-[repeat(auto-fill,minmax(160px,1fr))] gap-4 sm:grid-cols-[repeat(auto-fill,minmax(180px,1fr))]">
      {groups.map((group) => (
        <GroupCard
          key={group.group_id}
          deleting={deletingGroups.has(group.group_id)}
          group={group}
          mode={mode}
          onDelete={onDeleteGroup}
          onOpen={onOpenGroup}
          stats={groupStats[group.group_id]}
        />
      ))}
    </div>
  );
}

export default function GroupSelector() {
  const router = useRouter();
  const [groups, setGroups] = useState<Group[]>([]);
  const [groupStats, setGroupStats] = useState<Record<number, GroupStats>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retryCount, setRetryCount] = useState(0);
  const [isRetrying, setIsRetrying] = useState(false);
  const [deletingGroups, setDeletingGroups] = useState<Set<number>>(new Set());
  const hasLoadedGroupsRef = useRef(false);
  const retryTimerRef = useRef<number | null>(null);
  const loadRequestRef = useRef(0);
  const statsRequestRef = useRef(0);

  const loadGroups = useCallback(async (currentRetryCount = 0) => {
    const loadRequestId = loadRequestRef.current + 1;
    loadRequestRef.current = loadRequestId;
    try {
      if (currentRetryCount === 0) {
        if (retryTimerRef.current) {
          window.clearTimeout(retryTimerRef.current);
          retryTimerRef.current = null;
        }
        statsRequestRef.current += 1;
        if (!hasLoadedGroupsRef.current) {
          setLoading(true);
        }
        setError(null);
        setRetryCount(0);
        setIsRetrying(false);
      } else {
        setIsRetrying(true);
        setRetryCount(currentRetryCount);
      }

      const data = await apiClient.getGroups();
      if (loadRequestRef.current !== loadRequestId) {
        return;
      }

      // 检查返回数据（允许为空，显示空态，不再抛错）

      setGroups(data.groups);
      hasLoadedGroupsRef.current = true;
      setGroupStats({});
      const statsRequestId = statsRequestRef.current + 1;
      statsRequestRef.current = statsRequestId;

      // 群组列表先展示出来，统计信息后台补齐；避免某个 stats 慢导致首页一直停在加载态。
      setError(null);
      setRetryCount(0);
      setIsRetrying(false);
      setLoading(false);

      void (async () => {
        const statsPromises = data.groups.map(async (group: Group) => {
          try {
            const stats = await apiClient.getGroupStats(group.group_id);
            return { groupId: group.group_id, stats };
          } catch (error) {
            console.warn(`获取群组 ${group.group_id} 统计信息失败:`, error);
            return { groupId: group.group_id, stats: null };
          }
        });

        const statsResults = await Promise.all(statsPromises);
        const statsMap: Record<number, GroupStats> = {};
        statsResults.forEach(({ groupId, stats }) => {
          if (stats) {
            statsMap[groupId] = stats;
          }
        });
        if (statsRequestRef.current === statsRequestId) {
          setGroupStats(statsMap);
        }
      })();

    } catch (err) {
      if (loadRequestRef.current !== loadRequestId) {
        return;
      }
      const errorMessage = err instanceof Error ? err.message : '加载群组列表失败';

      if (isRetryableLoadError(errorMessage) && currentRetryCount < MAX_AUTO_RETRIES) {
        const nextRetryCount = currentRetryCount + 1;
        const delay = Math.min(1000 + (nextRetryCount * 500), 5000); // 递增延迟，最大5秒

        if (retryTimerRef.current) {
          window.clearTimeout(retryTimerRef.current);
        }
        retryTimerRef.current = window.setTimeout(() => {
          retryTimerRef.current = null;
          void loadGroups(nextRetryCount);
        }, delay);
        return;
      }

      setError(isRetryableLoadError(errorMessage) ? `${errorMessage}，自动重试已达上限` : errorMessage);
      setIsRetrying(false);
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadGroups();
  }, [loadGroups]);

  useEffect(() => {
    return () => {
      if (retryTimerRef.current) {
        window.clearTimeout(retryTimerRef.current);
        retryTimerRef.current = null;
      }
      loadRequestRef.current += 1;
      statsRequestRef.current += 1;
    };
  }, []);

  // 监听页面可见性变化和窗口焦点，返回页面时自动刷新群组列表
  // 使用节流避免频繁刷新
  useEffect(() => {
    let lastRefresh = 0;
    const REFRESH_INTERVAL = 5000; // 最少间隔 5 秒

    const maybeRefresh = () => {
      const now = Date.now();
      if (now - lastRefresh > REFRESH_INTERVAL) {
        lastRefresh = now;
        void loadGroups(0);
      }
    };

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        maybeRefresh();
      }
    };
    const handleFocus = () => {
      maybeRefresh();
    };
    document.addEventListener('visibilitychange', handleVisibilityChange);
    window.addEventListener('focus', handleFocus);
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.removeEventListener('focus', handleFocus);
    };
  }, [loadGroups]);



  const handleRefresh = async () => {
    try {
      await apiClient.refreshLocalGroups();
      await loadGroups(0);
      toast.success('已刷新本地群目录');
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      toast.error(`刷新失败: ${msg}`);
    }
  };

  const handleDeleteGroup = async (groupId: number) => {
    if (deletingGroups.has(groupId)) return;
    setDeletingGroups((prev) => new Set(prev).add(groupId));
    try {
      const res = await apiClient.deleteGroup(groupId);
      const msg = (res as any)?.message || '已删除';
      toast.success(msg);
      await loadGroups(0);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      toast.error(`删除失败: ${msg}`);
    } finally {
      setDeletingGroups((prev) => {
        const s = new Set(prev);
        s.delete(groupId);
        return s;
      });
    }
  };

  const openGroup = (groupId: number) => {
    router.push(`/groups/${groupId}`);
  };

  if (loading || isRetrying) {
    return (
      <div className="min-h-screen bg-background">
        <div className="container mx-auto p-4">
          <div className="mb-4">
            <h1 className="text-2xl font-bold mb-1">🌟 知识星球数据采集器</h1>
            <p className="text-sm text-muted-foreground">
              {isRetrying ? '正在重试获取群组列表...' : '正在加载您的知识星球群组...'}
            </p>
          </div>
          <div className="flex items-center justify-center py-8">
            <div className="text-center">
              <Progress value={undefined} className="w-64 mb-4" />
              <p className="text-muted-foreground">
                {isRetrying ? `正在重试... (第${retryCount}次)` : '加载群组列表中...'}
              </p>
              {isRetrying && (
                <p className="text-xs text-gray-400 mt-2">
                  检测到API防护机制，正在自动重试获取数据
                </p>
              )}
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-background">
        <div className="container mx-auto p-4">
          <div className="mb-4">
            <h1 className="text-2xl font-bold mb-1">🌟 知识星球数据采集器</h1>
            <p className="text-sm text-muted-foreground">
              加载群组列表时出现错误
            </p>
          </div>
          <Card className="max-w-md mx-auto">
            <CardHeader>
              <CardTitle className="text-red-600">加载失败</CardTitle>
              <CardDescription>无法获取群组列表</CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground mb-4">{error}</p>
              <Button onClick={() => loadGroups()} className="w-full">
                重试
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>
    );
  }

  // 按来源拆分群组：网络群组（账号）与本地群组
  // 说明：凡是包含 account 的都视为“网络群组”；凡是包含 local 的都视为“本地群组”
  // 这样 account|local 这类“既有账号又有本地数据”的群，会在两个 Tab 都展示，
  // 满足你在网络和本地视角下都能看到完整信息的需求。
  const accountGroups = groups.filter((g) => !g.source || g.source.includes('account'));
  const localGroups = groups.filter((g) => g.source && g.source.includes('local'));

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto p-4">
        <div className="mb-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold mb-1">🌟 知识星球数据采集器</h1>
              <p className="text-sm text-muted-foreground">
                选择要操作的知识星球群组
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                onClick={handleRefresh}
                className="flex items-center gap-2"
              >
                <RefreshCw className="h-4 w-4" />
                刷新本地群
              </Button>
              <Button
                variant="outline"
                onClick={() => router.push('/accounts')}
                className="flex items-center gap-2"
              >
                <UserCog className="h-4 w-4" />
                账号管理
              </Button>
            </div>
          </div>
        </div>

        {/* 群组统计 */}
        <div className="mb-4 space-y-0.5">
          <p className="text-sm text-muted-foreground">
            共 {accountGroups.length} 个网络群组，{localGroups.length} 个本地群组
          </p>
        </div>

        {/* 群组网格：通过标签区分账号群组与本地群组，禁止混在同一列表中 */}
        <Tabs defaultValue="account" className="space-y-3">
          <TabsList className="grid w-full grid-cols-2 h-9 text-sm">
            <TabsTrigger value="account">网络群组（账号）</TabsTrigger>
            <TabsTrigger value="local">本地群组</TabsTrigger>
          </TabsList>

          {/* 网络群组 */}
          <TabsContent value="account">
            {accountGroups.length === 0 ? (
              <Card className="max-w-md mx-auto border border-gray-200 shadow-none">
                <CardContent className="pt-6">
                  <div className="text-center">
                    <p className="text-muted-foreground">
                      暂无可访问的网络群组，请先在账号管理中添加或更新 Cookie
                    </p>
                  </div>
                </CardContent>
              </Card>
            ) : (
              <GroupGrid
                deletingGroups={deletingGroups}
                groupStats={groupStats}
                groups={accountGroups}
                mode="account"
                onDeleteGroup={(groupId) => void handleDeleteGroup(groupId)}
                onOpenGroup={openGroup}
              />
            )}
          </TabsContent>

          {/* 本地群组 */}
          <TabsContent value="local">
            {localGroups.length === 0 ? (
              <Card className="max-w-md mx-auto border border-gray-200 shadow-none">
                <CardContent className="pt-6">
                  <div className="text-center">
                    <p className="text-muted-foreground">
                      暂无本地群组，请先执行采集或从旧版本迁移数据
                    </p>
                  </div>
                </CardContent>
              </Card>
            ) : (
              <GroupGrid
                deletingGroups={deletingGroups}
                groupStats={groupStats}
                groups={localGroups}
                mode="local"
                onDeleteGroup={(groupId) => void handleDeleteGroup(groupId)}
                onOpenGroup={openGroup}
              />
            )}
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
