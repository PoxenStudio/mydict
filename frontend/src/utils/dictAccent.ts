// 顺序与数量即分配规则：调整顺序或增减颜色都会让已有词典重新分配颜色
const DICT_ACCENT_KEYS = [
  'marine',
  'velvet',
  'night-blue',
  'green',
  'yellow',
  'red',
  'purple',
  'orange',
  'olive',
  'brown',
] as const

export function dictAccentColor(dictionaryId: number | null | undefined) {
  if (dictionaryId == null) return undefined
  const index = Math.abs(dictionaryId) % DICT_ACCENT_KEYS.length
  return `var(--color-dict-${DICT_ACCENT_KEYS[index]})`
}
