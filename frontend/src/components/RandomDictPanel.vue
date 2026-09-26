<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import EntryFrame from './EntryFrame.vue'
import FavoriteButton from './FavoriteButton.vue'
import { getEntryHtml, prefetchEntryHtml, randomEntry } from '../api/dict'
import type { RandomEntry } from '../types/query'

const props = defineProps<{
  /** 随机池：检索范围勾选的词典 id；空数组 = 全部可用词典 */
  poolIds: number[]
  favoritedWords: Set<string>
  favoriteLoading: Set<string>
}>()

const emit = defineEmits<{
  /** 词条正文里点了 entry:// 链接，父级据此发起正常查询 */
  entry: [word: string]
  toggleFavorite: [word: string, dictionaryId: number]
  unsupportedAudio: []
}>()

const current = ref<RandomEntry | null>(null)
const loading = ref(false)
const failed = ref(false)
// 预取流水线：当前词条一显示就随机挑好下一条并预取其文档，【换一个】瞬时切换。
// poolKey 跟着词条走——池子变了（用户改了勾选）就作废重挑。
const nextUp = ref<{ entry: RandomEntry; poolKey: string } | null>(null)

const poolKey = computed(() => props.poolIds.join(','))

async function run() {
  loading.value = true
  failed.value = false
  current.value = null
  try {
    current.value = await randomEntry(props.poolIds)
    afterShow()
  } catch {
    failed.value = true
  } finally {
    loading.value = false
  }
}

function afterShow() {
  if (!nextUp.value) void prefetchNext()
}

async function prefetchNext() {
  const keyAtStart = poolKey.value
  try {
    const entry = await randomEntry(props.poolIds)
    if (poolKey.value !== keyAtStart) return // 池子在请求期间变了，这条作废
    nextUp.value = { entry, poolKey: keyAtStart }
    prefetchEntryHtml(entry.dictionary_id, entry.word, [entry.entry_id])
  } catch {
    /* 预取失败无所谓，点【换一个】时走同步路径 */
  }
}

async function next() {
  if (loading.value) return
  const up = nextUp.value
  if (up && up.poolKey === poolKey.value) {
    failed.value = false
    current.value = up.entry
    nextUp.value = null
    afterShow()
    return
  }
  nextUp.value = null
  await run()
}

onMounted(run)
// 池子变化（用户改了检索范围勾选）：作废预取、立即按新池换一条
watch(
  () => props.poolIds.join(','),
  () => {
    nextUp.value = null
    if (!loading.value) run()
  },
)

function loaderFor(e: RandomEntry) {
  return () => getEntryHtml(e.dictionary_id, e.word, [e.entry_id])
}

const poolLabel = computed(() =>
  props.poolIds.length ? `${props.poolIds.length} 部词典` : '全部可用词典',
)
</script>

<template>
  <div class="random-panel">
    <p v-if="loading" class="hint">正在随机挑词条…</p>

    <div v-else-if="failed" class="hint">
      随机挑词条失败，请重试。
      <button type="button" class="retry" @click="run">重新来一个</button>
    </div>

    <template v-else-if="current">
      <header class="random-head">
        <div class="random-meta">
          <span class="random-dict">{{ current.dictionary_name }}</span>
          <span class="random-pool">随机浏览 · {{ poolLabel }}</span>
        </div>
        <div class="random-actions">
          <FavoriteButton
            :favorited="favoritedWords.has(current.word.toLowerCase())"
            :loading="favoriteLoading.has(current.word.toLowerCase())"
            @toggle="emit('toggleFavorite', current.word, current.dictionary_id)"
          />
          <button type="button" class="next-btn" @click="next">换一个 →</button>
        </div>
      </header>

      <h2 class="random-word">{{ current.word }}</h2>

      <EntryFrame
        :key="current.entry_id"
        :loader="loaderFor(current)"
        @entry="emit('entry', $event)"
        @unsupported-audio="emit('unsupportedAudio')"
      />
    </template>
  </div>
</template>

<style scoped>
.random-panel {
  display: flex;
  flex-direction: column;
}

.hint {
  margin: 0;
  padding: var(--space-3) 0;
  color: var(--color-text-tertiary);
  font-size: var(--text-sm);
}

.retry {
  border: none;
  background: none;
  color: var(--color-brand-600);
  cursor: pointer;
  font-size: var(--text-sm);
  padding: 0;
}

.random-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  margin-bottom: var(--space-2);
}

.random-meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.random-dict {
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.random-pool {
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
  opacity: 0.8;
}

.random-actions {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-shrink: 0;
}

.next-btn {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-full);
  background: var(--color-bg-surface);
  color: var(--color-brand-600);
  font-size: var(--text-xs);
  padding: var(--space-1) var(--space-4);
  cursor: pointer;
  white-space: nowrap;
}

.next-btn:hover {
  border-color: var(--color-brand-500);
  background: var(--color-brand-50);
}

.random-word {
  margin: 0 0 var(--space-2);
  font-size: var(--text-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}
</style>
