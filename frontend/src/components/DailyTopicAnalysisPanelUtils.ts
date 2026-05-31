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

const CONCEPT_ALIAS_GROUPS: Array<{ concept: string; aliases: string[] }> = [
  {
    concept: '机器人',
    aliases: ['人形机器人', '具身智能', 'Optimus', 'Optimus V3', '特斯拉Optimus', 'T链', 't链', 'T/S链', '机器人零部件', '机器人整机', '汽车零部件', '总成', '结构件', '塑料件', '减速器', '谐波减速器', '丝杠', '灵巧手', '传感器', '微型丝杠', '机器人传动部件', '行星滚柱丝杠', '核心传动部件', '滚珠丝杠'],
  },
  {
    concept: '物理AI',
    aliases: ['物理AI', '物理ai'],
  },
  {
    concept: 'AI算力/数据中心',
    aliases: ['AI', '算力', 'AI算力', '算力基建', 'AI基建', 'AIDC', 'AI数据中心', '数据中心', 'AI服务器'],
  },
  {
    concept: '电源/HVDC',
    aliases: ['AI电源', 'AIDC电源', '中压UPS', 'UPS', 'HVDC', 'SST', '高压直流', '服务器电源', '电源', 'AIDC供配电', '供配电'],
  },
  {
    concept: 'CPU产业链',
    aliases: ['CPU', '国产CPU', 'CPU涨价', '服务器CPU', '数据中心CPU', 'CPU算力', 'x86'],
  },
  {
    concept: 'AI芯片/GPU',
    aliases: ['GPU', '合封GPU', 'ASIC', 'AI芯片', '国产GPU'],
  },
  {
    concept: '存储产业链',
    aliases: ['存储', '存储产业链', '长江存储产业链', '长江存储上市', '存储扩产', '存储链', '利基存储', '长鑫存储', '长鑫', '国产存储', '长存产业链', '存储芯片', 'DRAM', 'HBM', 'MRDIMM'],
  },
  {
    concept: '半导体设备/先进封装',
    aliases: ['半导体设备', '先进封装', '先进封测', '半导体先进封装', 'CoWoS'],
  },
  {
    concept: '半导体材料/硅片',
    aliases: ['半导体材料', '半导体硅片', '12英寸硅片', '电子材料', '先进硅片', '大硅片', '12寸硅片', '硅片', 'SOI硅片', '抛光硅片'],
  },
  {
    concept: 'SiC/功率半导体',
    aliases: ['SiC', '碳化硅', '功率半导体', '碳化硅衬底', '第三代半导体', '功率器件'],
  },
  {
    concept: '玻璃基板/载板',
    aliases: ['玻璃基板', '玻璃基载板', '玻璃载板', '玻璃基封装基板', '玻璃基封装载板', '玻璃基板TGV', 'TGV玻璃基板', 'TGV玻璃基板设备', 'ABF载板', 'IC载板', '封装基板', '载板'],
  },
  {
    concept: '电力/变压器',
    aliases: ['固态变压器', '电力设备', '电力电子', '变压器', '高频变压器', '微电网技术', '电网设备', '高压设备', '电网智能化'],
  },
  {
    concept: '储能',
    aliases: ['储能', '户储', '光储', '大储', '工商储', '储能逆变器', '逆变器'],
  },
  {
    concept: '绿电',
    aliases: ['绿电'],
  },
  {
    concept: '光伏/HJT',
    aliases: ['光伏', '光伏设备', '钙钛矿', 'HJT', '光伏辅材', '光伏胶膜', 'HJT设备', 'HJT电池', '光伏组件', '光伏电池'],
  },
  {
    concept: '锂电/电池',
    aliases: ['锂电', '锂电材料', '电池', '固态电池', '磷酸铁锂'],
  },
  {
    concept: '光通信/CPO',
    aliases: ['光模块', '光通信', '光互联', '光互连', 'CPO', '光芯片', '硅光', 'Micro LED光互联', '短距光互联', 'MPO', 'NPO', 'OCS', '1.6T', '1.6T光模块', '800G', '3.2T', '光器件', '光模块设备', 'DSP', 'EML', '光纤', '通信'],
  },
  {
    concept: '液冷/热管理',
    aliases: ['液冷', 'AI液冷', 'AIDC液冷', '数据中心液冷', '液冷板', '液冷散热', '液冷产业链', '热管理', '冷却塔'],
  },
  {
    concept: 'PCB',
    aliases: ['PCB', 'AI PCB', 'AI设备及耗材', '光模块mSAP PCB', 'PCB钻针', 'AI PCB钻针', 'PCB高端钻针', 'PCB高端铣刀', '金刚石涂层PCB钻针', 'PCB专用设备', 'PCB曝光设备', 'PCB高端设备'],
  },
  {
    concept: 'CCL',
    aliases: ['CCL', '高端CCL', 'CCL上游材料', '电子布', 'Q布', '正交背板'],
  },
  {
    concept: '铜箔',
    aliases: ['铜箔', '高端铜箔', '载体铜箔', 'HVLP4/5铜箔', 'HVLP5铜箔', 'RCC铜箔', '铜箔设备'],
  },
  {
    concept: '商业航天/卫星',
    aliases: ['商业航天', '空天行业', '低轨卫星星座', '卫星', '卫星互联网', '太空算力', '太空光伏', 'SpaceX', 'SpaceX产业链', 'SpaceX IPO催化', '火箭'],
  },
  {
    concept: '燃机/SOFC',
    aliases: ['SOFC', '燃气轮机', '燃机', '固体氧化物燃料电池'],
  },
];

const CONCEPT_ALIAS_MAP = new Map<string, string>(
  CONCEPT_ALIAS_GROUPS.flatMap((group) => [
    [group.concept.toLocaleLowerCase(), group.concept] as [string, string],
    ...group.aliases.map((alias) => [alias.toLocaleLowerCase(), group.concept] as [string, string]),
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

export function isRisingTrend(counts: number[]) {
  if (counts.length < 3) {
    return false;
  }
  const recent = counts.slice(-3).reduce((sum, count) => sum + count, 0);
  const previous = counts.slice(0, -3).reduce((sum, count) => sum + count, 0);
  return recent >= 3 && recent > previous;
}
