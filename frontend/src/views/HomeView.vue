<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useTheme, type ThemeMode } from '../composables/useTheme'
import { getHealth } from '../api/health'
import { useUserAuthStore } from '../stores/userAuth'

const { theme, setTheme } = useTheme()
const apiStatus = ref('checking...')
const authStore = useUserAuthStore()

const modes: ThemeMode[] = ['light', 'dark', 'system']

onMounted(async () => {
  try {
    const res = await getHealth()
    apiStatus.value = res.status
  } catch {
    apiStatus.value = 'unreachable'
  }
  if (authStore.isLoggedIn && !authStore.profile) {
    authStore.loadProfile().catch(() => undefined)
  }
})
</script>

<template>
  <main class="home">
    <nav class="user-nav">
      <template v-if="authStore.isLoggedIn">
        <span>{{ authStore.profile?.username ?? '...' }}</span>
        <button class="link-btn" type="button" @click="authStore.logout()">退出登录</button>
      </template>
      <template v-else>
        <router-link to="/login">登录</router-link>
        <router-link to="/register">注册</router-link>
      </template>
    </nav>

    <img class="logo" src="/logo.png" alt="MyDict" />
    <h1>MyDict</h1>
    <p class="tagline">词典查询与生词本 · 查询/生词本页面将在 Step 5 实现</p>

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
  position: relative;
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

.user-nav {
  position: absolute;
  top: var(--space-4);
  right: var(--space-5);
  display: flex;
  align-items: center;
  gap: var(--space-3);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.user-nav a {
  color: var(--color-brand-500);
  text-decoration: none;
}

.link-btn {
  border: none;
  background: none;
  color: var(--color-text-secondary);
  cursor: pointer;
  font-size: var(--text-sm);
  padding: 0;
}
</style>
