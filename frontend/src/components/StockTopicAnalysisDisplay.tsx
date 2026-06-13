import { Badge } from '@/components/ui/badge';
import type { StockTopicAnalysisResponse } from '@/lib/api';

export function formatStockTopicAnalysisDateTime(value?: string | null) {
  if (!value) {
    return '-';
  }
  try {
    return new Date(value).toLocaleString('zh-CN');
  } catch {
    return value;
  }
}

export function getStockTopicAnalysisStatusLabel(result: StockTopicAnalysisResponse) {
  if ((result.new_topic_count ?? 0) > 0 && result.summary_markdown) {
    return `有 ${result.new_topic_count} 条待处理话题`;
  }
  if (result.status === 'failed') {
    return '失败';
  }
  if (result.status === 'missing') {
    return result.topic_count > 0 ? '待分析' : '未保存';
  }
  if (result.summary_markdown) {
    return '已处理';
  }
  if (result.status === 'completed' && result.topic_count <= 0) {
    return '无话题';
  }
  if (result.topic_count > 0) {
    return '待分析';
  }
  return '无话题';
}

export function StockTopicAnalysisStatusBadge({ result }: { result: StockTopicAnalysisResponse }) {
  const label = getStockTopicAnalysisStatusLabel(result);
  if (label.startsWith('有 ')) {
    return <Badge className="bg-blue-100 text-blue-800">{label}</Badge>;
  }
  switch (label) {
    case '已处理':
      return <Badge className="bg-green-100 text-green-800">已处理</Badge>;
    case '待分析':
      return <Badge className="bg-amber-100 text-amber-800">待分析</Badge>;
    case '失败':
      return <Badge className="bg-red-100 text-red-800">失败</Badge>;
    case '无话题':
      return <Badge className="bg-gray-100 text-gray-700">无话题</Badge>;
    default:
      return <Badge variant="secondary">{label}</Badge>;
  }
}
