export function formatStockAnalysisDateTime(value?: string | null) {
  if (!value) {
    return '-';
  }
  try {
    return new Date(value).toLocaleString('zh-CN');
  } catch {
    return value;
  }
}
