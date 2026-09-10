<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAdminAuthStore } from '../../stores/adminAuth'
import ThemeToggle from '../../components/ThemeToggle.vue'
import BackgroundTasksIndicator from '../../components/admin/BackgroundTasksIndicator.vue'

const router = useRouter()
const authStore = useAdminAuthStore()
const drawerOpen = ref(false)

const navItems = [
  { to: '/admin', label: '概览', exact: true },
  { to: '/admin/dictionaries', label: '词典管理' },
  { to: '/admin/tokens', label: 'Token 管理' },
  { to: '/admin/users', label: '用户管理' },
  { to: '/admin/stats', label: '统计' },
  { to: '/admin/settings', label: '系统设置' },
]

onMounted(() => {
  if (!authStore.profile) authStore.loadProfile().catch(() => undefined)
})

function logout() {
  authStore.logout()
  router.push('/admin/login')
}
</script>

<template>
  <div class="admin-shell">
    <header class="admin-topbar">
      <button
        type="button"
        class="drawer-toggle"
        aria-label="打开菜单"
        @click="drawerOpen = !drawerOpen"
      >
        ☰
      </button>
      <span class="brand">MyDict 管理后台</span>
      <div class="topbar-actions">
        <BackgroundTasksIndicator />
        <ThemeToggle />
        <span v-if="authStore.profile" class="username">{{ authStore.profile.username }}</span>
        <button type="button" class="link-btn" @click="logout">退出</button>
      </div>
    </header>

    <div class="admin-body">
      <aside class="admin-sidebar" :class="{ open: drawerOpen }">
        <router-link
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          :class="{
            active: item.exact ? $route.path === item.to : $route.path.startsWith(item.to),
          }"
          @click="drawerOpen = false"
        >
          {{ item.label }}
        </router-link>
      </aside>
      <div v-if="drawerOpen" class="drawer-backdrop" @click="drawerOpen = false" />

      <main class="admin-content">
        <router-view />
      </main>
    </div>
  </div>
</template>

<style scoped>
.admin-shell {
  min-height: 100vh;
  background: var(--color-bg-base);
}

.admin-topbar {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  padding: var(--space-3) var(--space-5);
  background: var(--color-bg-surface);
  border-bottom: 1px solid var(--color-border);
}

.brand {
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.drawer-toggle {
  display: none;
  border: none;
  background: none;
  font-size: var(--text-lg);
  color: var(--color-text-secondary);
  cursor: pointer;
}

.topbar-actions {
  margin-left: auto;
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
}

.admin-body {
  display: flex;
  align-items: stretch;
}

.admin-sidebar {
  width: 200px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding: var(--space-4) var(--space-3);
  border-right: 1px solid var(--color-border);
  background: var(--color-bg-surface);
  min-height: calc(100vh - 57px);
}

.admin-sidebar a {
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  color: var(--color-text-secondary);
  text-decoration: none;
  font-size: var(--text-sm);
}

.admin-sidebar a:hover {
  background: var(--color-hover-tint);
}

.admin-sidebar a.active {
  background: var(--color-brand-50);
  color: var(--color-brand-700);
  font-weight: var(--font-weight-medium);
}

.admin-content {
  flex: 1;
  min-width: 0;
}

.drawer-backdrop {
  display: none;
}

@media (max-width: 1023px) {
  .drawer-toggle {
    display: inline-flex;
  }

  .admin-sidebar {
    position: fixed;
    z-index: 20;
    top: 0;
    left: 0;
    bottom: 0;
    transform: translateX(-100%);
    transition: transform 200ms ease;
    box-shadow: var(--shadow-elevation-3);
  }

  .admin-sidebar.open {
    transform: translateX(0);
  }

  .drawer-backdrop {
    display: block;
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.3);
    z-index: 10;
  }
}
</style>
