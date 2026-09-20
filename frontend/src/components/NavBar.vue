<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ArrowDown } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useUserAuthStore } from '../stores/userAuth'
import { useSettingsStore } from '../stores/settings'
import { listDictionaries } from '../api/dict'
import { setAllowedDictionaries } from '../api/auth'
import ThemeToggle from './ThemeToggle.vue'
import ChangePasswordDialog from './ChangePasswordDialog.vue'
import DictionaryPickerDialog from './DictionaryPickerDialog.vue'
import type { PublicDictionary } from '../types/query'

const authStore = useUserAuthStore()
const settingsStore = useSettingsStore()
const changePasswordVisible = ref(false)
const dictPickerVisible = ref(false)
const availableDictionaries = ref<PublicDictionary[]>([])

onMounted(() => {
  if (!settingsStore.loaded) settingsStore.load().catch(() => undefined)
  if (authStore.isLoggedIn && !authStore.profile) authStore.loadProfile().catch(() => undefined)
})

async function handleUserCommand(command: string) {
  if (command === 'change-password') {
    changePasswordVisible.value = true
  } else if (command === 'logout') {
    authStore.logout()
  } else if (command === 'dictionaries') {
    availableDictionaries.value = await listDictionaries()
    dictPickerVisible.value = true
  }
}

async function saveAllowedDictionaries(ids: number[] | null) {
  const profile = await setAllowedDictionaries(ids)
  if (authStore.profile) authStore.profile.allowed_dictionary_ids = profile.allowed_dictionary_ids
  ElMessage.success('已保存')
}
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
      <router-link to="/history" active-class="active">历史记录</router-link>
    </nav>

    <div class="nav-actions">
      <ThemeToggle />
      <template v-if="authStore.isLoggedIn">
        <el-dropdown trigger="click" @command="handleUserCommand">
          <span class="username-trigger">
            {{ authStore.profile?.username ?? '...' }}
            <el-icon class="dropdown-icon"><ArrowDown /></el-icon>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="dictionaries">词典选择</el-dropdown-item>
              <el-dropdown-item command="change-password">修改密码</el-dropdown-item>
              <el-dropdown-item command="logout" divided>退出</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </template>
      <template v-else>
        <router-link to="/login" class="link-btn">登录</router-link>
        <router-link to="/register" class="link-btn">注册</router-link>
        <router-link to="/admin" class="link-btn">后台</router-link>
      </template>
    </div>

    <ChangePasswordDialog v-model:visible="changePasswordVisible" />
    <DictionaryPickerDialog
      v-model:visible="dictPickerVisible"
      :dictionaries="availableDictionaries"
      :current-ids="authStore.profile?.allowed_dictionary_ids ?? null"
      @confirm="saveAllowedDictionaries"
    />
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

.username-trigger {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  color: var(--color-text-secondary);
  cursor: pointer;
}

.username-trigger:hover {
  color: var(--color-text-primary);
}

.dropdown-icon {
  font-size: var(--text-xs);
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
