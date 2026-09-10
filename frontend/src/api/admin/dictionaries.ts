import request from '../request'
import type {
  DictionaryItem,
  DictionaryUpdatePayload,
  DictsDirListing,
  ImportFromDictsDirPayload,
  TestQueryEntry,
} from '../../types/dictionary'

export function listDictionaries() {
  return request.get<never, DictionaryItem[]>('/admin/dictionaries')
}

export function uploadDictionary(form: FormData) {
  return request.post<never, DictionaryItem>('/admin/dictionaries', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export function listDictsDirFiles(path = '') {
  return request.get<never, DictsDirListing>('/admin/dictionaries/dicts-dir-files', {
    params: path ? { path } : undefined,
  })
}

export function importFromDictsDir(payload: ImportFromDictsDirPayload) {
  return request.post<never, DictionaryItem>('/admin/dictionaries/import-from-dicts-dir', payload)
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
