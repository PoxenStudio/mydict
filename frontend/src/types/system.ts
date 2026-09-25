export type SystemPhase = 'starting' | 'migrating' | 'failed' | 'ready'

export interface SystemTask {
  id: number
  title: string
  stage: string | null
  done: number | null
  total: number | null
  elapsed_seconds: number
}

export interface SystemStatus {
  phase: SystemPhase
  blocking: boolean
  message: string | null
  tasks: SystemTask[]
  busy_notice: string | null
}
