import request from '../request'
import type { AdminPublic, TokenPairResponse } from '../../types/auth'

export function bootstrapStatus() {
  return request.get<never, { initialized: boolean }>('/admin/bootstrap-status')
}

export function setup(username: string, password: string) {
  return request.post<never, TokenPairResponse>('/admin/setup', { username, password })
}

export function login(username: string, password: string) {
  return request.post<never, TokenPairResponse>('/admin/login', { username, password })
}

export function fetchMe() {
  return request.get<never, AdminPublic>('/admin/me')
}
