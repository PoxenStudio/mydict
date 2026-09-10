export interface QueryResultItem {
  dictionary_id: number
  dictionary_name: string
  word: string
  phonetic: string | null
  definition: string
  extra: Record<string, unknown> | null
}

export interface QueryResponse {
  results: QueryResultItem[]
}

export interface PublicDictionary {
  id: number
  name: string
  lang_from: string
  lang_to: string
}

export interface QueryHistoryEntry {
  word: string
  dictionary_id: number
  dictionary_name: string
  created_at: string
}
