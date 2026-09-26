import request from './request'
import type { SystemStatus } from '../types/system'

export interface SystemInfo {
  version: string
}

export function getSystemInfo() {
  return request.get<never, SystemInfo>('/system/info')
}

export function getSystemStatus() {
  return request.get<never, SystemStatus>('/system/status')
}
