import { computed, type Ref } from 'vue'
import type { PublicDictionary } from '../types/query'
import { ZH_CODES, langLabel } from '../utils/language'

// 中文系（含早期数据里的裸 zh）在界面上合成一个按钮：查询路由本来就不区分简繁
// （输入汉字时三种码都算「优先语言」），拆成两个按钮只会让「只看中文词典」要点两次。
// 中文按钮的循环顺序：中文（全部）→ 简中 → 繁中 → 中文…
const ZH_SCOPES = ['zh', 'zh-Hans', 'zh-Hant']
const ZH_SCOPE_LABELS: Record<string, string> = {
  zh: '中文',
  'zh-Hans': '简中',
  'zh-Hant': '繁中',
}

/** 每个筛选范围对应的 lang_from 取值；不在表里的按原样精确匹配 */
const SCOPE_CODES: Record<string, string[]> = {
  zh: ZH_CODES,
  'zh-Hans': ['zh-Hans'],
  'zh-Hant': ['zh-Hant'],
}

function codesOf(scope: string) {
  return SCOPE_CODES[scope] ?? [scope]
}

/** 检索范围的语言标签：库里出现过的语言、当前勾选命中哪一种、点击后勾选该语言的全部词典。 */
export function useLanguageScopes(options: {
  dictionaries: Ref<PublicDictionary[]>
  checkedIds: Ref<Set<number>>
  isFiltering: Ref<boolean>
  setSelection: (ids: number[]) => void
}) {
  const { dictionaries, checkedIds, isFiltering, setSelection } = options

  /** 库里出现过的语言筛选项，按出现顺序去重；中文系合并成一项 */
  const languageScopes = computed(() => {
    const scopes: string[] = []
    for (const item of dictionaries.value) {
      const scope = ZH_CODES.includes(item.lang_from) ? 'zh' : item.lang_from
      if (!scopes.includes(scope)) scopes.push(scope)
    }
    return scopes
  })

  /** 当前勾选集是否恰好等于某个筛选范围的全部词典 */
  function matchesScope(scope: string): boolean {
    const codes = codesOf(scope)
    const ids = dictionaries.value
      .filter((item) => codes.includes(item.lang_from))
      .map((item) => item.id)
    return (
      ids.length > 0 &&
      ids.length === checkedIds.value.size &&
      ids.every((id) => checkedIds.value.has(id))
    )
  }

  /** 中文按钮当前落在哪一态；不在任何一种中文范围里时为 null（按钮显示默认的「中文」） */
  const activeZhScope = computed<string | null>(() => {
    if (!isFiltering.value) return null
    return ZH_SCOPES.find(matchesScope) ?? null
  })

  /** 当前勾选恰好命中的语言标签；未收窄或是自定义组合时为 null */
  const activeLanguageScope = computed<string | null>(() => {
    if (!isFiltering.value) return null
    return languageScopes.value.find(matchesScope) ?? null
  })

  function scopeLabel(scope: string): string {
    return scope === 'zh' ? ZH_SCOPE_LABELS[activeZhScope.value ?? 'zh'] : langLabel(scope)
  }

  /** 勾选该筛选范围下的全部词典；中文按钮在三种范围之间循环 */
  function selectScope(scope: string) {
    let target = scope
    if (scope === 'zh') {
      const index = activeZhScope.value ? ZH_SCOPES.indexOf(activeZhScope.value) : -1
      target = ZH_SCOPES[(index + 1) % ZH_SCOPES.length]
    }
    const codes = codesOf(target)
    setSelection(
      dictionaries.value.filter((item) => codes.includes(item.lang_from)).map((i) => i.id),
    )
  }

  return { languageScopes, activeLanguageScope, scopeLabel, selectScope }
}
