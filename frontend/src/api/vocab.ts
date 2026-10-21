import request from './request'
import type {
  SortOrder,
  VocabDueResponse,
  VocabItem,
  VocabListResponse,
  VocabReviewResponse,
  VocabSort,
  VocabStats,
} from '../types/vocab'

export function listVocab(
  search?: string,
  page = 1,
  pageSize = 20,
  langFrom?: string,
  sort?: VocabSort,
  order?: SortOrder,
) {
  return request.get<never, VocabListResponse>('/vocab', {
    params: {
      search: search || undefined,
      page,
      page_size: pageSize,
      lang_from: langFrom,
      sort,
      order,
    },
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

/** 本次要复习的卡片（到期优先，不够用新词补） */
export function getDueVocab(limit = 20, newLimit = 10) {
  return request.get<never, VocabDueResponse>('/vocab/due', {
    params: { limit, new_limit: newLimit },
  })
}

/** 提交一次评分：1=Again 2=Hard 3=Good 4=Easy */
export function reviewVocab(
  id: number,
  rating: number,
  options: { reviewedAt?: string; client?: string; clientReviewId?: string } = {},
) {
  return request.post<never, VocabReviewResponse>(`/vocab/${id}/review`, {
    rating,
    reviewed_at: options.reviewedAt,
    client: options.client ?? 'web',
    client_review_id: options.clientReviewId,
  })
}

export function getVocabStats() {
  return request.get<never, VocabStats>('/vocab/stats')
}
