export interface BackgroundTask {
  id: number
  task_type: string
  title: string
  status: 'running' | 'success' | 'error'
  progress_data: Record<string, unknown>
  result: Record<string, unknown> | null
  error: string | null
  created_at: string
  updated_at: string
}
