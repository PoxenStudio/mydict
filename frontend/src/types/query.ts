export interface QueryResultItem {
  dictionary_id: number
  dictionary_name: string
  word: string
  phonetic: string | null
  definition: string
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
