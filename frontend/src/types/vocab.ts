export interface VocabItem {
  id: number
  word: string
  phonetic: string | null
  definition: string | null
  note: string | null
  dictionary_id: number | null
  /** 来源词典名快照（词典被删后仍有值） */
  dictionary_name: string | null
  created_at: string
  /** 复习调度：下次到期（UTC ISO），新词为 null */
  due_at: string | null
  /** 已复习次数，0 表示新词 */
  reps: number
  lapses: number
  last_review_at: string | null
}

export interface VocabListResponse {
  items: VocabItem[]
  total: number
  page: number
  page_size: number
}

export type VocabSort = 'word' | 'date'
export type SortOrder = 'asc' | 'desc'

export interface VocabCounts {
  total: number
  new: number
  due: number
}

export interface VocabDueResponse {
  items: VocabItem[]
  counts: VocabCounts
}

export interface VocabReviewResponse {
  item: VocabItem
  counts: VocabCounts
}

export interface VocabStats extends VocabCounts {
  learned: number
  reviewed_today: number
  scheduled_total: number
}
