import request from './request'
import { currentTheme } from '../composables/useTheme'
import type {
  OnlineLookup,
  PublicDictionary,
  QueryHistoryEntry,
  QueryResponse,
} from '../types/query'

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

/** 在线词典（维基百科/维基词典/百度百科 + 外部搜索链接）。lang 是两位语言码 */
export function lookupOnline(word: string, lang: string) {
  return request.get<never, OnlineLookup>('/dict/online/lookup', { params: { word, lang } })
}

/**
 * 需要登录。`usable`：当前用户能用的词典（首页检索范围）；`all`：全部已启用词典（词典选择弹窗）。
 */
export function listDictionaries(scope: 'usable' | 'all' = 'usable') {
  return request.get<never, PublicDictionary[]>('/dict/dictionaries', { params: { scope } })
}

/**
 * 取词条渲染好的 HTML 文档，供隔离 iframe 用 srcdoc 加载。
 *
 * 同一部词典里同一词头可以有多条内容不同的条目（MDict 允许），这时整组条目会聚合进
 * **一个**文档返回——逐条各建 iframe 的话，搜韵这类词典展开一次就要挂载 82 个沙箱文档。
 * `entryIds` 告诉后端要渲染哪些条目（查询结果里带回的 id，单条也传），保证 iframe 里的内容
 * 与结果列表一一对应。`word` 是用户查询输入的词：后端只在它的变体及前缀范围内认这些 id
 * （搜索有前缀兜底，命中的词头如「あ【亜】」以查询词开头但不是它的等价变体）；
 * id 都对不上（词典被重新解析过、条目 id 已换新）时后端退回按词取。
 *
 * 必须走 axios 取回再塞 srcdoc，而不是让 iframe 直接 src 到这个地址：
 * iframe 导航不会带 Authorization 头，端点就只能匿名开放，会绕过 Token 的
 * 「可用词典」限制。
 */
export function getEntryHtml(dictionaryId: number, word: string, entryIds?: number[]) {
  const key = `${dictionaryId}|${word}|${entryIds && entryIds.length ? entryIds.join(',') : ''}`
  const cached = ENTRY_HTML_CACHE.get(key)
  if (cached) {
    // LRU 触碰：命中就挪到队尾，最旧的先淘汰
    ENTRY_HTML_CACHE.delete(key)
    ENTRY_HTML_CACHE.set(key, cached)
    return cached
  }
  const pending = request.get<never, string>(`/dict/entry/${dictionaryId}`, {
    params: {
      word,
      entry_ids: entryIds && entryIds.length ? entryIds.join(',') : undefined,
      theme: currentTheme(),
    },
    responseType: 'text',
  })
  ENTRY_HTML_CACHE.set(key, pending)
  // 失败的预取别留在缓存里，用户真点开时还能重试
  pending.catch(() => ENTRY_HTML_CACHE.delete(key))
  if (ENTRY_HTML_CACHE.size > ENTRY_HTML_CACHE_MAX) {
    const oldest = ENTRY_HTML_CACHE.keys().next().value
    if (oldest !== undefined) ENTRY_HTML_CACHE.delete(oldest)
  }
  return pending
}

// 词条文档预取缓存：悬停/按下面板标题时就把文档拉回来，点击展开时 HTML 已在手，
// iframe 立即挂载——首屏等待里最大的可消除项就是这次往返。
// 主题不在 key 里：缓存文档带着取回时的主题，父页在 iframe load 后会补发当前主题
// （EntryFrame.postTheme），引导脚本的 applyTheme 会自行切换。
const ENTRY_HTML_CACHE = new Map<string, Promise<string>>()
const ENTRY_HTML_CACHE_MAX = 24

/** 后台预取词条文档（悬停/按下时调用）；失败静默，等真正展开时再走正常重试路径 */
export function prefetchEntryHtml(dictionaryId: number, word: string, entryIds?: number[]) {
  getEntryHtml(dictionaryId, word, entryIds).catch(() => undefined)
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
