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
}

export interface ImportFromDictsDirPayload {
  name: string
  format: DictionaryFormat
  lang_from: string
  lang_to: string
  files: string[]
}

export interface TestQueryEntry {
  word: string
  phonetic: string | null
  definition: string
  extra: Record<string, unknown> | null
}
