import { onBeforeUnmount } from 'vue'
import * as tasksApi from '../api/admin/tasks'
import type { BackgroundTask } from '../types/backgroundTask'

const POLL_INTERVAL_MS = 1000
const POLL_TIMEOUT_MS = 60 * 60 * 1000
const POLL_MAX_CONSECUTIVE_FAILURES = 3

export class PollAbortedError extends Error {}

function sleep(ms: number) {
  return new Promise<void>((resolve) => setTimeout(resolve, ms))
}

function isAxiosError(err: unknown) {
  return !!(err as { isAxiosError?: boolean } | null)?.isAxiosError
}

// result 是 Record<string, unknown>，逐字段收窄
export function resultNumber(task: BackgroundTask, key: string): number | null {
  const value = task.result?.[key]
  return typeof value === 'number' ? value : null
}

export function resultString(task: BackgroundTask, key: string): string | null {
  const value = task.result?.[key]
  return typeof value === 'string' ? value : null
}

export function errorMessage(err: unknown): string {
  const serverMessage = (err as { response?: { data?: { message?: string } } })?.response?.data
    ?.message
  if (serverMessage) return serverMessage
  return err instanceof Error ? err.message : '导入失败'
}

// 导入接口立即返回 task_id，解析入库在后端线程跑，这里轮询任务状态直到成功/失败；
// 组件卸载后停止轮询并抛 PollAbortedError
export function useImportTask() {
  let unmounted = false
  onBeforeUnmount(() => {
    unmounted = true
  })

  async function waitForImportTask(taskId: number): Promise<BackgroundTask> {
    const deadline = Date.now() + POLL_TIMEOUT_MS
    let failures = 0
    while (!unmounted) {
      try {
        const task = await tasksApi.getTask(taskId)
        failures = 0
        if (task.status === 'success') return task
        if (task.status === 'error') throw new Error(task.error ?? '导入失败')
      } catch (err) {
        // 任务自身失败直接抛出；偶发的轮询请求失败容忍几次，任务在后端仍在跑
        if (!isAxiosError(err)) throw err
        failures += 1
        if (failures >= POLL_MAX_CONSECUTIVE_FAILURES) throw err
      }
      if (Date.now() > deadline) throw new Error('等待导入超时，请稍后在词典列表确认是否已完成')
      await sleep(POLL_INTERVAL_MS)
    }
    throw new PollAbortedError()
  }

  return { waitForImportTask, isUnmounted: () => unmounted }
}

export { isAxiosError }
