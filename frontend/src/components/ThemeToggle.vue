<script setup lang="ts">
import { useTheme, type ThemeMode } from '../composables/useTheme'

const { theme, setTheme } = useTheme()

const modes: { value: ThemeMode; label: string }[] = [
  { value: 'light', label: '浅色' },
  { value: 'dark', label: '深色' },
  { value: 'system', label: '跟随系统' },
]

function cycle() {
  const index = modes.findIndex((m) => m.value === theme.value)
  setTheme(modes[(index + 1) % modes.length].value)
}
</script>

<template>
  <button
    type="button"
    class="theme-toggle"
    :aria-label="`切换主题，当前：${modes.find((m) => m.value === theme)?.label}`"
    :title="modes.find((m) => m.value === theme)?.label"
    @click="cycle"
  >
    <svg
      v-if="theme === 'light'"
      viewBox="0 0 24 24"
      width="18"
      height="18"
      fill="none"
      stroke="currentColor"
      stroke-width="2"
    >
      <circle cx="12" cy="12" r="4" />
      <path
        stroke-linecap="round"
        d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"
      />
    </svg>
    <svg
      v-else-if="theme === 'dark'"
      viewBox="0 0 24 24"
      width="18"
      height="18"
      fill="none"
      stroke="currentColor"
      stroke-width="2"
    >
      <path
        stroke-linecap="round"
        stroke-linejoin="round"
        d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5Z"
      />
    </svg>
    <svg
      v-else
      viewBox="0 0 24 24"
      width="18"
      height="18"
      fill="none"
      stroke="currentColor"
      stroke-width="2"
    >
      <rect x="3" y="5" width="18" height="13" rx="2" />
      <path stroke-linecap="round" d="M8 21h8M12 18v3" />
    </svg>
  </button>
</template>

<style scoped>
.theme-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: var(--radius-full);
  border: 1px solid var(--color-border);
  background: var(--color-bg-surface);
  color: var(--color-text-secondary);
  cursor: pointer;
}

.theme-toggle:hover {
  border-color: var(--color-border-hover);
  color: var(--color-text-primary);
}
</style>
