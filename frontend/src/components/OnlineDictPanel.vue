<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import SkeletonList from './SkeletonList.vue'
import EmptyState from './EmptyState.vue'
import { lookupOnline } from '../api/dict'
import type { OnlineLookup } from '../types/query'

const props = defineProps<{
  /** 要查询的词（与本地查询共用 submittedWord） */
  word: string
}>()

// 完全自治：加载/错误/结果都在内部渲染，父级只负责把 word 传进来（:key=word 保证换词重挂）
const loading = ref(false)
const error = ref(false)
const data = ref<OnlineLookup | null>(null)

async function run() {
  const word = props.word.trim()
  if (!word) return
  loading.value = true
  error.value = false
  data.value = null
  try {
    // 语言按查询词的字符判断：汉字走中文维基/维基词典的 zh 分区，其余走英文
    const lang = /[\u4e00-\u9fff]/.test(word) ? 'zh' : 'en'
    data.value = await lookupOnline(word, lang)
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
}

onMounted(run)
watch(() => props.word, run)
</script>

<template>
  <div class="online-panel">
    <SkeletonList v-if="loading" :rows="2" />

    <EmptyState
      v-else-if="error"
      title="在线词典查询失败，请重试"
      action-text="重新查询"
      @action="run"
    />

    <div v-else-if="!word" class="empty-hint">输入词语后点【查询】。</div>

    <template v-else>
      <div v-if="data && data.sections.length === 0" class="empty-hint">
        在线词典没有查到「{{ data.word }}」的内容，可以用下面的外部搜索。
      </div>

      <template v-for="section in data?.sections ?? []" :key="section.id">
        <article class="online-card">
          <header class="card-head">
            <div>
              <h2 class="card-title">
                {{ section.title || section.name }}
              </h2>
              <p v-if="section.subtitle" class="card-subtitle">{{ section.subtitle }}</p>
            </div>
            <span class="card-source">{{ section.name }}</span>
          </header>

          <!-- wikipedia / baike：摘要卡片 -->
          <p v-if="section.text" class="card-text">{{ section.text }}</p>

          <!-- wiktionary：按词性分组的释义 -->
          <div v-for="entry in section.entries ?? []" :key="entry.pos" class="wt-entry">
            <h3 class="wt-pos">{{ entry.pos }}</h3>
            <ol class="wt-senses">
              <li v-for="(sense, si) in entry.senses" :key="si">
                {{ sense.text }}
                <ul v-if="sense.examples.length" class="wt-examples">
                  <li v-for="(example, ei) in sense.examples" :key="ei">{{ example }}</li>
                </ul>
              </li>
            </ol>
          </div>

          <p v-if="section.url" class="card-link">
            <a :href="section.url" target="_blank" rel="noopener noreferrer">
              在 {{ section.name }} 查看原文 →
            </a>
          </p>
        </article>
      </template>

      <div v-if="data && data.links.length" class="link-row">
        <a
          v-for="link in data.links"
          :key="link.name"
          class="link-chip"
          :href="link.url"
          target="_blank"
          rel="noopener noreferrer"
        >
          {{ link.name }} ↗
        </a>
      </div>
    </template>
  </div>
</template>

<style scoped>
.online-panel {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.empty-hint {
  color: var(--color-text-tertiary);
  font-size: var(--text-sm);
}

.online-card {
  background: var(--color-bg-surface);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-elevation-1);
  padding: var(--space-4);
}

.card-head {
  display: flex;
  align-items: baseline;
  gap: var(--space-3);
  margin-bottom: var(--space-2);
}

.card-title {
  margin: 0;
  font-size: var(--text-lg);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
}

.card-subtitle {
  margin: 2px 0 0;
  font-size: var(--text-sm);
  color: var(--color-text-tertiary);
}

.card-source {
  margin-left: auto;
  flex-shrink: 0;
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-full);
  padding: 1px var(--space-2);
}

.card-text {
  margin: 0;
  line-height: 1.7;
  color: var(--color-text-primary);
  font-size: var(--text-sm);
}

.wt-entry {
  margin-top: var(--space-3);
}

.wt-pos {
  margin: 0 0 var(--space-1);
  font-size: var(--text-sm);
  font-style: italic;
  color: var(--color-text-secondary);
}

.wt-senses {
  margin: 0;
  padding-left: 1.5em;
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  line-height: 1.7;
}

.wt-examples {
  margin: var(--space-1) 0 0;
  padding-left: 1.2em;
  list-style-type: disc;
  color: var(--color-text-tertiary);
  font-size: var(--text-xs);
}

.card-link {
  margin: var(--space-3) 0 0;
  font-size: var(--text-sm);
}

.card-link a,
.link-chip {
  color: var(--color-brand-700);
  text-decoration: none;
}

.card-link a:hover,
.link-chip:hover {
  text-decoration: underline;
}

.link-row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.link-chip {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-full);
  background: var(--color-bg-surface);
  padding: var(--space-1) var(--space-3);
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.link-chip:hover {
  border-color: var(--color-border-hover);
  background: var(--color-hover-tint);
  text-decoration: none;
}
</style>
