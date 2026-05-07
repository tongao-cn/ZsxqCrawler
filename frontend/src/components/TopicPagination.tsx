'use client';

import { memo } from 'react';

import { Button } from '@/components/ui/button';

interface TopicPaginationProps {
  currentPage: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}

function TopicPagination({ currentPage, totalPages, onPageChange }: TopicPaginationProps) {
  if (totalPages <= 1) {
    return null;
  }

  const goToPage = (page: number) => {
    if (page >= 1 && page <= totalPages) {
      onPageChange(page);
    }
  };

  const restoreInputValue = (input: HTMLInputElement) => {
    input.value = currentPage.toString();
  };

  return (
    <div className="flex-shrink-0 flex items-center justify-center gap-3 pt-4 border-t border-gray-200 mt-4">
      <Button
        variant="outline"
        size="sm"
        onClick={() => goToPage(Math.max(1, currentPage - 1))}
        disabled={currentPage === 1}
      >
        上一页
      </Button>

      <div className="flex items-center gap-2">
        <span className="text-sm text-gray-600">第</span>
        <input
          type="number"
          min="1"
          max={totalPages}
          defaultValue={currentPage}
          key={currentPage}
          onChange={() => {
            // 输入过程中不跳转，保持原交互：Enter 或失焦时再确认页码。
          }}
          onKeyDown={(event) => {
            if (event.key !== 'Enter') {
              return;
            }

            const value = event.currentTarget.value;
            if (value === '') {
              return;
            }

            const page = parseInt(value);
            if (!Number.isNaN(page)) {
              goToPage(page);
            }
          }}
          onBlur={(event) => {
            const value = event.target.value;
            const page = parseInt(value);

            if (value === '' || Number.isNaN(page) || page < 1 || page > totalPages) {
              restoreInputValue(event.target);
              return;
            }

            goToPage(page);
          }}
          className="w-16 px-2 py-1 text-sm text-center border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        />
        <span className="text-sm text-gray-600">页，共 {totalPages} 页</span>
      </div>

      <Button
        variant="outline"
        size="sm"
        onClick={() => goToPage(Math.min(totalPages, currentPage + 1))}
        disabled={currentPage === totalPages}
      >
        下一页
      </Button>
    </div>
  );
}

export default memo(TopicPagination);
