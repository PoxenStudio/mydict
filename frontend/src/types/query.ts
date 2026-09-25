/** 前台查询结果不带释义：释义走 /dict/entry 渲染进隔离 iframe */
export interface QueryResultItem {
  /** 条目主键。同一部词典里可能有多条同名词条（MDict 允许），用它做 key 与寻址 */
  id: number
  dictionary_id: number
  dictionary_name: string
  word: string
  phonetic: string | null
  extra: Record<string, unknown> | null
  /**
   * 该词典的 lang_from 是否与输入语言一致。false 表示这是「优先语言都没命中、
   * 于是回退到其他语言词典」的结果，界面上要标出来以免误导。
   */
  lang_match?: boolean
}

export interface QueryResponse {
  results: QueryResultItem[]
}

export interface PublicDictionary {
  id: number
  name: string
  lang_from: string
  lang_to: string
}

export interface QueryHistoryEntry {
  word: string
  dictionary_id: number
  dictionary_name: string
  created_at: string
}

/** 在线词典：单个源的结果（wikipedia/baike 是卡片；wiktionary 是按词性分组的释义） */
export interface OnlineSection {
  id: string
  name: string
  title: string | null
  subtitle: string | null
  text: string | null
  url: string | null
  /** wiktionary 专用：词性分组 */
  entries: { pos: string; language: string; senses: { text: string; examples: string[] }[] }[] | null
}

/** 在线词典：外部搜索链接（这些站点拒绝内嵌，给链接打开） */
export interface OnlineLink {
  name: string
  url: string
}

export interface OnlineLookup {
  word: string
  lang: string
  sections: OnlineSection[]
  links: OnlineLink[]
}
