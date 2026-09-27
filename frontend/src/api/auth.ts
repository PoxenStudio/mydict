import request from './request'
import type { TokenPairResponse, UserPublic } from '../types/auth'

export function register(username: string, password: string, email?: string) {
  return request.post<never, UserPublic>('/auth/register', { username, password, email })
}

export function login(username: string, password: string) {
  return request.post<never, TokenPairResponse>('/auth/login', { username, password })
}

export function changePassword(oldPassword: string, newPassword: string) {
  return request.post<never, { ok: boolean }>('/auth/change-password', {
    old_password: oldPassword,
    new_password: newPassword,
  })
}

export function fetchMe() {
  return request.get<never, UserPublic>('/auth/me')
}

export function setAllowedDictionaries(dictionaryIds: number[] | null) {
  return request.put<never, UserPublic>('/auth/allowed-dictionaries', {
    dictionary_ids: dictionaryIds,
  })
}

/** 当前用户自己的 API Token（以本人身份调用对外 API），没有时 api_token 为 null */
export function getApiToken() {
  return request.get<never, { api_token: string | null }>('/auth/api-token')
}

/** 分配 API Token；已有则重新分配，旧值立即失效 */
export function issueApiToken() {
  return request.post<never, { api_token: string }>('/auth/api-token')
}
