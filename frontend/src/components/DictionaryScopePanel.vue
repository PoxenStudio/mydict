<script setup lang="ts">
import { computed, ref } from 'vue'
import { ZH_CODES, langLabel } from '../utils/language'
import type { PublicDictionary } from '../types/query'

const props = defineProps<{
  dictionaries: PublicDictionary[]
  checkedIds: Set<number>
  loading: boolean
  /** 是否正在按勾选收窄范围（false = 检索全部） */
  isFiltering: boolean
}>()

const emit = defineEmits<{
  toggle: [id: number]
  selectAll: []
  selectLanguage: [langFrom: string]
}>()

const keyword = ref('')

const visible = computed(() => {
  const needle = keyword.value.trim().toLowerCase()
  if (!needle) return props.dictionaries
  return props.dictionaries.filter((item) => item.name.toLowerCase().includes(needle))
})

// 中文系（含早期数据里的裸 zh）在界面上合成一个按钮：查询路由本来就不区分简繁
// （输入汉字时三种码都算「优先语言」），拆成两个按钮只会让「只看中文词典」要点两次。
// ZH_CODES 与词典管理页的语种 tab 共用同一份定义，避免两处各写一遍。
// 中文按钮的循环顺序：中文（全部）→ 简中 → 繁中 → 中文…
const ZH_SCOPES = ['zh', 'zh-Hans', 'zh-Hant']
const ZH_SCOPE_LABELS: Record<string, string> = {
  zh: '中文',
  'zh-Hans': '简中',
  'zh-Hant': '繁中',
}

/** 每个筛选范围对应的 lang_from 取值；不在表里的按原样精确匹配 */
const SCOPE_CODES: Record<string, string[]> = {
  zh: ZH_CODES,
  'zh-Hans': ['zh-Hans'],
  'zh-Hant': ['zh-Hant'],
}

/** 库里出现过的语言筛选项，按出现顺序去重；中文系合并成一项 */
const languageScopes = computed(() => {
  const scopes: string[] = []
  let zhAdded = false
  for (const item of props.dictionaries) {
    const code = item.lang_from
    if (ZH_CODES.includes(code)) {
      if (!zhAdded) {
        zhAdded = true
        scopes.push('zh')
      }
      continue
    }
    if (!scopes.includes(code)) scopes.push(code)
  }
  return scopes
})

/** 当前勾选集是否恰好等于某个筛选范围的全部词典 */
function matchesScope(scope: string): boolean {
  const codes = SCOPE_CODES[scope] ?? [scope]
  const ids = props.dictionaries
    .filter((item) => codes.includes(item.lang_from))
    .map((item) => item.id)
  return (
    ids.length > 0 &&
    ids.length === props.checkedIds.size &&
    ids.every((id) => props.checkedIds.has(id))
  )
}

/** 中文按钮当前落在哪一态；不在任何一种中文范围里时为 null（按钮显示默认的「中文」） */
const activeZhScope = computed<string | null>(() => {
  if (!props.isFiltering) return null
  for (const scope of ZH_SCOPES) {
    if (matchesScope(scope)) return scope
  }
  return null
})

function scopeLabel(scope: string): string {
  return scope === 'zh' ? ZH_SCOPE_LABELS[activeZhScope.value ?? 'zh'] : langLabel(scope)
}

function selectScope(scope: string) {
  if (scope !== 'zh') {
    emit('selectLanguage', scope)
    return
  }
  // 中文按钮：在三种范围之间循环
  const index = activeZhScope.value ? ZH_SCOPES.indexOf(activeZhScope.value) : -1
  emit('selectLanguage', ZH_SCOPES[(index + 1) % ZH_SCOPES.length])
}
</script>

<template>
  <section class="scope-panel">
    <input v-model="keyword" class="search" type="search" placeholder="筛选词典名" />

    <div class="actions">
      <button type="button" :class="{ active: !isFiltering }" @click="emit('selectAll')">
        全部
      </button>
      <button
        v-for="scope in languageScopes"
        :key="scope"
        type="button"
        :class="{ active: matchesScope(scope) }"
        @click="selectScope(scope)"
      >
        {{ scopeLabel(scope) }}
      </button>
    </div>

    <p v-if="!loading && !isFiltering" class="hint">未限制范围：检索全部已启用词典</p>

    <p v-if="loading" class="hint">正在载入词典列表…</p>
    <p v-else-if="dictionaries.length === 0" class="hint">暂无已启用的词典。</p>
    <p v-else-if="visible.length === 0" class="hint">没有匹配「{{ keyword }}」的词典。</p>

    <ul v-else class="dict-list app-scrollbar">
      <li v-for="item in visible" :key="item.id">
        <label class="dict-row">
          <input
            type="checkbox"
            :checked="checkedIds.has(item.id)"
            @change="emit('toggle', item.id)"
          />
          <span class="dict-name" :title="`[${langLabel(item.lang_from)}]${item.name}`">
            <span class="dict-lang">[{{ langLabel(item.lang_from) }}]</span>{{ item.name }}
          </span>
        </label>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.scope-panel {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  background: var(--color-bg-surface);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-elevation-1);
  padding: var(--space-4);
  text-align: left;
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

/* 面板与搜索框同宽，词典多时排成多列（240px 是多数「[语言]词典名」能完整显示的列宽），超出高度在列表内滚动 */
.dict-list {
  margin: 0;
  padding: 0;
  list-style: none;
  max-height: var(--size-scroll-md);
  overflow-y: auto;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: var(--space-1) var(--space-3);
}

.dict-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-sm);
  cursor: pointer;
}

.dict-row input {
  accent-color: var(--color-brand-500);
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
  color: var(--color-text-tertiary);
}
</style>
