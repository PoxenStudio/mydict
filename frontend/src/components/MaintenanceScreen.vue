<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useSystemStatusStore } from '../stores/systemStatus'
import type { SystemTask } from '../types/system'
import { formatDuration } from '../utils/format'

const store = useSystemStatusStore()
const now = ref(Date.now())
let ticker: ReturnType<typeof setInterval> | undefined

const failed = computed(() => store.status?.phase === 'failed')

const heading = computed(() => {
  switch (store.status?.phase) {
    case 'migrating':
      return '正在升级数据库'
    case 'failed':
      return '服务暂不可用'
    default:
      return '服务正在启动'
  }
})

function stepText(task: SystemTask) {
  if (task.done === null || task.total === null) return task.stage ?? ''
  const step = `第 ${Math.min(task.done + 1, task.total)}/${task.total} 步`
  return task.stage ? `${step}：${task.stage}` : step
}

function elapsedText(task: SystemTask) {
  const drift = (now.value - store.receivedAt) / 1000
  return `已用时 ${formatDuration(task.elapsed_seconds + drift)}`
}

onMounted(() => {
  ticker = setInterval(() => {
    now.value = Date.now()
  }, 1000)
})

onUnmounted(() => {
  clearInterval(ticker)
})
</script>

<template>
  <div class="maintenance">
    <section class="card" role="status" aria-live="polite">
      <img class="logo" src="/logo.png" alt="" />
      <h1 :class="{ failed }">{{ heading }}</h1>
      <p v-if="store.status?.message" class="message">{{ store.status.message }}</p>

      <div v-for="task in store.status?.tasks ?? []" :key="task.id" class="task">
        <div class="task-head">
          <span class="task-title">{{ task.title }}</span>
          <span class="task-elapsed">{{ elapsedText(task) }}</span>
        </div>
        <p class="task-stage">{{ stepText(task) }}</p>
        <el-progress :percentage="100" :indeterminate="true" :show-text="false" :duration="3" />
      </div>

      <p v-if="!failed" class="hint">完成后页面会自动刷新，请勿重启服务。</p>
    </section>
  </div>
</template>

<style scoped>
.maintenance {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-4);
  background: var(--color-bg-base);
}

.card {
  width: 100%;
  max-width: var(--size-dialog-md);
  background: var(--color-bg-surface);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-elevation-2);
  padding: var(--space-7) var(--space-6);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  text-align: center;
}

.logo {
  width: var(--size-control-lg);
  height: var(--size-control-lg);
}

h1 {
  margin: 0;
  font-size: var(--text-xl);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

h1.failed {
  color: var(--color-danger);
}

.message {
  margin: 0;
  font-size: var(--text-sm);
  line-height: var(--leading-body);
  color: var(--color-text-secondary);
}

.task {
  width: 100%;
  margin-top: var(--space-2);
  padding-top: var(--space-4);
  border-top: 1px solid var(--color-border);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  text-align: left;
}

.task-head {
  display: flex;
  justify-content: space-between;
  gap: var(--space-3);
  font-size: var(--text-sm);
}

.task-title {
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
}

.task-elapsed {
  color: var(--color-text-tertiary);
  font-variant-numeric: tabular-nums;
}

.task-stage {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.hint {
  margin: var(--space-2) 0 0;
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
}
</style>
