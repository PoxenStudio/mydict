import request from '../request'
import type { ApiTokenCreateResponse, ApiTokenItem } from '../../types/token'

export function listTokens() {
  return request.get<never, ApiTokenItem[]>('/admin/tokens')
}

export function createToken(
  name: string,
  dailyLimit: number | null,
  allowedDictionaryIds: number[] | null = null,
) {
  return request.post<never, ApiTokenCreateResponse>('/admin/tokens', {
    name,
    daily_limit: dailyLimit,
    allowed_dictionary_ids: allowedDictionaryIds,
  })
}

export function setTokenAllowedDictionaries(id: number, dictionaryIds: number[] | null) {
  return request.put<never, ApiTokenItem>(`/admin/tokens/${id}/allowed-dictionaries`, {
    dictionary_ids: dictionaryIds,
  })
}

export function enableToken(id: number) {
  return request.put<never, ApiTokenItem>(`/admin/tokens/${id}/enable`)
}

export function disableToken(id: number) {
  return request.put<never, ApiTokenItem>(`/admin/tokens/${id}/disable`)
}

export function regenerateToken(id: number) {
  return request.post<never, ApiTokenCreateResponse>(`/admin/tokens/${id}/regenerate`)
}

export function getTokenVocabCount(id: number) {
  return request.get<never, { count: number }>(`/admin/tokens/${id}/vocab-count`)
}

/** 删除 Token（查询日志/统计保留但匿名化，生词本随级联清理）。 */
export function deleteToken(tokenId: number) {
  return request.delete<never, void>(`/admin/tokens/${tokenId}`)
}
