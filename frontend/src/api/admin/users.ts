import request from '../request'
import type { AdminUserDetail, AdminUserItem, AdminUserListResponse } from '../../types/adminUser'

export function listUsers(search: string, status: string, page: number, pageSize = 20) {
  return request.get<never, AdminUserListResponse>('/admin/users', {
    params: {
      search: search || undefined,
      status: status || undefined,
      page,
      page_size: pageSize,
    },
  })
}

export function getUserDetail(id: number) {
  return request.get<never, AdminUserDetail>(`/admin/users/${id}`)
}

export function enableUser(id: number) {
  return request.put<never, AdminUserItem>(`/admin/users/${id}/enable`)
}

export function disableUser(id: number) {
  return request.put<never, AdminUserItem>(`/admin/users/${id}/disable`)
}

export function resetUserPassword(id: number) {
  return request.post<never, { temporary_password: string }>(`/admin/users/${id}/reset-password`)
}
