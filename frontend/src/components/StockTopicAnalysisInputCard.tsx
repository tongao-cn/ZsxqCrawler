'use client';

import type { ChangeEvent, ClipboardEvent, KeyboardEvent, RefObject } from 'react';
import { ImagePlus, Search, Sparkles } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';

interface StockTopicAnalysisInputCardProps {
  analyzeButtonLabel: string;
  analyzing: boolean;
  extractingImage: boolean;
  imageInputRef: RefObject<HTMLInputElement>;
  maxStockCount: number;
  onAnalyze: () => void;
  onImageSelected: (event: ChangeEvent<HTMLInputElement>) => void;
  onImageUploadClick: () => void;
  onSearch: () => void;
  onStockInputChange: (value: string) => void;
  onStockInputKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => void;
  onStockInputPaste: (event: ClipboardEvent<HTMLTextAreaElement>) => void;
  parsedStockCount: number;
  searching: boolean;
  stockInput: string;
  taskActive: boolean;
}

export default function StockTopicAnalysisInputCard({
  analyzeButtonLabel,
  analyzing,
  extractingImage,
  imageInputRef,
  maxStockCount,
  onAnalyze,
  onImageSelected,
  onImageUploadClick,
  onSearch,
  onStockInputChange,
  onStockInputKeyDown,
  onStockInputPaste,
  parsedStockCount,
  searching,
  stockInput,
  taskActive,
}: StockTopicAnalysisInputCardProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>个股分析</CardTitle>
        <CardDescription>输入多只股票，查询已保存结果；没有结果可初始化，有新话题可增量更新</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <input
          ref={imageInputRef}
          type="file"
          accept="image/png,image/jpeg,image/webp"
          className="hidden"
          onChange={onImageSelected}
        />
        <Textarea
          value={stockInput}
          onChange={(event) => onStockInputChange(event.target.value)}
          onPaste={onStockInputPaste}
          onKeyDown={onStockInputKeyDown}
          placeholder={'例如：德龙激光、宁德时代\n中际旭创 贵州茅台'}
          className="min-h-24 resize-y"
        />
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="text-sm text-muted-foreground">
            已识别 {parsedStockCount}/{maxStockCount} 只，自动去重
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              onClick={onImageUploadClick}
              disabled={extractingImage}
            >
              <ImagePlus className="mr-2 h-4 w-4" />
              {extractingImage ? '识别中...' : '图片提取'}
            </Button>
            <Button variant="outline" onClick={onSearch} disabled={searching || parsedStockCount === 0}>
              <Search className="mr-2 h-4 w-4" />
              {searching ? '搜索中...' : '搜索'}
            </Button>
            <Button onClick={onAnalyze} disabled={analyzing || taskActive || parsedStockCount === 0}>
              <Sparkles className="mr-2 h-4 w-4" />
              {analyzeButtonLabel}
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
