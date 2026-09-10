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
