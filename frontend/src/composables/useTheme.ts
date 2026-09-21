import { ref, watchEffect } from 'vue'

export type ThemeMode = 'light' | 'dark' | 'system'
export type ResolvedTheme = 'light' | 'dark'

const STORAGE_KEY = 'mydict-theme'
const media = window.matchMedia('(prefers-color-scheme: dark)')

const theme = ref<ThemeMode>((localStorage.getItem(STORAGE_KEY) as ThemeMode | null) ?? 'system')
const resolvedTheme = ref<ResolvedTheme>(resolve(theme.value))

function resolve(mode: ThemeMode): ResolvedTheme {
  return mode === 'system' ? (media.matches ? 'dark' : 'light') : mode
}

function setTheme(mode: ThemeMode) {
  theme.value = mode
  if (mode === 'system') {
    localStorage.removeItem(STORAGE_KEY)
  } else {
    localStorage.setItem(STORAGE_KEY, mode)
  }
}

watchEffect(() => {
  resolvedTheme.value = resolve(theme.value)
  document.documentElement.setAttribute('data-theme', resolvedTheme.value)
})

media.addEventListener('change', () => {
  if (theme.value === 'system') {
    resolvedTheme.value = resolve('system')
    document.documentElement.setAttribute('data-theme', resolvedTheme.value)
  }
})

export function useTheme() {
  return { theme, resolvedTheme, setTheme }
}

/**
 * 当前解析后的主题值。
 *
 * 给不持有组件实例的地方用（api 层、工具函数）：它们调 useTheme() 只能拿到 ref，
 * 而请求参数需要的是此刻的值。
 */
export function currentTheme(): ResolvedTheme {
  return resolvedTheme.value
}
