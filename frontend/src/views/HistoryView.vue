<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import NavBar from '../components/NavBar.vue'
import SkeletonList from '../components/SkeletonList.vue'
import EmptyState from '../components/EmptyState.vue'
import FavoriteButton from '../components/FavoriteButton.vue'
import { getQueryHistory } from '../api/dict'
import { useFavorites } from '../composables/useFavorites'
import type { QueryHistoryEntry } from '../types/query'

const router = useRouter()
const { favoriteLoading, loadFavorites, isFavorited, toggleFavorite } = useFavorites()

const items = ref<QueryHistoryEntry[]>([])
const loading = ref(true)

onMounted(async () => {
  loading.value = true
  try {
    const [history] = await Promise.all([getQueryHistory(), loadFavorites()])
    items.value = history.items
  } finally {
    loading.value = false
  }
})

function formatDate(value: string) {
  return value.replace('T', ' ').slice(0, 16)
}
</script>

<template>
  <div class="page">
    <NavBar />
    <main class="history-page">
      <h1>查询历史</h1>
      <p class="hint">最近 100 次查询，未命中的搜索不计入。</p>

      <SkeletonList v-if="loading" :rows="4" />

      <EmptyState
        v-else-if="items.length === 0"
        title="还没有查询记录，去首页搜一个词吧"
        action-text="去查询"
        @action="router.push('/')"
      />

      <div v-else class="history-list">
        <div v-for="(item, i) in items" :key="`${item.word}-${item.dictionary_id}-${i}`" class="history-item">
          <div class="history-main">
            <span class="word">{{ item.word }}</span>
            <span class="dict-name">{{ item.dictionary_name }}</span>
            <span class="time">{{ formatDate(item.created_at) }}</span>
          </div>
          <FavoriteButton
            :favorited="isFavorited(item.word)"
            :loading="favoriteLoading.has(item.word.toLowerCase())"
            @toggle="toggleFavorite(item.word, item.dictionary_id)"
          />
        </div>
      </div>
    </main>
  </div>
</template>

<style scoped>
.page {
  min-height: 100vh;
  background: var(--color-bg-base);
}

.history-page {
  max-width: 720px;
  margin: 0 auto;
  padding: var(--space-6) var(--space-4);
}

.history-page h1 {
  font-size: var(--text-xl);
  color: var(--color-text-primary);
  margin: 0;
}

.hint {
  margin: var(--space-1) 0 var(--space-5);
  font-size: var(--text-sm);
  color: var(--color-text-tertiary);
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.history-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  background: var(--color-bg-surface);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-elevation-1);
  padding: var(--space-4);
}

.history-main {
  display: flex;
  align-items: baseline;
  gap: var(--space-3);
  min-width: 0;
}

.word {
  font-size: var(--text-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.dict-name {
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
  background: var(--color-bg-base);
  border-radius: var(--radius-sm);
  padding: var(--space-1) var(--space-2);
  white-space: nowrap;
}

.time {
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
  white-space: nowrap;
}
</style>
