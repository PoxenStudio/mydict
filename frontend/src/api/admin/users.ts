import request from '../request'
import type {
  AdminUserCreateResponse,
  AdminUserDeleteResult,
  AdminUserDetail,
  AdminUserItem,
  AdminUserListResponse,
} from '../../types/adminUser'

export function createUser(username: string, email?: string) {
  return request.post<never, AdminUserCreateResponse>('/admin/users', {
    username,
    email: email || undefined,
  })
}

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

/** 设置用户的「可用词典」，null 为不限制 */
export function setUserAllowedDictionaries(id: number, dictionaryIds: number[] | null) {
  return request.put<never, AdminUserItem>(`/admin/users/${id}/allowed-dictionaries`, {
    dictionary_ids: dictionaryIds,
  })
}

/** 生成用户 Token（已有则重新生成，旧值立即失效） */
export function generateUserToken(id: number) {
  return request.post<never, AdminUserItem>(`/admin/users/${id}/token`)
}

export function deleteUserToken(id: number) {
  return request.delete<never, AdminUserItem>(`/admin/users/${id}/token`)
}

/** 删除用户，连同他的 Token、生词本与查询记录 */
export function deleteUser(id: number) {
  return request.delete<never, AdminUserDeleteResult>(`/admin/users/${id}`)
}
