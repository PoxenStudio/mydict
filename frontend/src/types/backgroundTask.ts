export interface BackgroundTask {
  id: number
  task_type: string
  title: string
  status: string
  progress_data: Record<string, unknown>
  created_at: string
  updated_at: string
}
