'use client';

import { useCallback, useState } from 'react';
import { toast } from 'sonner';

import { apiClient } from '@/lib/api';

interface UseGroupAccountAssignmentOptions {
  groupId: number;
  selectedAccountId: string;
  loadGroupAccount: () => void | Promise<void>;
  loadGroupAccountSelf: () => void | Promise<void>;
}

export function useGroupAccountAssignment({
  groupId,
  selectedAccountId,
  loadGroupAccount,
  loadGroupAccountSelf,
}: UseGroupAccountAssignmentOptions) {
  const [assigningAccount, setAssigningAccount] = useState<boolean>(false);

  const handleAssignAccount = useCallback(async () => {
    if (!selectedAccountId) {
      toast.error('请选择要绑定的账号');
      return;
    }

    setAssigningAccount(true);
    try {
      await apiClient.assignGroupAccount(groupId, selectedAccountId);
      toast.success('已绑定账号到该群组');
      await loadGroupAccount();
      await loadGroupAccountSelf();
    } catch (error) {
      toast.error('绑定失败');
      console.error('绑定账号失败:', error);
    } finally {
      setAssigningAccount(false);
    }
  }, [groupId, loadGroupAccount, loadGroupAccountSelf, selectedAccountId]);

  return {
    assigningAccount,
    handleAssignAccount,
  };
}
