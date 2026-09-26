<script setup lang="ts">
import { computed, ref } from 'vue'
import { langLabel } from '../utils/language'
import type { PublicDictionary } from '../types/query'

/**
 * 词典勾选列表（可按名称过滤）。语言/在线标签行已移到 HomeView 的搜索框下方常驻
 * （高频操作不该藏在折叠面板里），本组件只负责「展开后挑具体词典」这个低频动作。
 */
const props = defineProps<{
  dictionaries: PublicDictionary[]
  checkedIds: Set<number>
  loading: boolean
}>()

const emit = defineEmits<{
  toggle: [id: number]
}>()

const keyword = ref('')

const visible = computed(() => {
  const needle = keyword.value.trim().toLowerCase()
  if (!needle) return props.dictionaries
  return props.dictionaries.filter((item) => item.name.toLowerCase().includes(needle))
})
</script>

<template>
  <section class="scope-panel">
    <input v-model="keyword" class="search" type="search" placeholder="筛选词典名" />

    <p v-if="loading" class="hint">正在载入词典列表…</p>
    <p v-else-if="dictionaries.length === 0" class="hint">暂无已启用的词典。</p>
    <p v-else-if="visible.length === 0" class="hint">没有匹配「{{ keyword }}」的词典。</p>

    <ul v-else class="dict-list app-scrollbar">
      <li v-for="item in visible" :key="item.id">
        <!--
          点击处理放在 label 上并 prevent（而不是在 input 上监听 change/click）：
          - 原生 checkbox 会先自己翻转 DOM，状态算回同值时 Vue 不回写，勾选框与真实
            状态错位；
          - 部分 WebKit 内核对 label 内的 checkbox 有双发 click 的怪癖，在 input 上监听
            会一次点击触发两次 toggle（勾上又立刻取消，表现为完全无法勾选）。
          prevent 掉 label 的默认动作（原生翻转 + 转发点击）后，无论哪类浏览器、点行的
          任何位置，都恰好触发一次 toggle，勾选态完全由 Vue 的 :checked 驱动。
        -->
        <label class="dict-row" @click.prevent="emit('toggle', item.id)">
          <!--
            pointer-events:none 让 checkbox 退化为纯受控显示组件：浏览器的原生翻转与
            label 转发被彻底隔离，勾选态 100% 由 :checked 驱动（Thorium/Chrome 实测
            有「计数 0/63 但勾还在」的残留错位）。键盘 space 的 click 仍会冒泡到
            label 正常工作。
          -->
          <input type="checkbox" :checked="checkedIds.has(item.id)" />
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

/* 勾选框是纯受控显示组件：点击统一由 label 的 @click.prevent 接管（见模板内注释） */
.dict-row input {
  pointer-events: none;
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
