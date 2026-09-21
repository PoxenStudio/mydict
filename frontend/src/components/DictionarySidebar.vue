<script setup lang="ts">
import { computed, ref } from 'vue'
import { langLabel } from '../utils/language'
import type { PublicDictionary } from '../types/query'

const props = defineProps<{
  dictionaries: PublicDictionary[]
  checkedIds: Set<number>
  loading: boolean
  /** 是否正在按勾选收窄范围（false = 检索全部） */
  isFiltering: boolean
  /** 移动端由外层控制显示 */
  mobileOpen: boolean
}>()

const emit = defineEmits<{
  toggle: [id: number]
  selectAll: []
  selectLanguage: [langFrom: string]
  closeMobile: []
}>()

const keyword = ref('')

const visible = computed(() => {
  const needle = keyword.value.trim().toLowerCase()
  if (!needle) return props.dictionaries
  return props.dictionaries.filter((item) => item.name.toLowerCase().includes(needle))
})

const checkedCount = computed(
  () => props.dictionaries.filter((item) => props.checkedIds.has(item.id)).length,
)

/** 库里实际出现过的语言，按出现顺序去重——用来做「只看中文词典」这类快速筛选 */
const presentLanguages = computed(() => {
  const seen: string[] = []
  for (const item of props.dictionaries) {
    if (!seen.includes(item.lang_from)) seen.push(item.lang_from)
  }
  return seen
})

/** 当前勾选集是否恰好等于某一门语言的全部词典 */
const activeLanguage = computed(() => {
  if (!props.isFiltering) return null
  const checked = props.dictionaries.filter((item) => props.checkedIds.has(item.id))
  if (checked.length === 0) return null
  const langs = new Set(checked.map((item) => item.lang_from))
  if (langs.size !== 1) return null
  const [lang] = [...langs]
  const sameLang = props.dictionaries.filter((item) => item.lang_from === lang)
  return sameLang.length === checked.length ? lang : null
})
</script>

<template>
  <aside class="sidebar" :class="{ 'mobile-open': mobileOpen }">
    <header class="sidebar-header">
      <h2 class="title">检索范围</h2>
      <button type="button" class="close-mobile" aria-label="收起" @click="emit('closeMobile')">
        ×
      </button>
      <span class="count">{{ checkedCount }} / {{ dictionaries.length }}</span>
    </header>

    <input v-model="keyword" class="search" type="search" placeholder="筛选词典名" />

    <div class="actions">
      <button type="button" :class="{ active: !isFiltering }" @click="emit('selectAll')">
        全部
      </button>
      <button
        v-for="lang in presentLanguages"
        :key="lang"
        type="button"
        :class="{ active: activeLanguage === lang }"
        @click="emit('selectLanguage', lang)"
      >
        {{ langLabel(lang) }}
      </button>
    </div>

    <p v-if="!loading && !isFiltering" class="hint">未限制范围：检索全部已启用词典</p>

    <p v-if="loading" class="hint">正在载入词典列表…</p>
    <p v-else-if="dictionaries.length === 0" class="hint">暂无已启用的词典。</p>
    <p v-else-if="visible.length === 0" class="hint">没有匹配「{{ keyword }}」的词典。</p>

    <ul v-else class="dict-list">
      <li v-for="item in visible" :key="item.id">
        <label class="dict-row">
          <input
            type="checkbox"
            :checked="checkedIds.has(item.id)"
            @change="emit('toggle', item.id)"
          />
          <span class="dict-name" :title="item.name">{{ item.name }}</span>
          <span class="dict-lang">{{ langLabel(item.lang_from) }}</span>
        </label>
      </li>
    </ul>
  </aside>
</template>

<style scoped>
.sidebar {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  background: var(--color-bg-surface);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-elevation-1);
  padding: var(--space-4);
  max-height: calc(100vh - var(--space-7) * 2);
}

.sidebar-header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.title {
  margin: 0;
  font-size: var(--text-base);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
}

.count {
  margin-left: auto;
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
}

.close-mobile {
  display: none;
  border: none;
  background: transparent;
  color: var(--color-text-tertiary);
  font-size: var(--text-lg);
  line-height: 1;
  cursor: pointer;
  order: 3;
}

.search {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-bg-base);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  padding: var(--space-2) var(--space-3);
  outline: none;
}

.search:focus {
  border-color: var(--color-brand-500);
}

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.actions button {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-full);
  background: var(--color-bg-base);
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
  padding: var(--space-1) var(--space-3);
  cursor: pointer;
}

.actions button:hover {
  border-color: var(--color-border-hover);
  background: var(--color-hover-tint);
}

.actions button.active {
  border-color: var(--color-brand-500);
  background: var(--color-brand-50);
  color: var(--color-brand-700);
}

.hint {
  margin: 0;
  color: var(--color-text-tertiary);
  font-size: var(--text-xs);
}

.dict-list {
  margin: 0;
  padding: 0;
  list-style: none;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.dict-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-sm);
  cursor: pointer;
}

.dict-row:hover {
  background: var(--color-hover-tint);
}

.dict-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--text-sm);
  color: var(--color-text-primary);
}

.dict-lang {
  flex-shrink: 0;
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
}

/* 移动端：侧边栏变成覆盖式抽屉，由外层按钮切换 */
@media (max-width: 640px) {
  .sidebar {
    position: fixed;
    inset: 0 auto 0 0;
    width: min(320px, 86vw);
    z-index: 20;
    border-radius: 0;
    max-height: none;
    transform: translateX(-100%);
    transition: transform 0.2s ease;
    box-shadow: var(--shadow-elevation-2);
  }

  .sidebar.mobile-open {
    transform: translateX(0);
  }

  .close-mobile {
    display: block;
  }
}
</style>
