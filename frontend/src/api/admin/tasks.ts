import request from '../request'
import type { BackgroundTask } from '../../types/backgroundTask'

export function getRunningTasks() {
  return request.get<never, BackgroundTask[]>('/admin/tasks/running')
}

export function getTask(taskId: number) {
  return request.get<never, BackgroundTask>(`/admin/tasks/${taskId}`)
}
