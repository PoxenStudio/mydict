<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import EntryFrame from './EntryFrame.vue'
import FavoriteButton from './FavoriteButton.vue'
import { getEntryHtml, prefetchEntryHtml } from '../api/dict'
import type { QueryResultItem } from '../types/query'

const props = defineProps<{
  dictionaryName: string
  entries: QueryResultItem[]
  /** 用户这次查询输入的词：后端只在它的变体范围内认 entry_ids */
  queryWord: string
  expanded: boolean
  /**
   * 是否在「保留已挂载 iframe」的 LRU 里（见 HomeView 的 liveKeys）。首次展开后才挂载，
   * 折叠后仍保留（声音还在放、内部滚动位置也留着），被挤出 LRU 才销毁
   */
  mounted: boolean
  favoritedWords: Set<string>
  favoriteLoading: Set<string>
}>()

const emit = defineEmits<{
  toggle: []
  entry: [word: string]
  toggleFavorite: [word: string, dictionaryId: number]
  unsupportedAudio: []
  /** 分批切换后请求把面板滚回视口顶部（HomeView 复用展开时的滚动逻辑） */
  rescroll: []
}>()

const KNOWN_ARRAY_LABELS: Record<string, string> = {
  synonyms: '同义字',
  antonyms: '反义字',
  likeness: '形近字',
  similar: '近义词',
  opposite: '反义词',
}

const KNOWN_TEXT_LABELS: Record<string, string> = {
  strokes: '笔画',
  radicals: '部首',
  structure: '结构',
  traditional: '繁体',
  variant: '异体',
  bnc: 'BNC 词频',
  frq: '当代语料词频',
  exchange: '词形变化',
  usage: '用法',
  notice: '注意',
}

const primary = computed(() => props.entries[0])
const hasMultiple = computed(() => props.entries.length > 1)

// --- 多词条分批加载 ---
// 词条渲染接口对 entry_ids 有 200 条上限（防伪造，见后端 dict.py）；搜韵这类
// 「每首诗一个词条」的词典对常见诗人就是几百条（李白 823）。每批一次独立的
// 文档请求、换批重建 iframe（:key 切换），按钮由父级渲染在词条卡片底部——
// 不进引导脚本协议，后端零改动。
const BATCH_SIZE = 200
const batchIndex = ref(0)
const batchCount = computed(() => Math.max(1, Math.ceil(props.entries.length / BATCH_SIZE)))
const currentBatchIds = computed(() =>
  props.entries
    .slice(batchIndex.value * BATCH_SIZE, (batchIndex.value + 1) * BATCH_SIZE)
    .map((item) => item.id),
)
const batchLabel = computed(() => {
  const start = batchIndex.value * BATCH_SIZE + 1
  const end = Math.min((batchIndex.value + 1) * BATCH_SIZE, props.entries.length)
  return `第 ${batchIndex.value + 1}/${batchCount.value} 批 · 第 ${start}-${end} 条`
})

// 换查询词/换结果集时归零，避免停在已不存在的批上
watch(() => [props.queryWord, props.entries.length], () => {
  batchIndex.value = 0
})

function gotoBatch(delta: number) {
  const next = batchIndex.value + delta
  if (next < 0 || next >= batchCount.value) return
  batchIndex.value = next
  emit('rescroll')
}

// 当前批挂载后就预取下一批：翻到批底部点【下一批】时文档已在手，基本瞬时
watch([batchIndex, () => props.expanded], ([index, expanded]) => {
  if (!expanded || index + 1 >= batchCount.value) return
  const ids = props.entries
    .slice((index + 1) * BATCH_SIZE, (index + 2) * BATCH_SIZE)
    .map((item) => item.id)
  prefetchEntryHtml(primary.value.dictionary_id, props.queryWord, ids)
})

/**
 * 悬停/按下标题时预取词条文档：点击展开时 HTML 已在手，iframe 立即挂载。
 * 指针事件在 click 之前触发（pointerdown 比 click 早一整次按压），局域网内足够把
 * 请求往返藏进点击里；已展开/已挂载的没有意义，跳过。缓存去重由 api 层负责。
 */
function prefetch() {
  if (props.expanded || !props.queryWord) return
  const ids = hasMultiple.value
    ? props.entries.map((item) => item.id)
    : [primary.value.id]
  prefetchEntryHtml(primary.value.dictionary_id, props.queryWord, ids)
}

function tagBadges(item: QueryResultItem): string[] {
  const tag = item.extra?.tag
  return typeof tag === 'string' ? tag.split(/\s+/).filter(Boolean) : []
}

function collinsStars(item: QueryResultItem): number | null {
  const value = item.extra?.collins
  return typeof value === 'number' && value > 0 ? value : null
}

function isOxford3000(item: QueryResultItem): boolean {
  return Boolean(item.extra?.oxford)
}

function arrayFields(item: QueryResultItem) {
  if (!item.extra) return []
  return Object.entries(item.extra)
    .filter(([key, value]) => key in KNOWN_ARRAY_LABELS && Array.isArray(value) && value.length)
    .map(([key, value]) => ({ label: KNOWN_ARRAY_LABELS[key], values: value as string[] }))
}

function textFields(item: QueryResultItem) {
  if (!item.extra) return []
  return Object.entries(item.extra)
    .filter(
      ([key, value]) =>
        key in KNOWN_TEXT_LABELS && (typeof value === 'string' || typeof value === 'number'),
    )
    .map(([key, value]) => ({ label: KNOWN_TEXT_LABELS[key], value: String(value) }))
}

function isFavorited(word: string) {
  return props.favoritedWords.has(word.toLowerCase())
}

function isLoading(word: string) {
  return props.favoriteLoading.has(word.toLowerCase())
}
</script>

<template>
  <section class="panel" :class="{ expanded }">
    <header
      class="panel-header"
      role="button"
      tabindex="0"
      :aria-expanded="expanded"
      @click="emit('toggle')"
      @pointerdown="prefetch"
      @mouseenter="prefetch"
      @keydown.enter.prevent="emit('toggle')"
      @keydown.space.prevent="emit('toggle')"
    >
      <span class="chevron" :class="{ open: expanded }" aria-hidden="true">›</span>
      <span class="dict-name">{{ dictionaryName }}</span>
      <span class="head-word">{{ primary.word }}</span>
      <span v-if="primary.phonetic" class="phonetic">[{{ primary.phonetic }}]</span>
      <!-- 语言路由兜底时的标记：这条命中的词典其 lang_from 与输入语言不一致 -->
      <span v-if="primary.lang_match === false" class="badge badge-warn">其他语言词典</span>
      <span v-if="hasMultiple" class="hint">共 {{ entries.length }} 条</span>
      <FavoriteButton
        class="head-favorite"
        :favorited="isFavorited(primary.word)"
        :loading="isLoading(primary.word)"
        @toggle="emit('toggleFavorite', primary.word, primary.dictionary_id)"
      />
    </header>

    <!--
      折叠时不用 display:none：隐藏的 iframe 会按 0 宽度排版、上报一个极大的高度，把 EntryFrame
      的增长守卫误触发成「冻结可滚动」。改为高度收成 0，iframe 仍按真实宽度排版；inert 挡住
      键盘焦点落进看不见的内容。
    -->
    <div
      v-if="expanded || mounted"
      class="panel-body"
      :class="{ collapsed: !expanded }"
      :inert="!expanded"
    >
      <!--
        同一部词典命中多条（同名词条或繁简变体）时，整个词典只用一个 iframe：词条端点会把
        这组词条聚合进一个文档，条与条之间有小标题和分隔线（见后端 render_entries_document）。
        逐条各建一个 iframe 的话，搜韵诗词全文检索版这类词典展开一次就要挂载 82 个沙箱文档。
      -->
      <EntryFrame
        v-if="hasMultiple"
        :key="`${primary.dictionary_id}-${primary.word}-b${batchIndex}`"
        :loader="() => getEntryHtml(primary.dictionary_id, queryWord, currentBatchIds)"
        @entry="emit('entry', $event)"
        @unsupported-audio="emit('unsupportedAudio')"
      />

      <!-- 分批导航：只在多词条且超过一批时出现 -->
      <nav v-if="hasMultiple && batchCount > 1" class="batch-nav">
        <button type="button" :disabled="batchIndex === 0" @click="gotoBatch(-1)">
          上一批
        </button>
        <span class="batch-label">{{ batchLabel }}</span>
        <button
          type="button"
          :disabled="batchIndex >= batchCount - 1"
          @click="gotoBatch(1)"
        >
          下一批
        </button>
      </nav>

      <!--
        单条：per-entry 的徽标（牛津3000 / 柯林斯星级 / extra 字段）只有 ECDICT 这类
        词典才有，它们不会同名多义，保持原来的渲染即可。
      -->
      <article v-if="!hasMultiple" :key="`${primary.dictionary_id}-${primary.word}`" class="entry">
        <div v-if="isOxford3000(primary) || collinsStars(primary) || tagBadges(primary).length" class="badges">
          <span v-if="isOxford3000(primary)" class="badge badge-brand">牛津3000</span>
          <span v-if="collinsStars(primary)" class="badge badge-brand">
            柯林斯 {{ collinsStars(primary) }} 星
          </span>
          <span v-for="t in tagBadges(primary)" :key="t" class="badge badge-info">{{ t }}</span>
        </div>

        <EntryFrame
          :key="`${primary.dictionary_id}-${primary.word}`"
          :loader="() => getEntryHtml(primary.dictionary_id, queryWord, [primary.id])"
          @entry="emit('entry', $event)"
          @unsupported-audio="emit('unsupportedAudio')"
        />

        <ul v-if="arrayFields(primary).length" class="extra-list">
          <li v-for="field in arrayFields(primary)" :key="field.label">
            <strong>{{ field.label }}：</strong>{{ field.values.join('、') }}
          </li>
        </ul>
        <ul v-if="textFields(primary).length" class="extra-list">
          <li v-for="field in textFields(primary)" :key="field.label">
            <strong>{{ field.label }}：</strong>{{ field.value }}
          </li>
        </ul>
      </article>
    </div>
  </section>
</template>

<style scoped>
.panel {
  background: var(--color-bg-surface);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-elevation-1);
  overflow: hidden;
  /* 展开时把标题滚到视口顶部（见 HomeView 的 toggleGroup），留一点呼吸空间别贴边 */
  scroll-margin-top: var(--space-4);
}

.panel-header {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  /* 垂直只留 --space-1：标题行的高度实际由 32px 的收藏按钮决定，多给的 padding 只是白占地方 */
  padding: var(--space-1) var(--space-5);
  cursor: pointer;
  user-select: none;
}

.panel-header:hover {
  background: var(--color-hover-tint);
}

.chevron {
  flex-shrink: 0;
  color: var(--color-text-tertiary);
  font-size: var(--text-lg);
  line-height: 1;
  transition: transform 0.15s ease;
}

.chevron.open {
  transform: rotate(90deg);
}

.dict-name {
  flex-shrink: 0;
  max-width: 40%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
  background: var(--color-bg-base);
  border-radius: var(--radius-sm);
  padding: var(--space-1) var(--space-2);
}

.head-word {
  font-size: var(--text-md);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.phonetic {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  font-family: 'Noto Serif SC', Georgia, serif;
}

.head-favorite {
  margin-left: auto;
}

.panel-body {
  padding: 0 var(--space-5) var(--space-5);
}

.panel-body.collapsed {
  height: 0;
  padding-bottom: 0;
  overflow: hidden;
  visibility: hidden;
}

.entry-header {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
}

.badges {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-bottom: var(--space-3);
}

.badge {
  border-radius: var(--radius-full);
  padding: 2px var(--space-3);
  font-size: var(--text-xs);
  white-space: nowrap;
}

.badge-brand {
  background: var(--color-brand-50);
  color: var(--color-brand-700);
}

.badge-info {
  background: color-mix(in srgb, var(--color-info) 14%, transparent);
  color: var(--color-info);
}

.badge-warn {
  background: color-mix(in srgb, var(--color-warning, var(--color-info)) 16%, transparent);
  color: var(--color-text-secondary);
}

.hint {
  color: var(--color-text-tertiary);
  font-size: var(--text-xs);
}

.extra-list {
  margin: var(--space-3) 0 0;
  padding: 0;
  list-style: none;
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.divider {
  margin: var(--space-5) 0;
  border: none;
  border-top: 1px solid var(--color-border);
}

/* 手机：词典卡片吃满屏宽，词条内容区只留 8px 左右内边距（约 95% 可用宽度）。
   之前的 95% 卡片 + 默认内边距叠加，实测仍然显得窄。 */
@media (max-width: 640px) {
  .panel {
    width: 100%;
    margin-left: 0;
    margin-right: 0;
  }

  .panel-body {
    padding: 0 var(--space-2) var(--space-3);
  }
}

/* 分批导航：贴在词条内容下方，胶囊按钮与检索范围标签同款 */
.batch-nav {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  padding: var(--space-2) 0 var(--space-3);
}

.batch-nav button {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-full);
  background: var(--color-bg-surface);
  color: var(--color-brand-600);
  font-size: var(--text-xs);
  padding: var(--space-1) var(--space-4);
  cursor: pointer;
}

.batch-nav button:hover:not(:disabled) {
  border-color: var(--color-brand-500);
  background: var(--color-brand-50);
}

.batch-nav button:disabled {
  color: var(--color-text-tertiary);
  cursor: not-allowed;
}

.batch-label {
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
}
</style>
