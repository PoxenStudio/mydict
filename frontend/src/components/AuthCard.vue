<script setup lang="ts">
import { useSettingsStore } from '../stores/settings'
import ThemeToggle from './ThemeToggle.vue'

defineProps<{ title: string; subtitle?: string }>()

const settingsStore = useSettingsStore()
</script>

<template>
  <div class="auth-page">
    <!-- 登录页不在导航栏里，这里补一个主题切换，否则这一页无法换主题 -->
    <ThemeToggle class="auth-theme" />
    <div class="auth-card">
      <!-- 登录/注册页原本是一张孤立的白卡，没有任何品牌线索；补一个与导航栏同款的标识 -->
      <router-link to="/" class="brand">
        <img src="/logo.png" alt="" class="brand-logo" />
        <span>{{ settingsStore.siteName }}</span>
      </router-link>
      <h1>{{ title }}</h1>
      <p v-if="subtitle" class="subtitle">{{ subtitle }}</p>
      <slot />
    </div>
  </div>
</template>

<style scoped>
.auth-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-4);
  background: var(--color-bg-base);
}

.auth-theme {
  position: fixed;
  top: var(--space-4);
  right: var(--space-4);
}

.auth-card {
  width: 100%;
  max-width: 360px;
  background: var(--color-bg-surface);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-elevation-2);
  padding: var(--space-6);
}

.brand {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-5);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  font-weight: var(--font-weight-medium);
  text-decoration: none;
}

.brand:hover {
  color: var(--color-text-primary);
}

.brand-logo {
  width: 24px;
  height: 24px;
  border-radius: var(--radius-sm);
}

h1 {
  margin: 0 0 var(--space-2);
  font-size: var(--text-xl);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.subtitle {
  margin: 0 0 var(--space-5);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}
</style>
