<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useAdminAuthStore } from '../../stores/adminAuth'
import * as statsApi from '../../api/admin/stats'
import type { StatsOverview } from '../../types/stats'

const authStore = useAdminAuthStore()
const overview = ref<StatsOverview | null>(null)
const loading = ref(true)

onMounted(async () => {
  if (!authStore.profile) authStore.loadProfile().catch(() => undefined)
  try {
    overview.value = await statsApi.getOverview()
  } finally {
    loading.value = false
  }
})

const cards = [
  { key: 'today_query_count', label: '今日查询量' },
  { key: 'active_tokens', label: '今日活跃 Token' },
  { key: 'active_users', label: '今日活跃用户' },
  { key: 'dictionary_count', label: '词典总数' },
] as const
</script>

<template>
  <div class="page">
    <h1>概览</h1>
    <p v-if="authStore.profile" class="welcome">欢迎回来，{{ authStore.profile.username }}</p>

    <div v-loading="loading" class="kpi-grid">
      <div v-for="card in cards" :key="card.key" class="kpi-card">
        <span class="kpi-value">{{ overview ? overview[card.key] : '—' }}</span>
        <span class="kpi-label">{{ card.label }}</span>
      </div>
    </div>

    <section class="panel">
      <h2>快速开始</h2>
      <ol class="steps">
        <li><router-link to="/admin/dictionaries">导入并启用词典</router-link></li>
        <li><router-link to="/admin/tokens">创建 API Token 分发给第三方</router-link></li>
        <li><router-link to="/admin/settings">按需开启「开放使用」或调整限流阈值</router-link></li>
        <li><router-link to="/admin/stats">查看查询趋势与热门词</router-link></li>
      </ol>
    </section>
  </div>
</template>

<style scoped>
.page {
  max-width: 1080px;
  margin: var(--space-6) auto;
  padding: 0 var(--space-4);
}

h1 {
  font-size: var(--text-xl);
  color: var(--color-text-primary);
  margin: 0 0 var(--space-2);
}

.welcome {
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  margin: 0 0 var(--space-5);
}

.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: var(--space-4);
  margin-bottom: var(--space-5);
}

.kpi-card {
  background: var(--color-bg-surface);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-elevation-1);
  padding: var(--space-5);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.kpi-value {
  font-size: var(--text-3xl);
  font-weight: var(--font-weight-bold);
  color: var(--color-brand-600);
}

.kpi-label {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.panel {
  background: var(--color-bg-surface);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-elevation-1);
  padding: var(--space-5);
}

.panel h2 {
  font-size: var(--text-md);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
  margin: 0 0 var(--space-3);
}

.steps {
  margin: 0;
  padding-left: var(--space-5);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.steps a {
  color: var(--color-brand-600);
}
</style>
