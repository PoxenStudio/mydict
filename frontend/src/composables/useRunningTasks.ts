import { onMounted, onUnmounted, ref } from 'vue'
import { getRunningTasks } from '../api/admin/tasks'
import type { BackgroundTask } from '../types/backgroundTask'

const POLL_INTERVAL_MS = 5000

export function useRunningTasks() {
  const tasks = ref<BackgroundTask[]>([])
  const loaded = ref(false)
  let timer: ReturnType<typeof setInterval> | undefined

  async function poll() {
    try {
      tasks.value = await getRunningTasks()
      loaded.value = true
    } catch {
      // 轮询失败不打扰用户，下一轮再试
    }
  }

  onMounted(() => {
    poll()
    timer = setInterval(poll, POLL_INTERVAL_MS)
  })

  onUnmounted(() => {
    clearInterval(timer)
  })

  return { tasks, loaded }
}
