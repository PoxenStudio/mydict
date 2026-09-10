<script setup lang="ts">
import { onMounted } from 'vue'
import { useAdminAuthStore } from '../../stores/adminAuth'

const authStore = useAdminAuthStore()

onMounted(() => {
  if (!authStore.profile) {
    authStore.loadProfile()
  }
})
</script>

<template>
  <div class="dashboard">
    <h1>管理后台</h1>
    <p v-if="authStore.profile">欢迎，{{ authStore.profile.username }}</p>
    <p class="hint">词典管理 / Token 管理 / 用户管理 / 统计 / 系统设置将在后续步骤中实现。</p>
  </div>
</template>

<style scoped>
.dashboard {
  max-width: 640px;
  margin: var(--space-7) auto;
  padding: var(--space-6);
  background: var(--color-bg-surface);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-elevation-1);
}

h1 {
  margin: 0 0 var(--space-3);
  font-size: var(--text-xl);
  color: var(--color-text-primary);
}

.hint {
  color: var(--color-text-tertiary);
  font-size: var(--text-sm);
}
</style>
