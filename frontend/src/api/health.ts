import request from './request'

export interface HealthStatus {
  status: string
}

export function getHealth() {
  return request.get<never, HealthStatus>('/health')
}
