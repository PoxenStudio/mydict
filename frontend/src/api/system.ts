import request from './request'

export interface SystemInfo {
  version: string
}

export function getSystemInfo() {
  return request.get<never, SystemInfo>('/system/info')
}
