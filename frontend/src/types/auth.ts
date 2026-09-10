export interface TokenPairResponse {
  access_token: string
  refresh_token: string
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
