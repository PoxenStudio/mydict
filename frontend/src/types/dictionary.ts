export type DictionaryFormat = 'mdict' | 'stardict' | 'ecdict'
export type DictionaryStatus = 'enabled' | 'disabled'
export type DictionaryImportMethod = 'upload' | 'dicts_dir'

export interface DictionaryItem {
  id: number
  name: string
  format: DictionaryFormat
  lang_from: string
  lang_to: string
  word_count: number
  sort_order: number
  status: DictionaryStatus
  import_method: DictionaryImportMethod
  imported_at: string
}

export interface DictsDirFile {
  name: string
  size: number
  modified_at: string
  imported: boolean
  is_dir: boolean
}

export interface DictsDirGroupFile {
  name: string
  relpath: string
  size: number
  imported: boolean
}

// 服务端把当前目录下的文件按 (格式, 主干) 归组出的待导入词典单元
export interface DictsDirGroup {
  key: string
  name: string
  format: DictionaryFormat
  // 该词典所在目录（相对 /data/dicts）；递归扫描时用来区分不同目录下的同名词典
  dir: string
  files: DictsDirGroupFile[]
  total_size: number
  importable: boolean
  reason: string | null
  imported: boolean
}

export interface DictsDirListing {
  path: string
  entries: DictsDirFile[]
  dictionaries: DictsDirGroup[]
  skipped: string[]
}

export interface DictionaryUpdatePayload {
  name: string
  lang_from: string
  lang_to: string
}

// 批量启用/停用
export interface BatchStatusPayload {
  dictionary_ids: number[]
  status: DictionaryStatus
}

// lang_from/lang_to 留空表示由服务端在导入时按词头/释义的文字种类自动识别
// skip_resources 为 true 时只导入释义，不解包 .mdd 里的图片/发音
export interface ImportFromDictsDirPayload {
  name: string
  format: DictionaryFormat
  lang_from?: string
  lang_to?: string
  skip_resources?: boolean
  files: string[]
}

export interface TestQueryEntry {
  word: string
  phonetic: string | null
  definition: string
  extra: Record<string, unknown> | null
}
