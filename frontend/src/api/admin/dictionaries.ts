import request from '../request'
import type {
  DictionaryItem,
  DictionaryStatus,
  DictionaryUpdatePayload,
  DictsDirListing,
  ImportFromDictsDirPayload,
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

export function deleteDictionary(id: number) {
  return request.delete<never, { ok: boolean }>(`/admin/dictionaries/${id}`)
}

export function reorderDictionaries(orderedIds: number[]) {
  return request.put<never, DictionaryItem[]>('/admin/dictionaries/reorder', {
    ordered_ids: orderedIds,
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
    params: { word },
    responseType: 'text',
  })
}
