import request from '../request'
import { currentTheme } from '../../composables/useTheme'
import type {
  DictionaryItem,
  DictionaryStatus,
  DictionaryUpdatePayload,
  DictsDirListing,
  ImportFromDictsDirPayload,
  RenameDictionariesPayload,
  RenameDictionariesResult,
  TestQueryEntry,
} from '../../types/dictionary'

export function listDictionaries() {
  return request.get<never, DictionaryItem[]>('/admin/dictionaries')
}

export function uploadDictionary(form: FormData) {
  return request.post<never, { task_id: number }>('/admin/dictionaries', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export function listDictsDirFiles(path = '', recursive = false) {
  const params: Record<string, string | boolean> = {}
  if (path) params.path = path
  if (recursive) params.recursive = true
  return request.get<never, DictsDirListing>('/admin/dictionaries/dicts-dir-files', {
    params: Object.keys(params).length ? params : undefined,
  })
}

export function importFromDictsDir(payload: ImportFromDictsDirPayload) {
  return request.post<never, { task_id: number }>(
    '/admin/dictionaries/import-from-dicts-dir',
    payload,
  )
}

export function updateDictionary(id: number, payload: DictionaryUpdatePayload) {
  return request.put<never, DictionaryItem>(`/admin/dictionaries/${id}`, payload)
}

export function enableDictionary(id: number) {
  return request.put<never, DictionaryItem>(`/admin/dictionaries/${id}/enable`)
}

export function disableDictionary(id: number) {
  return request.put<never, DictionaryItem>(`/admin/dictionaries/${id}/disable`)
}

export function setBatchStatus(dictionaryIds: number[], status: DictionaryStatus) {
  return request.put<never, DictionaryItem[]>('/admin/dictionaries/batch-status', {
    dictionary_ids: dictionaryIds,
    status,
  })
}

/**
 * 按正则批量重命名词典。
 *
 * dry_run=true 只返回「原名称 → 新名称」的对照表、不写库，用来先看一遍结果；
 * 确认后再以 dry_run=false 调一次真正落库。响应只含会被改名的条目。
 */
export function renameDictionaries(payload: RenameDictionariesPayload) {
  return request.post<never, RenameDictionariesResult>('/admin/dictionaries/rename', payload)
}

export function deleteDictionary(id: number) {
  return request.delete<never, { ok: boolean }>(`/admin/dictionaries/${id}`)
}

export function reorderDictionaries(orderedIds: number[]) {
  return request.put<never, DictionaryItem[]>('/admin/dictionaries/reorder', {
    ordered_ids: orderedIds,
  })
}

/**
 * 从源文件修复：把「只存在于源文件里、导入时被漏掉的东西」补进已导入的词典。
 *
 * 两件事：① 补 .mdx 同级的 CSS/字体/JS/图片（MDict 按惯例把它们放在 .mdx 旁边而不是
 * .mdd 里，早先的导入只解包 .mdd，于是存量词典全都缺——图标按原始像素渲染、表格丢边框）；
 * ② 展开词条里的 `` `编号` `` 样式标记（规则来自 .mdx 头部的 StyleSheet，此前没处理，
 * 标记原样显示看起来就是排版错乱）。都不需要重新导入。dictionaryIds 留空表示全部词典。
 */
export function repairFromSource(dictionaryIds?: number[] | null) {
  return request.post<never, { task_id: number }>('/admin/dictionaries/repair-from-source', {
    dictionary_ids: dictionaryIds && dictionaryIds.length ? dictionaryIds : null,
  })
}

/**
 * 重新解析：重读源文件、把词条整个重灌一遍（词典 id 不变）。
 * 给「同名词词条曾被按词头去重丢掉」的存量词典找回内容——约束去掉后已入库的行不会自动
 * 长出来。dictionaryIds 留空表示全部词典；源文件不在的会被跳过并计数。
 */
export function reparseDictionaries(dictionaryIds?: number[] | null) {
  return request.post<never, { task_id: number }>('/admin/dictionaries/reparse', {
    dictionary_ids: dictionaryIds && dictionaryIds.length ? dictionaryIds : null,
  })
}

export function testQuery(id: number, word: string) {
  return request.get<never, TestQueryEntry[]>(`/admin/dictionaries/${id}/test-query`, {
    params: { word },
  })
}

/**
 * 管理端预览的单条词条文档，供「测试查询」弹窗放进隔离 iframe。
 * 与前台 /dict/entry/{id} 的区别是不检查启用状态——测试对象常常正是还没启用的词典。
 */
export function getEntryHtml(id: number, word: string) {
  return request.get<never, string>(`/admin/dictionaries/${id}/entry`, {
    params: { word, theme: currentTheme() },
    responseType: 'text',
  })
}
