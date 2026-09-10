export interface VocabItem {
  id: number
  word: string
  phonetic: string | null
  definition: string | null
  note: string | null
  dictionary_id: number | null
  created_at: string
}

export interface VocabListResponse {
  items: VocabItem[]
  total: number
  page: number
  page_size: number
}
