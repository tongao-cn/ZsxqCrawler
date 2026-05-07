'use client';

import { Dispatch, SetStateAction, useEffect, useState } from 'react';

interface UseDebouncedSearchOptions {
  delay?: number;
  onDebouncedChange?: (value: string) => void;
}

export function useDebouncedSearch({
  delay = 300,
  onDebouncedChange,
}: UseDebouncedSearchOptions = {}) {
  const [searchTerm, setSearchTerm] = useState('');
  const [debouncedSearchTerm, setDebouncedSearchTerm] = useState('');

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const nextValue = searchTerm.trim();
      setDebouncedSearchTerm(nextValue);
      onDebouncedChange?.(nextValue);
    }, delay);

    return () => {
      window.clearTimeout(timer);
    };
  }, [delay, onDebouncedChange, searchTerm]);

  return {
    searchTerm,
    setSearchTerm: setSearchTerm as Dispatch<SetStateAction<string>>,
    debouncedSearchTerm,
  };
}
