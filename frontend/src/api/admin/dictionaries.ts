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
 * 扫描发音资源：统计各部词典里待转码的 .spx 数并回填。dictionaryIds 留空表示全部词典。
 *
 * 放在后台跑（大词典单部就有几十万个资源文件），返回 task_id 供轮询。
 */
export function scanSpx(dictionaryIds?: number[] | null) {
  return request.post<never, { task_id: number }>('/admin/dictionaries/scan-spx', {
    dictionary_ids: dictionaryIds && dictionaryIds.length ? dictionaryIds : null,
  })
}

/** 批量转码发音；单部传一个 id 走同一个端点。**转成功后后端会删掉原 .spx**。 */
export function transcodeSpx(dictionaryIds: number[]) {
  return request.post<never, { task_id: number }>('/admin/dictionaries/transcode-spx', {
    dictionary_ids: dictionaryIds,
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
