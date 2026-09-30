import type { VocabItem } from './vocab'

export interface AdminUserItem {
  id: number
  username: string
  email: string | null
  status: 'active' | 'disabled'
  created_at: string
  last_login_at: string | null
  vocab_count: number
  query_count: number
  /** 可用词典，null 为不限制 */
  allowed_dictionary_ids: number[] | null
  /** 用户 Token 明文（以该用户身份调用对外 API），没有时为 null */
  api_token: string | null
}

export interface AdminUserListResponse {
  items: AdminUserItem[]
  total: number
  page: number
  page_size: number
}

export interface AdminUserCreateResponse {
  user: AdminUserItem
  temporary_password: string
}

export interface QueryLogEntry {
  word: string
  status: string | null
  dictionary_id: number | null
  duration_ms: number | null
  created_at: string
}

export interface AdminUserDetail {
  user: AdminUserItem
  vocab_items: VocabItem[]
  recent_queries: QueryLogEntry[]
}

export interface AdminUserDeleteResult {
  username: string
  tokens: number
  vocab: number
  queries: number
  stats: number
}
