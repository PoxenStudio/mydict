export interface ApiTokenItem {
  id: number
  name: string
  token_prefix: string
  daily_limit: number | null
  status: 'active' | 'disabled'
  created_at: string
  last_used_at: string | null
  today_count: number
  total_count: number
}

export interface ApiTokenCreateResponse extends ApiTokenItem {
  token: string
}
