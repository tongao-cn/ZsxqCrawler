'use client';

import { ReactNode } from 'react';

import { TabsContent } from '@/components/ui/tabs';

interface GroupScrollableTabContentProps {
  children: ReactNode;
  value: string;
}

export default function GroupScrollableTabContent({
  children,
  value,
}: GroupScrollableTabContentProps) {
  return (
    <TabsContent value={value} className="flex-1 flex flex-col min-h-0">
      <div className="flex-1 min-h-0 overflow-auto">
        {children}
      </div>
    </TabsContent>
  );
}
