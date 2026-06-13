import stockConceptTaxonomy from '@/components/stockConceptTaxonomy.json';
import { DailyStockConcept } from '@/lib/api';

export interface ConceptStat {
  concept: string;
  aliases: string[];
  stockNames: string[];
  stockCount: number;
  topicIds: Array<string | number>;
  topicCount: number;
  recommendationHitCount: number;
}

export interface ConceptQualityTag {
  label: string;
  className: string;
}

export const DEFAULT_VISIBLE_CONCEPT_COUNT = 30;

const CONCEPT_ALIAS_GROUPS: Array<{ concept: string; aliases: string[] }> = stockConceptTaxonomy.conceptGroups;

const CONCEPT_ALIAS_MAP = new Map<string, string>(
  CONCEPT_ALIAS_GROUPS.flatMap((group) => [
    [group.concept.toLocaleLowerCase(), group.concept] as [string, string],
    ...group.aliases.map((alias) => [alias.toLocaleLowerCase(), group.concept] as [string, string]),
  ])
);

const SIGNAL_TAG_ALIAS_GROUPS: Array<{ tag: string; aliases: string[] }> = stockConceptTaxonomy.signalTagGroups;

const SIGNAL_TAG_ALIAS_MAP = new Map<string, string>(
  SIGNAL_TAG_ALIAS_GROUPS.flatMap((group) => [
    [group.tag.toLocaleLowerCase(), group.tag] as [string, string],
    ...group.aliases.map((alias) => [alias.toLocaleLowerCase(), group.tag] as [string, string]),
  ])
);

export function getTodayText() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export function formatDateTime(value?: string | null) {
  if (!value) {
    return '暂无';
  }
  return new Date(value).toLocaleString('zh-CN');
}

export function normalizeReportMarkdown(value?: string | null) {
  const content = value || '报告内容为空';
  const headingMap: Record<string, string> = {
    每日话题分析报告: '# 每日话题分析报告',
    一句话结论: '## 一句话结论',
    今日核心洞察: '## 今日核心洞察',
    热点话题: '## 热点话题',
    '热点话题 Top 5': '## 热点话题 Top 5',
    高价值观点与问答: '## 高价值观点与问答',
    需要跟进的机会或风险: '## 需要跟进的机会或风险',
    明日关注点: '## 明日关注点',
    话题索引: '## 话题索引',
  };

  return content
    .split('\n')
    .map((line) => {
      const trimmed = line.trim();
      if (trimmed.startsWith('#')) {
        return line;
      }
      return headingMap[trimmed] || line;
    })
    .join('\n');
}

export function getDateText(offsetDays = 0, baseDate?: string) {
  const date = baseDate ? new Date(`${baseDate}T00:00:00`) : new Date();
  date.setDate(date.getDate() + offsetDays);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export function stockKey(stock: DailyStockConcept) {
  return stock.stock_code || stock.stock_name;
}

export function normalizeCompanyName(value?: string | null) {
  return (value || '')
    .replace(/\s+/g, '')
    .replace(/股份有限公司|有限责任公司|有限公司|集团/g, '');
}

export function normalizeConceptName(value?: string | null) {
  const concept = (value || '').trim();
  return CONCEPT_ALIAS_MAP.get(concept.toLocaleLowerCase()) || concept;
}

export function normalizeSignalTagName(value?: string | null) {
  const tag = (value || '').trim();
  return SIGNAL_TAG_ALIAS_MAP.get(tag.toLocaleLowerCase()) || null;
}

export function classifyStockConceptTerm(value?: string | null): 'concept' | 'signal' | 'unmapped' | 'empty' {
  const term = (value || '').trim();
  if (!term) {
    return 'empty';
  }
  const key = term.toLocaleLowerCase();
  if (SIGNAL_TAG_ALIAS_MAP.has(key)) {
    return 'signal';
  }
  if (CONCEPT_ALIAS_MAP.has(key)) {
    return 'concept';
  }
  return 'unmapped';
}

export function isRisingTrend(counts: number[]) {
  if (counts.length < 3) {
    return false;
  }
  const recent = counts.slice(-3).reduce((sum, count) => sum + count, 0);
  const previous = counts.slice(0, -3).reduce((sum, count) => sum + count, 0);
  return recent >= 3 && recent > previous;
}
