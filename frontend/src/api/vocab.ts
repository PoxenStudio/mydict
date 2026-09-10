import request from './request'
import type { VocabListResponse, VocabItem } from '../types/vocab'

export function listVocab(search?: string, page = 1, pageSize = 20, langFrom?: string) {
  return request.get<never, VocabListResponse>('/vocab', {
    params: { search: search || undefined, page, page_size: pageSize, lang_from: langFrom },
  })
}

export function listVocabLanguages() {
  return request.get<never, string[]>('/vocab/languages')
}

export function addVocab(word: string, dictionaryId?: number, note?: string) {
  return request.post<never, VocabItem>('/vocab', {
    word,
    dictionary_id: dictionaryId,
    note,
  })
}

export function deleteVocab(id: number) {
  return request.delete<never, { ok: boolean }>(`/vocab/${id}`)
}
