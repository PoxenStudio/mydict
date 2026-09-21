// 查询侧按 CJK 表意文字识别中文输入，简体/繁体都归到这一类（见后端 query_service.py
// 的 _ZH_LANG_CODES），这里仍分开列出方便管理员准确记录词典本身的文字版本。
export const LANGUAGE_OPTIONS = [
  { label: '简体中文', value: 'zh-Hans' },
  { label: '繁体中文', value: 'zh-Hant' },
  { label: '英文', value: 'en' },
  { label: '日文', value: 'ja' },
]

// 早期数据 lang_from/lang_to 存的是裸 "zh"（不分简繁），仍是合法值，只是不出现在
// 新导入的下拉选项里；这里额外加一条用于把旧数据也显示成中文名而不是原始代码。
const LANGUAGE_LABELS: Record<string, string> = Object.fromEntries([
  ...LANGUAGE_OPTIONS.map((opt) => [opt.value, opt.label]),
  ['zh', '中文'],
])

export function langLabel(code: string) {
  return LANGUAGE_LABELS[code] ?? code
}

/**
 * 中文系的全部 lang_from 取值（含早期数据里的裸 `zh`）。
 *
 * 查询路由本来就不区分简繁——输入汉字时这三种码都算「优先语言」——所以凡是「按中文筛」
 * 的地方都该一次覆盖它们。词典管理页的语种 tab 与前台检索范围的「中文」按钮共用这份定义。
 */
export const ZH_CODES = ['zh', 'zh-Hans', 'zh-Hant']

/** 把某个 lang_from 归到「按语种看词典」用的分组键；简繁都归成 `zh`。 */
export function langGroupOf(code: string): string {
  return ZH_CODES.includes(code) ? 'zh' : code
}

/** 语种分组键的显示名；表里没有的原样返回。 */
const LANG_GROUP_LABELS: Record<string, string> = {
  zh: '中文',
  en: '英文',
  ja: '日文',
}

export function langGroupLabel(group: string) {
  return LANG_GROUP_LABELS[group] ?? group
}
