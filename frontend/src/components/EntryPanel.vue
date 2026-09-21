<script setup lang="ts">
import { computed } from 'vue'
import EntryFrame from './EntryFrame.vue'
import FavoriteButton from './FavoriteButton.vue'
import { getEntryHtml } from '../api/dict'
import type { QueryResultItem } from '../types/query'

const props = defineProps<{
  dictionaryName: string
  entries: QueryResultItem[]
  expanded: boolean
  /** 首次展开后才挂载 iframe：一次查询可能命中几十部词典，不能一上来就建几十个文档 */
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

    <div v-if="expanded" class="panel-body">
      <article
        v-for="(item, index) in entries"
        :key="`${item.dictionary_id}-${item.word}`"
        class="entry"
      >
        <header v-if="hasMultiple" class="entry-header">
          <span class="head-word">{{ item.word }}</span>
          <span v-if="item.phonetic" class="phonetic">[{{ item.phonetic }}]</span>
          <FavoriteButton
            :favorited="isFavorited(item.word)"
            :loading="isLoading(item.word)"
            @toggle="emit('toggleFavorite', item.word, item.dictionary_id)"
          />
        </header>

        <div
          v-if="isOxford3000(item) || collinsStars(item) || tagBadges(item).length"
          class="badges"
        >
          <span v-if="isOxford3000(item)" class="badge badge-brand">牛津3000</span>
          <span v-if="collinsStars(item)" class="badge badge-brand">
            柯林斯 {{ collinsStars(item) }} 星
          </span>
          <span v-for="t in tagBadges(item)" :key="t" class="badge badge-info">{{ t }}</span>
        </div>

        <!--
          释义只在首次展开时才去取、才建 iframe。留着已挂载的 iframe 而不是每次折叠就销毁，
          这样音频播放位置与内部滚动不会丢。
        -->
        <EntryFrame
          v-if="mounted"
          :key="`${item.dictionary_id}-${item.word}`"
          :loader="() => getEntryHtml(item.dictionary_id, item.word)"
          @entry="emit('entry', $event)"
          @unsupported-audio="emit('unsupportedAudio')"
        />

        <ul v-if="arrayFields(item).length" class="extra-list">
          <li v-for="field in arrayFields(item)" :key="field.label">
            <strong>{{ field.label }}：</strong>{{ field.values.join('、') }}
          </li>
        </ul>
        <ul v-if="textFields(item).length" class="extra-list">
          <li v-for="field in textFields(item)" :key="field.label">
            <strong>{{ field.label }}：</strong>{{ field.value }}
          </li>
        </ul>

        <hr v-if="hasMultiple && index < entries.length - 1" class="divider" />
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
