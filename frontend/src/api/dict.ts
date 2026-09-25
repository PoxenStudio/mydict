import request from './request'
import { currentTheme } from '../composables/useTheme'
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
 * 取词条渲染好的 HTML 文档，供隔离 iframe 用 srcdoc 加载。
 *
 * 同一部词典里同一词头可以有多条内容不同的条目（MDict 允许），这时整组条目会聚合进
 * **一个**文档返回——逐条各建 iframe 的话，搜韵这类词典展开一次就要挂载 82 个沙箱文档。
 * `entryIds` 用来告诉后端这一组是哪些条目（查询结果里带回了 id），不传则后端按词的
 * 变体集合取（兼容单条与旧调用）。传 `entryIds` 时 `word` 必须是用户查询输入的词：
 * 后端只在它的变体范围内认这些 id。
 *
 * 必须走 axios 取回再塞 srcdoc，而不是让 iframe 直接 src 到这个地址：
 * iframe 导航不会带 Authorization 头，端点就只能匿名开放，会绕过 Token 的
 * 「可用词典」限制。
 */
export function getEntryHtml(dictionaryId: number, word: string, entryIds?: number[]) {
  // 带上主题：明暗直接写进文档，iframe 首屏就不会先白一下再变色
  return request.get<never, string>(`/dict/entry/${dictionaryId}`, {
    params: {
      word,
      entry_ids: entryIds && entryIds.length > 1 ? entryIds.join(',') : undefined,
      theme: currentTheme(),
    },
    responseType: 'text',
  })
}

/**
 * 生词本里那条释义**快照**渲染成的文档。
 * 刻意渲染快照而不是按词典实时取：生词本存的就是收藏当时那份释义，词典后来被删或改
 * 都不该影响它。
 */
export function getVocabEntryHtml(itemId: number) {
  return request.get<never, string>(`/vocab/${itemId}/entry`, {
    params: { theme: currentTheme() },
    responseType: 'text',
  })
}

export function getQueryHistory() {
  return request.get<never, { items: QueryHistoryEntry[] }>('/dict/history')
}
