<script setup lang="ts">
import { computed } from 'vue'
import type { QueryResultItem } from '../types/query'

const props = defineProps<{
  result: QueryResultItem
  favorited: boolean
  favoriteLoading?: boolean
}>()

const emit = defineEmits<{ toggleFavorite: [] }>()

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

const tagBadges = computed(() => {
  const tag = props.result.extra?.tag
  return typeof tag === 'string' ? tag.split(/\s+/).filter(Boolean) : []
})

const collinsStars = computed(() => {
  const value = props.result.extra?.collins
  return typeof value === 'number' && value > 0 ? value : null
})

const isOxford3000 = computed(() => Boolean(props.result.extra?.oxford))

// 部分 ECDICT 数据（含已导入的旧数据）把多行释义存成字面 "\n" 而非真换行，
// 这里兜底转换一次，避免页面上直接显示出 \n 这两个字符；真 HTML 内容（MDict）不受影响。
const definitionHtml = computed(() => props.result.definition.replace(/\\n/g, '\n'))

const arrayFields = computed(() => {
  if (!props.result.extra) return []
  return Object.entries(props.result.extra)
    .filter(([key, value]) => key in KNOWN_ARRAY_LABELS && Array.isArray(value) && value.length)
    .map(([key, value]) => ({ label: KNOWN_ARRAY_LABELS[key], values: value as string[] }))
})

const textFields = computed(() => {
  if (!props.result.extra) return []
  return Object.entries(props.result.extra)
    .filter(
      ([key, value]) =>
        key in KNOWN_TEXT_LABELS && (typeof value === 'string' || typeof value === 'number'),
    )
    .map(([key, value]) => ({ label: KNOWN_TEXT_LABELS[key], value: String(value) }))
})
</script>

<template>
  <article class="word-card">
    <header class="word-card-header">
      <span class="dict-tag">{{ result.dictionary_name }}</span>
      <button
        type="button"
        class="favorite-btn"
        :class="{ favorited }"
        :disabled="favoriteLoading"
        :aria-label="favorited ? '取消收藏' : '加入生词本'"
        @click="emit('toggleFavorite')"
      >
        <svg
          viewBox="0 0 24 24"
          width="20"
          height="20"
          :fill="favorited ? 'currentColor' : 'none'"
          stroke="currentColor"
          stroke-width="1.5"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            d="M12 3.5l2.7 5.6 6.1.9-4.4 4.3 1 6.1-5.4-2.9-5.4 2.9 1-6.1-4.4-4.3 6.1-.9L12 3.5Z"
          />
        </svg>
      </button>
    </header>

    <div class="word-row">
      <span class="word">{{ result.word }}</span>
      <span v-if="result.phonetic" class="phonetic">[{{ result.phonetic }}]</span>
    </div>

    <div v-if="tagBadges.length || collinsStars || isOxford3000" class="badges">
      <span v-if="isOxford3000" class="badge badge-brand">牛津3000</span>
      <span v-if="collinsStars" class="badge badge-brand">柯林斯 {{ collinsStars }} 星</span>
      <span v-for="t in tagBadges" :key="t" class="badge badge-info">{{ t }}</span>
    </div>

    <div class="definition" v-html="definitionHtml"></div>

    <ul v-if="arrayFields.length" class="extra-list">
      <li v-for="field in arrayFields" :key="field.label">
        <strong>{{ field.label }}：</strong>{{ field.values.join('、') }}
      </li>
    </ul>
    <ul v-if="textFields.length" class="extra-list">
      <li v-for="field in textFields" :key="field.label">
        <strong>{{ field.label }}：</strong>{{ field.value }}
      </li>
    </ul>
  </article>
</template>

<style scoped>
.word-card {
  background: var(--color-bg-surface);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-elevation-1);
  padding: var(--space-5);
}

.word-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-3);
}

.dict-tag {
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
  background: var(--color-bg-base);
  border-radius: var(--radius-sm);
  padding: var(--space-1) var(--space-2);
}

.favorite-btn {
  border: 1px solid var(--color-border);
  background: transparent;
  color: var(--color-text-secondary);
  width: 32px;
  height: 32px;
  border-radius: var(--radius-full);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: transform 100ms ease;
}

.favorite-btn:hover {
  background: var(--color-brand-50);
}

.favorite-btn.favorited {
  color: var(--color-brand-500);
  border-color: var(--color-brand-500);
  transform: scale(1.08);
}

.word-row {
  display: flex;
  align-items: baseline;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
}

.word {
  font-size: var(--text-xl);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.phonetic {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  font-family: 'Noto Serif SC', Georgia, serif;
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
}

.badge-brand {
  background: var(--color-brand-50);
  color: var(--color-brand-700);
}

.badge-info {
  background: color-mix(in srgb, var(--color-info) 14%, transparent);
  color: var(--color-info);
}

.definition {
  color: var(--color-text-primary);
  font-size: var(--text-base);
  line-height: var(--leading-body);
  white-space: pre-wrap;
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
</style>
