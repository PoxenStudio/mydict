<script setup lang="ts">
import { useRunningTasks } from '../../composables/useRunningTasks'
import { taskLabel, taskProgressText } from '../../utils/backgroundTask'
import { formatDuration } from '../../utils/format'
import type { BackgroundTask } from '../../types/backgroundTask'

const { tasks, loaded } = useRunningTasks()

function elapsedText(task: BackgroundTask) {
  return formatDuration((Date.now() - new Date(task.created_at).getTime()) / 1000)
}
</script>

<template>
  <section class="panel">
    <h2>后台任务</h2>
    <p v-if="loaded && tasks.length === 0" class="empty">当前没有正在运行的任务</p>
    <ul v-else class="task-list">
      <li v-for="task in tasks" :key="task.id" class="task-row">
        <div class="task-head">
          <span class="task-name">{{ taskLabel(task) }} · {{ task.title }}</span>
          <span class="task-elapsed">已用时 {{ elapsedText(task) }}</span>
        </div>
        <span class="task-progress">{{ taskProgressText(task) }}</span>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.panel {
  background: var(--color-bg-surface);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-elevation-1);
  padding: var(--space-5);
}

h2 {
  font-size: var(--text-md);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
  margin: 0 0 var(--space-3);
}

.empty {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--color-text-tertiary);
}

.task-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.task-row {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding: var(--space-3) 0;
  border-top: 1px solid var(--color-border);
  font-size: var(--text-sm);
}

.task-row:first-child {
  border-top: none;
  padding-top: 0;
}

.task-head {
  display: flex;
  justify-content: space-between;
  gap: var(--space-3);
}

.task-name {
  color: var(--color-text-primary);
}

.task-elapsed,
.task-progress {
  color: var(--color-text-tertiary);
  font-size: var(--text-xs);
}

.task-elapsed {
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
}
</style>
