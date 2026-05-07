'use client';

import { useEffect } from 'react';

interface UseInitialLoadOptions {
  loaders: Array<() => void | Promise<void>>;
}

export function useInitialLoad({ loaders }: UseInitialLoadOptions) {
  useEffect(() => {
    for (const load of loaders) {
      void load();
    }
  }, [loaders]);
}
