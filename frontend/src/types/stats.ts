export interface StatsOverview {
  today_query_count: number
  active_tokens: number
  active_users: number
  dictionary_count: number
}

export interface StatRow {
  id: number | null
  label: string
  query_count: number
  rate_limited_count: number
}

export interface TopWordRow {
  word: string
  count: number
}

export type StatsDimension = 'token' | 'user' | 'date' | 'source'
