<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import NavBar from '../components/NavBar.vue'
import WordCard from '../components/WordCard.vue'
import SkeletonList from '../components/SkeletonList.vue'
import EmptyState from '../components/EmptyState.vue'
import { searchWord } from '../api/dict'
import { addVocab, deleteVocab, listVocab } from '../api/vocab'
import { useUserAuthStore } from '../stores/userAuth'
import { useSettingsStore } from '../stores/settings'
import type { QueryResultItem } from '../types/query'

const router = useRouter()
const authStore = useUserAuthStore()
const settingsStore = useSettingsStore()

const word = ref('')
const submittedWord = ref('')
const results = ref<QueryResultItem[]>([])
const status = ref<'idle' | 'loading' | 'ok' | 'error'>('idle')

// word(小写) -> 生词本条目 id，用于收藏态展示与取消收藏
const favoriteMap = ref<Map<string, number>>(new Map())
const favoriteLoading = ref<Set<string>>(new Set())

const showLoginGate = computed(
  () => settingsStore.loaded && !settingsStore.openAccess && !authStore.isLoggedIn,
)

async function loadFavoritesForPreload() {
  if (!authStore.isLoggedIn) return
  try {
    const resp = await listVocab(undefined, 1, 100)
    const map = new Map<string, number>()
    for (const item of resp.items) map.set(item.word.toLowerCase(), item.id)
    favoriteMap.value = map
  } catch {
    // 生词本预加载失败不影响查询本身
  }
}

onMounted(async () => {
  if (!settingsStore.loaded) await settingsStore.load().catch(() => undefined)
  await loadFavoritesForPreload()
})

async function runSearch() {
  const q = word.value.trim()
  if (!q) return
  if (showLoginGate.value) return

  status.value = 'loading'
  submittedWord.value = q
  try {
    const resp = await searchWord(q)
    results.value = resp.results
    status.value = 'ok'
  } catch {
    status.value = 'error'
  }
}

function isFavorited(w: string) {
  return favoriteMap.value.has(w.toLowerCase())
}

async function toggleFavorite(result: QueryResultItem) {
  if (!authStore.isLoggedIn) {
    ElMessage.warning('登录后才能收藏生词')
    router.push('/login')
    return
  }
  const key = result.word.toLowerCase()
  favoriteLoading.value.add(key)
  try {
    if (isFavorited(result.word)) {
      const id = favoriteMap.value.get(key)!
      await deleteVocab(id)
      favoriteMap.value.delete(key)
    } else {
      const item = await addVocab(result.word, result.dictionary_id)
      favoriteMap.value.set(key, item.id)
    }
    favoriteMap.value = new Map(favoriteMap.value)
  } catch {
    // 错误已由响应拦截器统一提示
  } finally {
    favoriteLoading.value.delete(key)
  }
}
</script>

<template>
  <div class="page">
    <NavBar />

    <main class="search-page">
      <h1 class="tagline">{{ settingsStore.siteName }} · 查询与生词本</h1>

      <form class="search-box" :class="{ disabled: showLoginGate }" @submit.prevent="runSearch">
        <input
          v-model="word"
          type="text"
          placeholder="输入要查询的单词或词语"
          :disabled="showLoginGate"
        />
        <button type="submit" :disabled="showLoginGate">查询</button>
      </form>

      <div v-if="showLoginGate" class="login-gate">
        <p>
          当前需要登录才能查询，<router-link to="/login">立即登录</router-link> 或
          <router-link to="/register">注册账号</router-link>。
        </p>
      </div>

      <SkeletonList v-else-if="status === 'loading'" :rows="2" />

      <EmptyState
        v-else-if="status === 'error'"
        title="网络异常，请重试"
        action-text="重新查询"
        @action="runSearch"
      />

      <EmptyState
        v-else-if="status === 'ok' && results.length === 0"
        :title="`暂未收录「${submittedWord}」，欢迎联系管理员补充词典`"
      />

      <div v-else-if="status === 'ok'" class="results">
        <WordCard
          v-for="r in results"
          :key="`${r.dictionary_id}-${r.word}`"
          :result="r"
          :favorited="isFavorited(r.word)"
          :favorite-loading="favoriteLoading.has(r.word.toLowerCase())"
          @toggle-favorite="toggleFavorite(r)"
        />
      </div>
    </main>
  </div>
</template>

<style scoped>
.page {
  min-height: 100vh;
  background: var(--color-bg-base);
}

.search-page {
  max-width: 720px;
  margin: 0 auto;
  padding: var(--space-7) var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.tagline {
  text-align: center;
  font-size: var(--text-lg);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-secondary);
  margin: 0;
}

.search-box {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  background: var(--color-bg-surface);
  border-radius: var(--radius-full);
  box-shadow: var(--shadow-elevation-1);
  padding: var(--space-2) var(--space-2) var(--space-2) var(--space-5);
  border: 1px solid transparent;
}

.search-box:focus-within {
  box-shadow: var(--shadow-elevation-2);
  border-color: var(--color-brand-500);
}

.search-box.disabled {
  opacity: 0.6;
}

.search-box input {
  flex: 1;
  border: none;
  outline: none;
  background: transparent;
  height: 48px;
  font-size: var(--text-md);
  color: var(--color-text-primary);
}

.search-box button {
  height: 40px;
  padding: 0 var(--space-5);
  border: none;
  border-radius: var(--radius-full);
  background: var(--color-brand-500);
  color: #fff;
  font-size: var(--text-base);
  cursor: pointer;
}

.search-box button:hover {
  background: var(--color-brand-600);
}

.search-box button:disabled {
  background: var(--color-border);
  cursor: not-allowed;
}

.login-gate {
  text-align: center;
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.results {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}
</style>
