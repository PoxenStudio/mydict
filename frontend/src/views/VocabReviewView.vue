<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import NavBar from '../components/NavBar.vue'
import { getDueVocab, reviewVocab } from '../api/vocab'
import type { VocabCounts, VocabItem } from '../types/vocab'

const router = useRouter()

const items = ref<VocabItem[]>([])
const counts = ref<VocabCounts>({ total: 0, new: 0, due: 0 })
const loading = ref(true)
const revealed = ref(false)
const submitting = ref(false)
const finished = ref(false)
const reviewedCount = ref(0)

const current = computed<VocabItem | null>(() => items.value[0] ?? null)
// 本次会话的进度：已评分数 /（已评分 + 手上还剩的）
const progress = computed(() => {
  const done = reviewedCount.value
  const total = done + items.value.length
  return total === 0 ? 0 : Math.round((done / total) * 100)
})

/** 释义快照可能是 HTML，复习卡片只用纯文本（不注入） */
const definitionText = computed(() => {
  const raw = current.value?.definition
  if (!raw) return ''
  const doc = new DOMParser().parseFromString(raw, 'text/html')
  return (doc.body.textContent ?? '').replace(/\s+\n/g, '\n').trim()
})

async function load() {
  loading.value = true
  try {
    const resp = await getDueVocab()
    items.value = resp.items
    counts.value = resp.counts
    if (items.value.length === 0) finished.value = true
  } catch {
    ElMessage.error('加载复习卡片失败')
  } finally {
    loading.value = false
  }
}

async function rate(rating: number) {
  const item = current.value
  if (!item || !revealed.value || submitting.value) return
  submitting.value = true
  try {
    const resp = await reviewVocab(item.id, rating)
    counts.value = resp.counts
    reviewedCount.value += 1
    items.value.shift()
    revealed.value = false
    if (items.value.length === 0) {
      // 一次只取一小批，用完再看还有没有（可能还有到期更晚的）
      const next = await getDueVocab()
      items.value = next.items
      counts.value = next.counts
      if (items.value.length === 0) finished.value = true
    }
  } catch {
    ElMessage.error('提交失败，请重试')
  } finally {
    submitting.value = false
  }
}

function onKeydown(event: KeyboardEvent) {
  if (finished.value || !current.value || submitting.value) return
  if (!revealed.value && (event.code === 'Space' || event.key === 'Enter')) {
    event.preventDefault()
    revealed.value = true
    return
  }
  if (revealed.value && ['1', '2', '3', '4'].includes(event.key)) {
    event.preventDefault()
    void rate(Number(event.key))
  }
}

function restart() {
  finished.value = false
  reviewedCount.value = 0
  void load()
}

onMounted(() => {
  void load()
  window.addEventListener('keydown', onKeydown)
})
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <div class="page">
    <NavBar />
    <main class="review-page">
      <header class="head">
        <button type="button" class="back" @click="router.push('/vocab')">← 生词本</button>
        <div class="counts">
          <span class="chip due">到期 {{ counts.due }}</span>
          <span class="chip new">新词 {{ counts.new }}</span>
          <span class="chip done">本次已复习 {{ reviewedCount }}</span>
        </div>
      </header>

      <div v-if="!finished" class="bar" role="progressbar" :aria-valuenow="progress">
        <span :style="{ width: `${progress}%` }" />
      </div>

      <div v-if="loading" class="card placeholder">正在取卡片…</div>

      <div v-else-if="finished" class="card done">
        <h2>{{ reviewedCount > 0 ? '这一轮复习完了' : '现在没有到期的卡片' }}</h2>
        <p>
          本次复习 <strong>{{ reviewedCount }}</strong> 条<template v-if="counts.due + counts.new > 0">
            ，还剩 {{ counts.due + counts.new }} 条可以继续</template
          >。
        </p>
        <div class="done-actions">
          <el-button v-if="counts.due + counts.new > 0" type="primary" @click="restart">
            再来一轮
          </el-button>
          <el-button @click="router.push('/vocab')">返回生词本</el-button>
        </div>
      </div>

      <template v-else-if="current">
        <section class="card front">
          <div class="word">{{ current.word }}</div>
          <div v-if="current.phonetic" class="phonetic">{{ current.phonetic }}</div>
          <div v-if="current.dictionary_name" class="source">{{ current.dictionary_name }}</div>

          <div v-if="revealed" class="answer">
            <p v-if="definitionText" class="definition">{{ definitionText }}</p>
            <p v-else class="definition muted">（收藏时没有取到释义，可回生词本查看原词条）</p>
            <p v-if="current.note" class="note">笔记：{{ current.note }}</p>
          </div>
          <div v-else class="hint">按空格显示答案</div>
        </section>

        <div class="actions">
          <template v-if="!revealed">
            <el-button type="primary" size="large" @click="revealed = true">显示答案</el-button>
          </template>
          <template v-else>
            <button type="button" class="rate again" :disabled="submitting" @click="rate(1)">
              <span class="k">1</span>重来
            </button>
            <button type="button" class="rate hard" :disabled="submitting" @click="rate(2)">
              <span class="k">2</span>困难
            </button>
            <button type="button" class="rate good" :disabled="submitting" @click="rate(3)">
              <span class="k">3</span>记得
            </button>
            <button type="button" class="rate easy" :disabled="submitting" @click="rate(4)">
              <span class="k">4</span>简单
            </button>
          </template>
        </div>
      </template>
    </main>
  </div>
</template>

<style scoped>
.page {
  min-height: 100vh;
  background: var(--color-bg-base);
}

.review-page {
  max-width: 720px;
  margin: 0 auto;
  padding: var(--space-6) var(--space-4) var(--space-10);
}

.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}

.back {
  border: 0;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  cursor: pointer;
  padding: var(--space-1) 0;
}
.back:hover {
  color: var(--color-brand-600);
}

.counts {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.chip {
  font-size: var(--text-xs);
  padding: 2px 8px;
  border-radius: var(--radius-full);
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border);
  color: var(--color-text-secondary);
}
.chip.due {
  color: var(--color-warning);
}
.chip.new {
  color: var(--color-brand-600);
}

.bar {
  height: 4px;
  border-radius: var(--radius-full);
  background: var(--color-border);
  overflow: hidden;
  margin-bottom: var(--space-4);
}
.bar > span {
  display: block;
  height: 100%;
  background: var(--color-brand-500);
  transition: width 160ms ease;
}

.card {
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-card);
  padding: var(--space-8) var(--space-6);
  min-height: 260px;
}

.card.placeholder,
.card.done {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  color: var(--color-text-secondary);
}

.card.done h2 {
  margin: 0 0 var(--space-3);
  color: var(--color-text-primary);
}
.done-actions {
  display: flex;
  gap: var(--space-3);
  margin-top: var(--space-5);
}

.front {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
}

.word {
  font-size: clamp(1.8rem, 4vw, 2.6rem);
  font-weight: 600;
  color: var(--color-text-primary);
  letter-spacing: 0.01em;
}

.phonetic {
  margin-top: var(--space-2);
  color: var(--color-text-secondary);
  font-size: var(--text-lg);
}

.source {
  margin-top: var(--space-2);
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
}

.answer {
  margin-top: var(--space-6);
  width: 100%;
  text-align: left;
  border-top: 1px dashed var(--color-border);
  padding-top: var(--space-4);
  max-height: 46vh;
  overflow-y: auto;
}

.definition {
  margin: 0;
  white-space: pre-wrap;
  line-height: 1.7;
  color: var(--color-text-primary);
}
.definition.muted {
  color: var(--color-text-tertiary);
}

.note {
  margin: var(--space-3) 0 0;
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.hint {
  margin-top: var(--space-6);
  font-size: var(--text-sm);
  color: var(--color-text-tertiary);
}

.actions {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-3);
  margin-top: var(--space-5);
}

.actions > .el-button {
  grid-column: 1 / -1;
}

.rate {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: var(--space-3) var(--space-2);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border);
  background: var(--color-bg-surface);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  cursor: pointer;
  transition:
    transform 120ms ease,
    border-color 120ms ease;
}
.rate:hover:not(:disabled) {
  border-color: var(--color-border-hover);
  transform: translateY(-1px);
}
.rate:disabled {
  opacity: 0.6;
  cursor: default;
}
.rate .k {
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
}
.rate.again {
  border-color: color-mix(in srgb, var(--color-danger) 35%, var(--color-border));
}
.rate.hard {
  border-color: color-mix(in srgb, var(--color-warning) 35%, var(--color-border));
}
.rate.good {
  border-color: color-mix(in srgb, var(--color-brand-500) 45%, var(--color-border));
}
.rate.easy {
  border-color: color-mix(in srgb, var(--color-info) 35%, var(--color-border));
}

@media (max-width: 640px) {
  .review-page {
    padding: var(--space-4) var(--space-3) var(--space-8);
  }
  .card {
    min-height: 200px;
    padding: var(--space-6) var(--space-4);
  }
}
</style>
