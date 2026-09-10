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
