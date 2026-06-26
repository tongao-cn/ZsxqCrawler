'use client';

import { BarChart3, File, HelpCircle, MessageSquare, Radar, Search, Sparkles, TrendingUp } from 'lucide-react';

import { TabsList, TabsTrigger } from '@/components/ui/tabs';

const GROUP_WORKBENCH_TABS = [
  { value: 'topics', label: '话题列表', Icon: MessageSquare },
  { value: 'research-radar', label: '研究雷达', Icon: Radar },
  { value: 'files', label: '文件', Icon: File },
  { value: 'analysis', label: '股票推荐池', Icon: BarChart3 },
  { value: 'daily-analysis', label: '每日总结', Icon: Sparkles },
  { value: 'stock-concepts', label: '股票概念', Icon: TrendingUp },
  { value: 'stock-topic-analysis', label: '个股分析', Icon: Search },
  { value: 'stock-question', label: 'A股问答', Icon: HelpCircle },
] as const;

export default function GroupWorkbenchTabList() {
  return (
    <div className="flex-shrink-0 mb-4">
      <TabsList className="grid w-full grid-cols-8">
        {GROUP_WORKBENCH_TABS.map(({ value, label, Icon }) => (
          <TabsTrigger key={value} value={value} className="flex items-center gap-2">
            <Icon className="h-4 w-4" />
            {label}
          </TabsTrigger>
        ))}
      </TabsList>
    </div>
  );
}
