import request from './request'
import type { PublicDictionary, QueryHistoryEntry, QueryResponse } from '../types/query'

/**
 * 查询词条。
 *
 * `dictIds` 是只影响本次检索的词典范围（侧边栏勾选），不写库、不影响其他用户与 Token；
 * 传空/不传表示不限制。
 */
export function searchWord(word: string, dictIds?: number[]) {
  const params: Record<string, string> = { word }
  if (dictIds && dictIds.length) params.dict = dictIds.join(',')
  return request.get<never, QueryResponse>('/dict/search', { params })
}

export function listDictionaries() {
  return request.get<never, PublicDictionary[]>('/dict/dictionaries')
}

/**
 * 取单条词条渲染好的 HTML 文档，供隔离 iframe 用 srcdoc 加载。
 *
 * 必须走 axios 取回再塞 srcdoc，而不是让 iframe 直接 src 到这个地址：
 * iframe 导航不会带 Authorization 头，端点就只能匿名开放，会绕过 Token 的
 * 「可用词典」限制。
 */
export function getEntryHtml(dictionaryId: number, word: string) {
  return request.get<never, string>(`/dict/entry/${dictionaryId}`, {
    params: { word },
    responseType: 'text',
  })
}

/**
 * 生词本里那条释义**快照**渲染成的文档。
 * 刻意渲染快照而不是按词典实时取：生词本存的就是收藏当时那份释义，词典后来被删或改
 * 都不该影响它。
 */
export function getVocabEntryHtml(itemId: number) {
  return request.get<never, string>(`/vocab/${itemId}/entry`, { responseType: 'text' })
}

export function getQueryHistory() {
  return request.get<never, { items: QueryHistoryEntry[] }>('/dict/history')
}
