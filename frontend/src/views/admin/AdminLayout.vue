<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAdminAuthStore } from '../../stores/adminAuth'
import ThemeToggle from '../../components/ThemeToggle.vue'
import BackgroundTasksIndicator from '../../components/admin/BackgroundTasksIndicator.vue'

const appVersion = __APP_VERSION__
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
        <svg
          viewBox="0 0 24 24"
          width="20"
          height="20"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          aria-hidden="true"
        >
          <path d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>
      <span class="brand">MyDict 管理后台<span class="version">（v{{ appVersion }}）</span></span>
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
        <!-- 离开后台是"出口"而不是后台的一个栏目，压到侧边栏底部单独放 -->
        <router-link class="nav-back" to="/" @click="drawerOpen = false">回到首页</router-link>
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
  /* 顶栏固定高度、主体吃掉剩余高度：侧边栏靠 flex 拉伸到底，不再用写死的 57px 反推 */
  display: flex;
  flex-direction: column;
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

.version {
  font-weight: var(--font-weight-regular);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
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
  color: var(--color-brand-text);
  cursor: pointer;
  font-size: var(--text-sm);
}

.link-btn:hover {
  text-decoration: underline;
}

.admin-body {
  flex: 1;
  display: flex;
  align-items: stretch;
  min-height: 0;
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
  color: var(--color-text-primary);
}

.admin-sidebar a.active {
  background: var(--color-brand-soft);
  color: var(--color-brand-soft-text);
  font-weight: var(--font-weight-medium);
}

/* 出口链接与栏目之间拉一道分隔，视觉上不再是一个可点击的"栏目" */
.admin-sidebar .nav-back {
  margin-top: auto;
  padding-top: var(--space-3);
  border-top: 1px solid var(--color-border);
  border-radius: 0;
  color: var(--color-text-tertiary);
}

.admin-sidebar .nav-back:hover {
  background: transparent;
  color: var(--color-brand-text);
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
