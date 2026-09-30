<script setup lang="ts">
import { computed, ref } from 'vue'
import EntryFrame from './EntryFrame.vue'
import { getVocabEntryHtml } from '../api/dict'
import { dictAccentColor } from '../utils/dictAccent'
import { formatAge } from '../utils/format'
import type { VocabItem } from '../types/vocab'

const props = defineProps<{ item: VocabItem }>()
const emit = defineEmits<{ remove: [item: VocabItem] }>()

const expanded = ref(false)
// 首次展开才挂载 EntryFrame，之后折叠只收高度，避免重复请求
const mounted = ref(false)

const age = computed(() => formatAge(props.item.created_at))
const accent = computed(() => dictAccentColor(props.item.dictionary_id))

function toggle() {
  expanded.value = !expanded.value
  if (expanded.value) mounted.value = true
}
</script>

<template>
  <div class="vocab-card" :class="{ accented: accent }" :style="{ '--vocab-card-accent': accent }">
    <div class="card-header" @click="toggle">
      <div class="title">
        <span class="word" :title="item.word">{{ item.word }}</span>
        <span v-if="item.dictionary_name" class="dict-name" :title="item.dictionary_name">
          {{ item.dictionary_name }}
        </span>
      </div>
      <span class="age">{{ age }}</span>
      <button
        type="button"
        class="toggle-btn"
        :class="{ open: expanded }"
        :aria-expanded="expanded"
        :aria-label="expanded ? '收起词条' : '展开词条'"
        @click.stop="toggle"
      >
        ›
      </button>
    </div>
    <!-- 折叠收高度而非 display:none：隐藏的 iframe 会按 0 宽度排版并上报异常高度 -->
    <div v-if="mounted" class="card-body" :class="{ collapsed: !expanded }" :inert="!expanded">
      <div class="body-scroll app-scrollbar">
        <p v-if="item.phonetic" class="phonetic">[{{ item.phonetic }}]</p>
        <EntryFrame
          v-if="item.definition"
          :key="item.id"
          class="definition"
          :loader="() => getVocabEntryHtml(item.id)"
        />
        <p v-if="item.note" class="note">备注：{{ item.note }}</p>
      </div>
      <div class="actions">
        <button type="button" class="remove-btn" @click="emit('remove', item)">删除</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.vocab-card {
  background: var(--color-bg-surface);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-elevation-1);
  padding: var(--space-2) var(--space-4);
  min-width: 0;
}

/* 左侧 3px 词典色条（一次性值）；用内阴影而不是 border-left，才能贴合圆角且不挤占内容宽度 */
.vocab-card.accented {
  box-shadow:
    inset 3px 0 0 var(--vocab-card-accent),
    var(--shadow-elevation-1);
}

.card-header {
  /* 字号阶梯外的一次性值：单词/展开按钮 28px 要比页面标题更醒目，词典名 10px 只作弱提示 */
  --vocab-card-title-size: 28px;
  --vocab-card-dict-size: 10px;
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
  cursor: pointer;
  user-select: none;
}

.title {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.word {
  min-width: 0;
  font-size: var(--vocab-card-title-size);
  font-weight: var(--font-weight-bold);
  line-height: var(--leading-heading);
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dict-name {
  min-width: 0;
  font-size: var(--vocab-card-dict-size);
  font-weight: var(--font-weight-regular);
  color: var(--color-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.age {
  flex-shrink: 0;
  margin-left: auto;
  font-size: var(--text-sm);
  font-weight: var(--font-weight-regular);
  color: var(--color-text-secondary);
  white-space: nowrap;
}

.toggle-btn {
  flex-shrink: 0;
  width: var(--size-control-md);
  height: var(--size-control-md);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--color-text-tertiary);
  font-size: var(--vocab-card-title-size);
  line-height: var(--leading-control);
  cursor: pointer;
  transition: transform 0.15s ease;
}

.toggle-btn:hover {
  background: var(--color-hover-tint);
  color: var(--color-text-primary);
}

.toggle-btn.open {
  transform: rotate(90deg);
}

.card-body {
  margin-top: var(--space-2);
}

.body-scroll {
  max-height: var(--size-scroll-md);
  overflow-y: auto;
}

.card-body.collapsed {
  height: 0;
  margin-top: 0;
  overflow: hidden;
  visibility: hidden;
}

.phonetic {
  margin: 0 0 var(--space-2);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.definition {
  display: block;
}

.note {
  margin-top: var(--space-2);
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
}

.actions {
  display: flex;
  justify-content: flex-end;
  margin-top: var(--space-2);
}

.remove-btn {
  border: none;
  background: none;
  color: var(--color-danger);
  cursor: pointer;
  font-size: var(--text-sm);
}
</style>
