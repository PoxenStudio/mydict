<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useTheme, type ThemeMode } from '../composables/useTheme'
import { getHealth } from '../api/health'

const { theme, setTheme } = useTheme()
const apiStatus = ref('checking...')

const modes: ThemeMode[] = ['light', 'dark', 'system']

onMounted(async () => {
  try {
    const res = await getHealth()
    apiStatus.value = res.status
  } catch {
    apiStatus.value = 'unreachable'
  }
})
</script>

<template>
  <main class="home">
    <img class="logo" src="/logo.png" alt="MyDict" />
    <h1>MyDict</h1>
    <p class="tagline">词典查询与生词本 · 占位页（Step 0）</p>

    <div class="theme-switch">
      <button
        v-for="mode in modes"
        :key="mode"
        class="theme-btn"
        :class="{ active: theme === mode }"
        type="button"
        @click="setTheme(mode)"
      >
        {{ mode }}
      </button>
    </div>

    <p class="api-status">/api/health: {{ apiStatus }}</p>
  </main>
</template>

<style scoped>
.home {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-4);
  text-align: center;
}

.logo {
  width: 64px;
  height: 64px;
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-elevation-2);
}

h1 {
  font-size: var(--text-3xl);
  font-weight: var(--font-weight-bold);
  color: var(--color-text-primary);
  margin: 0;
}

.tagline {
  color: var(--color-text-secondary);
  margin: 0;
}

.theme-switch {
  display: flex;
  gap: var(--space-2);
  padding: var(--space-2);
  background: var(--color-bg-surface);
  border-radius: var(--radius-full);
  box-shadow: var(--shadow-elevation-1);
}

.theme-btn {
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-full);
  font-size: var(--text-sm);
  cursor: pointer;
}

.theme-btn.active {
  background: var(--color-brand-500);
  color: #fff;
}

.api-status {
  font-size: var(--text-sm);
  color: var(--color-text-tertiary);
}
</style>
