import type { BackgroundTask } from '../types/backgroundTask'

const TASK_TYPE_LABELS: Record<string, string> = {
  system_migration: '数据库升级',
  dictionary_import: '词典导入',
  dictionary_source_repair: '从源文件修复',
  dictionary_reparse: '重新解析词典',
}

export function taskLabel(task: BackgroundTask) {
  return TASK_TYPE_LABELS[task.task_type] ?? task.task_type
}

export function taskProgressText(task: BackgroundTask) {
  const { done, total, stage } = task.progress_data
  if (
    task.task_type === 'system_migration' &&
    typeof done === 'number' &&
    typeof total === 'number'
  ) {
    return `第 ${Math.min(done + 1, total)}/${total} 步${typeof stage === 'string' ? `：${stage}` : ''}`
  }
  // 修复/重新解析按「已完成 / 总数」报进度；词典导入报的是已写入的词条数，没有总数
  if (typeof done === 'number' && typeof total === 'number' && total > 0) {
    return `已处理 ${done.toLocaleString()} / ${total.toLocaleString()}`
  }
  return typeof done === 'number' ? `已处理 ${done.toLocaleString()} 条` : '处理中…'
}
