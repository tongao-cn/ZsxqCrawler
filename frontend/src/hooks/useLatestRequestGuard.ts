'use client';

import { useCallback, useEffect, useRef } from 'react';

export function useLatestRequestGuard() {
  const requestIdRef = useRef(0);

  const nextRequestId = useCallback(() => {
    requestIdRef.current += 1;
    return requestIdRef.current;
  }, []);

  const isLatestRequest = useCallback((requestId: number) => (
    requestIdRef.current === requestId
  ), []);

  const invalidateRequests = useCallback(() => {
    requestIdRef.current += 1;
  }, []);

  useEffect(() => invalidateRequests, [invalidateRequests]);

  return {
    invalidateRequests,
    isLatestRequest,
    nextRequestId,
  };
}
