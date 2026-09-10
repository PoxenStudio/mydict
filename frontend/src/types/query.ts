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
