<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import { getRunningTasks } from '../../api/admin/tasks'
import type { BackgroundTask } from '../../types/backgroundTask'

const tasks = ref<BackgroundTask[]>([])
let timer: ReturnType<typeof setInterval> | undefined

const TASK_TYPE_LABELS: Record<string, string> = {
  dictionary_import: '词典导入',
  dictionary_spx_scan: '发音资源扫描',
  dictionary_spx_transcode: '发音转码',
  dictionary_source_repair: '从源文件修复',
  dictionary_reparse: '重新解析词典',
}

function taskLabel(task: BackgroundTask) {
  return TASK_TYPE_LABELS[task.task_type] ?? task.task_type
}

function taskProgressText(task: BackgroundTask) {
  const { done, total } = task.progress_data
  // 扫描/转码按「已完成 / 总数」报进度；词典导入报的是已写入的词条数，没有总数
  if (typeof done === 'number' && typeof total === 'number' && total > 0) {
    return `已处理 ${done.toLocaleString()} / ${total.toLocaleString()}`
  }
  return typeof done === 'number' ? `已处理 ${done.toLocaleString()} 条` : '处理中…'
}

async function poll() {
  try {
    tasks.value = await getRunningTasks()
  } catch {
    // 轮询失败不打扰用户，下一轮再试
  }
}

onMounted(() => {
  poll()
  timer = setInterval(poll, 5000)
})

onUnmounted(() => {
  clearInterval(timer)
})
</script>

<template>
  <el-popover v-if="tasks.length > 0" placement="bottom-end" width="320" trigger="click">
    <template #reference>
      <el-button circle text class="tasks-btn" :icon="Loading" title="后台任务" />
    </template>
    <p class="tasks-title">后台任务（{{ tasks.length }}）</p>
    <div v-for="task in tasks" :key="task.id" class="task-row">
      <span class="task-name">{{ taskLabel(task) }} · {{ task.title }}</span>
      <span class="task-progress">{{ taskProgressText(task) }}</span>
    </div>
  </el-popover>
</template>

<style scoped>
.tasks-btn {
  color: var(--color-brand-600);
  animation: tasks-spin 1.6s linear infinite;
}

@keyframes tasks-spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

.tasks-title {
  margin: 0 0 var(--space-2);
  font-size: var(--text-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
}

.task-row {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding: var(--space-2) 0;
  border-top: 1px solid var(--color-border);
  font-size: var(--text-sm);
}

.task-name {
  color: var(--color-text-primary);
}

.task-progress {
  color: var(--color-text-tertiary);
  font-size: var(--text-xs);
}
</style>
