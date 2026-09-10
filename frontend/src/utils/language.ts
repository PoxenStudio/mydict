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
