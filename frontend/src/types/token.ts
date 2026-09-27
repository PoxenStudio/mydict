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
  allowed_dictionary_ids: number[] | null
  /** 用户 Token 的所属用户；普通 Token 为 null */
  user_id: number | null
  username: string | null
}

export interface ApiTokenCreateResponse extends ApiTokenItem {
  token: string
}
