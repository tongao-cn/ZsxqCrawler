export function formatAShareDateTime(value?: string | null) {
  if (!value) {
    return '暂无';
  }
  return new Date(value).toLocaleString('zh-CN');
}

export function formatAShareInputDate(value?: string | null) {
  if (!value) {
    return '';
  }
  return value.slice(0, 10);
}
