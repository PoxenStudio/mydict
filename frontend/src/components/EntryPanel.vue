<script setup lang="ts">
import { computed } from 'vue'
import EntryFrame from './EntryFrame.vue'
import FavoriteButton from './FavoriteButton.vue'
import { getEntryHtml } from '../api/dict'
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
        :key="`${primary.dictionary_id}-${primary.word}`"
        :loader="() => getEntryHtml(primary.dictionary_id, queryWord, entries.map((item) => item.id))"
        @entry="emit('entry', $event)"
        @unsupported-audio="emit('unsupportedAudio')"
      />

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
          :loader="() => getEntryHtml(primary.dictionary_id, primary.word)"
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
</style>
