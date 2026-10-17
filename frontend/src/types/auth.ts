export interface TokenPairResponse {
  access_token: string
  // 网页端刷新时服务端不回显（凭证只存 HttpOnly cookie），这里允许为 null
  refresh_token: string | null
  token_type: string
}

export interface UserPublic {
  id: number
  username: string
  email: string | null
  status: string
  allowed_dictionary_ids: number[] | null
}

export interface AdminPublic {
  id: number
  username: string
}
