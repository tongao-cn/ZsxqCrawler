'use client';

import SafeImage from '@/components/SafeImage';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { apiClient, type Account, type AccountSelf, type Group, type GroupStats } from '@/lib/api';
import { BookOpen, PanelLeftClose, PanelLeftOpen } from 'lucide-react';

type GroupInfo = {
  statistics?: {
    files?: {
      count?: number;
    };
  };
};

type LocalFileStats = {
  total: number;
  downloaded: number;
  pending: number;
  failed: number;
};

type GroupSidebarProps = {
  group: Group;
  groupStats: GroupStats | null;
  groupInfo: GroupInfo | null;
  localFileCount: number;
  localFileStats: LocalFileStats;
  accountSelf: AccountSelf | null;
  accounts: Account[];
  groupAccount?: Account | null;
  selectedAccountId: string;
  onSelectedAccountIdChange: (accountId: string) => void;
  assigningAccount: boolean;
  onAssignAccount: () => void;
  hasColumns: boolean;
  columnsTitle?: string | null;
  onOpenColumns?: () => void;
  collapsed: boolean;
  onCollapsedChange: (collapsed: boolean) => void;
};

const getTypeBadge = (type: string) => {
  switch (type) {
    case 'private':
      return <Badge variant="secondary" className="text-xs px-1.5 py-0.5">私密</Badge>;
    case 'public':
      return <Badge variant="secondary" className="text-xs px-1.5 py-0.5">公开</Badge>;
    case 'pay':
      return <Badge className="bg-orange-100 text-orange-800 text-xs px-1.5 py-0.5">付费</Badge>;
    default:
      return <Badge variant="secondary" className="text-xs px-1.5 py-0.5">未知</Badge>;
  }
};

const getStatusBadge = (status?: string) => {
  switch (status) {
    case 'active':
      return <Badge className="bg-green-100 text-green-800 text-xs">活跃</Badge>;
    case 'expiring_soon':
      return <Badge className="bg-yellow-100 text-yellow-800 text-xs">即将到期</Badge>;
    case 'expired':
      return <Badge className="bg-red-100 text-red-800 text-xs">已过期</Badge>;
    default:
      return null;
  }
};

const formatDate = (dateString?: string) => {
  if (!dateString) return '';
  try {
    return new Date(dateString).toLocaleDateString('zh-CN');
  } catch {
    return '';
  }
};

const getGradientByType = (type: string) => {
  switch (type) {
    case 'private':
      return 'from-purple-400 to-pink-500';
    case 'public':
      return 'from-blue-400 to-cyan-500';
    case 'pay':
      return 'from-orange-400 to-red-500';
    default:
      return 'from-gray-400 to-gray-600';
  }
};

export default function GroupSidebar({
  group,
  groupStats,
  groupInfo,
  localFileCount,
  localFileStats,
  accountSelf,
  accounts,
  groupAccount,
  selectedAccountId,
  onSelectedAccountIdChange,
  assigningAccount,
  onAssignAccount,
  hasColumns,
  columnsTitle,
  onOpenColumns,
  collapsed,
  onCollapsedChange,
}: GroupSidebarProps) {
  const accountName = accountSelf?.name || groupAccount?.name || groupAccount?.id || '默认账号';
  const accountFallbackText = accountName.slice(0, 1) || '账';
  const remoteFileCount = groupInfo?.statistics?.files?.count;
  const showAccountAssignment = accounts.length > 0 && false;

  if (collapsed) {
    return (
      <div className="w-16 flex-shrink-0 sticky top-0 h-fit max-h-screen">
        <Card className="border border-gray-200 shadow-none h-full">
          <CardContent className="p-2 flex flex-col items-center gap-3">
            <Button
              variant="ghost"
              size="sm"
              className="h-9 w-9 p-0"
              aria-label="展开群组信息侧边栏"
              title="展开群组信息侧边栏"
              onClick={() => onCollapsedChange(false)}
            >
              <PanelLeftOpen className="h-4 w-4" />
            </Button>
            <SafeImage
              src={group.background_url}
              alt={group.name}
              className="w-10 h-10 rounded-lg object-cover"
              fallbackClassName="w-10 h-10 rounded-lg"
              fallbackText={group.name.slice(0, 2)}
              fallbackGradient={getGradientByType(group.type)}
            />
            {hasColumns && (
              <Button
                variant="ghost"
                size="sm"
                className="h-9 w-9 p-0"
                aria-label={columnsTitle || '打开专栏'}
                title={columnsTitle || '打开专栏'}
                onClick={onOpenColumns}
              >
                <BookOpen className="h-4 w-4" />
              </Button>
            )}
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="w-80 flex-shrink-0 sticky top-0 h-fit max-h-screen">
      <Card className="border border-gray-200 shadow-none h-full">
        <ScrollArea className="h-full">
          <CardContent className="p-4 flex flex-col">
            <div className="flex items-center gap-3 mb-4">
              <SafeImage
                src={group.background_url}
                alt={group.name}
                className="w-12 h-12 rounded-lg object-cover"
                fallbackClassName="w-12 h-12 rounded-lg"
                fallbackText={group.name.slice(0, 2)}
                fallbackGradient={getGradientByType(group.type)}
              />
              <div className="flex-1">
                <h2 className="text-lg font-bold text-gray-900 mb-1">{group.name}</h2>
                <div className="flex items-center gap-2">
                  {getTypeBadge(group.type)}
                  {getStatusBadge(group.status)}
                </div>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-3 text-sm">
              {group.join_time && (
                <div>
                  <span className="text-gray-500 block">加入时间</span>
                  <span className="text-gray-900 font-medium">{formatDate(group.join_time)}</span>
                </div>
              )}
              {group.expiry_time && (
                <div>
                  <span className="text-gray-500 block">到期时间</span>
                  <span className={
                    group.status === 'expiring_soon' ? 'text-yellow-600 font-medium' :
                    group.status === 'expired' ? 'text-red-600 font-medium' : 'text-gray-900 font-medium'
                  }>
                    {formatDate(group.expiry_time)}
                  </span>
                </div>
              )}
              {groupStats && (
                <div>
                  <span className="text-gray-500 block">本地话题数</span>
                  <span className="text-blue-600 font-semibold">{groupStats.topics_count}</span>
                </div>
              )}
            </div>

            {hasColumns && (
              <div className="mt-6 border-t border-gray-200 pt-4">
                <Button
                  variant="outline"
                  size="sm"
                  className="w-full flex items-center gap-2 whitespace-nowrap bg-gradient-to-r from-amber-50 to-orange-50 border-amber-200 hover:border-amber-300 hover:from-amber-100 hover:to-orange-100 text-amber-700"
                  onClick={onOpenColumns}
                >
                  <BookOpen className="h-4 w-4" />
                  {columnsTitle || '专栏'}
                </Button>
              </div>
            )}

            <div className="mt-6 border-t border-gray-200 pt-4">
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-sm font-medium text-gray-900">所属账号</h3>
                <Badge variant="outline" className="text-xs">自动匹配</Badge>
              </div>
              <div className="text-sm text-gray-700 mb-3">
                <div className="flex items-center gap-2">
                  {accountSelf?.avatar_url ? (
                    <SafeImage
                      src={apiClient.getProxyImageUrl(accountSelf.avatar_url, group.group_id.toString())}
                      alt={accountSelf?.name || ''}
                      className="w-5 h-5 rounded-full"
                      fallbackClassName="w-5 h-5 rounded-full"
                      fallbackText={accountFallbackText}
                    />
                  ) : (
                    <div className="w-5 h-5 rounded-full bg-gray-200" />
                  )}
                  <span>{accountName}</span>
                  {(groupAccount?.is_default || groupAccount?.id === 'default') && (
                    <Badge variant="secondary" className="text-xs">默认</Badge>
                  )}
                </div>
              </div>
              {showAccountAssignment && (
                <div className="flex items-center gap-2">
                  <Select value={selectedAccountId} onValueChange={onSelectedAccountIdChange}>
                    <SelectTrigger className="w-[240px]">
                      <SelectValue placeholder="选择一个账号" />
                    </SelectTrigger>
                    <SelectContent>
                      {accounts.map((acc) => (
                        <SelectItem key={acc.id} value={acc.id}>
                          {(acc.name || acc.id) + (acc.is_default ? '（默认）' : '')}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Button
                    size="sm"
                    onClick={onAssignAccount}
                    disabled={!selectedAccountId || assigningAccount}
                  >
                    {assigningAccount ? '绑定中...' : '绑定到此群组'}
                  </Button>
                </div>
              )}
            </div>

            <div className="mt-6 border-t border-gray-200 pt-4">
              <div className={`rounded-lg border p-3 text-xs ${
                localFileCount === 0
                  ? 'border-amber-200 bg-amber-50 text-amber-800'
                  : 'border-blue-200 bg-blue-50 text-blue-800'
              }`}>
                <div className="flex items-center justify-between gap-2">
                  <div className="font-medium">文件记录</div>
                  <Badge variant="secondary" className="text-[10px]">
                    {localFileStats.total} 条
                  </Badge>
                </div>
                {localFileCount === 0 ? (
                  <div className="mt-2">当前还没有文件记录。采集包含附件的话题后，文件会自动同步到这里。</div>
                ) : (
                  <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px]">
                    <span>已下载 {localFileStats.downloaded}</span>
                    <span>未下载 {localFileStats.pending}</span>
                    <span className={localFileStats.failed > 0 ? 'text-red-600' : ''}>
                      失败 {localFileStats.failed}
                    </span>
                    {remoteFileCount !== undefined && (
                      <span className="text-blue-600">本地/远端 {localFileCount}/{remoteFileCount}</span>
                    )}
                  </div>
                )}
              </div>
            </div>

          </CardContent>
        </ScrollArea>
      </Card>
    </div>
  );
}
