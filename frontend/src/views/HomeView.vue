<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import NavBar from '../components/NavBar.vue'
import DictionarySidebar from '../components/DictionarySidebar.vue'
import EntryPanel from '../components/EntryPanel.vue'
import SkeletonList from '../components/SkeletonList.vue'
import EmptyState from '../components/EmptyState.vue'
import { searchWord } from '../api/dict'
import { getSystemInfo } from '../api/system'
import { useUserAuthStore } from '../stores/userAuth'
import { useSettingsStore } from '../stores/settings'
import { useFavorites } from '../composables/useFavorites'
import { useDictionaryFilter } from '../composables/useDictionaryFilter'
import type { QueryResultItem } from '../types/query'

const router = useRouter()
const authStore = useUserAuthStore()
const settingsStore = useSettingsStore()
const { favoriteMap, favoriteLoading, loadFavorites, toggleFavorite } = useFavorites()
const {
  dictionaries,
  selectedIds,
  checkedIds,
  allIds,
  filterIds,
  isFiltering,
  loading: dictLoading,
  load: loadDictionaryFilter,
  toggle: toggleDictionary,
  setSelection,
} = useDictionaryFilter()

// 同时保留的 iframe 文档数上限：折叠时不立刻销毁（声音还在放、内部滚动位置也要留住），
// 但也不能无限累积——一次查询最多可能命中几十部词典，每个 iframe 都是一份带 CSS/JS 的文档。
const MAX_LIVE_FRAMES = 5

const word = ref('')
const submittedWord = ref('')
const results = ref<QueryResultItem[]>([])
const status = ref<'idle' | 'loading' | 'ok' | 'error'>('idle')
const version = ref('')
const mobileOpen = ref(false)

// 展开状态只存一个 key（互斥展开）；liveKeys 是「已挂载过 iframe」的 LRU 列表
const expandedKey = ref<string | null>(null)
const liveKeys = ref<string[]>([])

const showLoginGate = computed(
  () => settingsStore.loaded && !settingsStore.openAccess && !authStore.isLoggedIn,
)

const favoritedWords = computed(() => new Set(favoriteMap.value.keys()))

interface DictionaryGroup {
  key: string
  dictionaryId: number
  dictionaryName: string
  entries: QueryResultItem[]
}

// 按词典分组。同一部词典命中多条（同形不同大小写、或以后查询扩展带来的多个词形）合并成一张面板，
// 面板顺序沿用后端给的顺序——后端已按「优先语言优先、再按 sort_order」排好。
const groups = computed<DictionaryGroup[]>(() => {
  const map = new Map<number, DictionaryGroup>()
  for (const item of results.value) {
    let group = map.get(item.dictionary_id)
    if (!group) {
      group = {
        key: String(item.dictionary_id),
        dictionaryId: item.dictionary_id,
        dictionaryName: item.dictionary_name,
        entries: [],
      }
      map.set(item.dictionary_id, group)
    }
    group.entries.push(item)
  }
  return [...map.values()]
})

onMounted(async () => {
  getSystemInfo()
    .then((info) => {
      version.value = info.version
    })
    .catch(() => undefined)
  if (!settingsStore.loaded) await settingsStore.load().catch(() => undefined)
  if (settingsStore.loaded && !settingsStore.initialized) {
    router.replace('/admin/setup')
    return
  }
  await Promise.all([loadFavorites(), loadDictionaryFilter()])
})

// 检索范围变了就用新范围重查（还没查过就不动）。比的是勾选结果的字符串，这样从
// [1,2] 换成 [1,3] 这种数量不变的变化也能触发。
watch(
  () => selectedIds.value.join(','),
  () => {
    if (submittedWord.value) runSearch()
  },
)

/** 侧边栏的「只看某种语言」：勾选该语言的全部词典 */
function selectLanguage(langFrom: string) {
  setSelection(dictionaries.value.filter((item) => item.lang_from === langFrom).map((i) => i.id))
}

function touchLive(key: string) {
  liveKeys.value = [key, ...liveKeys.value.filter((k) => k !== key)].slice(0, MAX_LIVE_FRAMES)
}

function toggleGroup(key: string) {
  if (expandedKey.value === key) {
    expandedKey.value = null
    return
  }
  expandedKey.value = key
  touchLive(key)
}

async function runSearch(query?: string) {
  const q = (query ?? word.value).trim()
  if (!q) return
  if (showLoginGate.value) return

  word.value = q
  status.value = 'loading'
  submittedWord.value = q
  try {
    const resp = await searchWord(q, filterIds.value)
    results.value = resp.results
    status.value = 'ok'
    // 排序第一的那部词典默认展开，其余折叠
    const first = resp.results[0]
    expandedKey.value = first ? String(first.dictionary_id) : null
    liveKeys.value = first ? [String(first.dictionary_id)] : []
  } catch {
    status.value = 'error'
  }
}

/** iframe 里点了 entry:// 词条链接，按新词重查 */
function searchFromEntry(next: string) {
  if (next.trim() === submittedWord.value.trim()) return
  runSearch(next)
}

function onUnsupportedAudio() {
  ElMessage.warning('这部词典的发音是浏览器不支持的 Speex 格式（尚未转码），暂时无法播放')
}
</script>

<template>
  <div class="page">
    <NavBar />

    <main class="search-page">
      <section class="search-head">
        <h1 class="tagline">{{ settingsStore.siteName }} · 查询与生词本</h1>

        <form class="search-box" :class="{ disabled: showLoginGate }" @submit.prevent="runSearch()">
          <input
            v-model="word"
            type="text"
            placeholder="输入要查询的单词或词语"
            :disabled="showLoginGate"
          />
          <button type="submit" :disabled="showLoginGate">查询</button>
        </form>

        <p v-if="authStore.isLoggedIn" class="search-hint">{{ settingsStore.searchHintText }}</p>
        <p class="search-hint">Ver: {{ version ? version : '0.0.0' }}</p>
      </section>

      <div class="layout">
        <div class="sidebar-slot">
          <button type="button" class="sidebar-toggle" @click="mobileOpen = true">
            检索范围（{{ checkedIds.size }}/{{ allIds.length }}）
          </button>
          <DictionarySidebar
            :dictionaries="dictionaries"
            :checked-ids="checkedIds"
            :loading="dictLoading"
            :is-filtering="isFiltering"
            :mobile-open="mobileOpen"
            @toggle="toggleDictionary"
            @select-all="setSelection([])"
            @select-language="selectLanguage"
            @close-mobile="mobileOpen = false"
          />
        </div>

        <div class="content">
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
            @action="runSearch()"
          />

          <EmptyState
            v-else-if="status === 'ok' && results.length === 0"
            :title="`暂未收录「${submittedWord}」，欢迎联系管理员补充词典`"
          />

          <div v-else-if="status === 'ok'" class="results">
            <EntryPanel
              v-for="group in groups"
              :key="group.key"
              :dictionary-name="group.dictionaryName"
              :entries="group.entries"
              :expanded="expandedKey === group.key"
              :mounted="liveKeys.includes(group.key)"
              :favorited-words="favoritedWords"
              :favorite-loading="favoriteLoading"
              @toggle="toggleGroup(group.key)"
              @entry="searchFromEntry"
              @toggle-favorite="toggleFavorite"
              @unsupported-audio="onUnsupportedAudio"
            />
          </div>
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

.search-page {
  max-width: 1080px;
  margin: 0 auto;
  padding: var(--space-7) var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.search-head {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.layout {
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr);
  gap: var(--space-5);
  align-items: start;
}

.sidebar-slot {
  position: sticky;
  top: var(--space-5);
}

.sidebar-toggle {
  display: none;
}

.content {
  min-width: 0;
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

.search-hint {
  margin: calc((var(--space-5) - var(--space-2)) * -1) 0 0;
  text-align: center;
  color: var(--color-text-tertiary);
  font-size: var(--text-xs);
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

@media (max-width: 640px) {
  .layout {
    grid-template-columns: minmax(0, 1fr);
  }

  .sidebar-slot {
    position: static;
  }

  .sidebar-toggle {
    display: block;
    width: 100%;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
    background: var(--color-bg-surface);
    color: var(--color-text-secondary);
    font-size: var(--text-sm);
    padding: var(--space-2);
    cursor: pointer;
  }
}
</style>
