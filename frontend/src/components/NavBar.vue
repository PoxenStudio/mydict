<script setup lang="ts">
import { onMounted } from 'vue'
import { useUserAuthStore } from '../stores/userAuth'
import { useSettingsStore } from '../stores/settings'
import ThemeToggle from './ThemeToggle.vue'

const authStore = useUserAuthStore()
const settingsStore = useSettingsStore()

onMounted(() => {
  if (!settingsStore.loaded) settingsStore.load().catch(() => undefined)
  if (authStore.isLoggedIn && !authStore.profile) authStore.loadProfile().catch(() => undefined)
})
</script>

<template>
  <header class="nav-bar">
    <router-link to="/" class="brand">
      <img src="/logo.png" alt="" class="brand-logo" />
      <span>{{ settingsStore.siteName }}</span>
    </router-link>

    <nav class="nav-links">
      <router-link to="/" exact-active-class="active">查询</router-link>
      <router-link to="/vocab" active-class="active">生词本</router-link>
    </nav>

    <div class="nav-actions">
      <ThemeToggle />
      <template v-if="authStore.isLoggedIn">
        <span class="username">{{ authStore.profile?.username ?? '...' }}</span>
        <button class="link-btn" type="button" @click="authStore.logout()">退出</button>
      </template>
      <template v-else>
        <router-link to="/login" class="link-btn">登录</router-link>
        <router-link to="/register" class="link-btn">注册</router-link>
      </template>
    </div>
  </header>
</template>

<style scoped>
.nav-bar {
  display: flex;
  align-items: center;
  gap: var(--space-5);
  padding: var(--space-3) var(--space-5);
  background: var(--color-bg-surface);
  border-bottom: 1px solid var(--color-border);
}

.brand {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  color: var(--color-text-primary);
  font-weight: var(--font-weight-semibold);
  font-size: var(--text-md);
  text-decoration: none;
}

.brand-logo {
  width: 28px;
  height: 28px;
  border-radius: var(--radius-sm);
}

.nav-links {
  display: flex;
  gap: var(--space-4);
  flex: 1;
}

.nav-links a {
  color: var(--color-text-secondary);
  text-decoration: none;
  font-size: var(--text-sm);
  padding: var(--space-2) 0;
  border-bottom: 2px solid transparent;
}

.nav-links a.active {
  color: var(--color-brand-600);
  border-bottom-color: var(--color-brand-500);
}

.nav-actions {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  font-size: var(--text-sm);
}

.username {
  color: var(--color-text-secondary);
}

.link-btn {
  border: none;
  background: none;
  color: var(--color-brand-600);
  cursor: pointer;
  font-size: var(--text-sm);
  text-decoration: none;
  padding: 0;
}

@media (max-width: 640px) {
  .nav-bar {
    gap: var(--space-3);
    padding: var(--space-2) var(--space-3);
  }
  .brand span {
    display: none;
  }
}
</style>
