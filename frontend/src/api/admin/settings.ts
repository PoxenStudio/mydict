import request from '../request'
import type {
  SpxTranscodeStatus,
  SystemSettings,
  SystemSettingsUpdate,
} from '../../types/settings'

export function getSettings() {
  return request.get<never, SystemSettings>('/admin/settings')
}

export function updateSettings(update: SystemSettingsUpdate) {
  return request.put<never, SystemSettings>('/admin/settings', update)
}

/** 发音转码的运行状态：容器里有没有 ffmpeg、已经转了多少。refresh 忽略后端探测缓存。 */
export function getSpxTranscodeStatus(refresh = false) {
  return request.get<never, SpxTranscodeStatus>('/admin/settings/spx-transcode', {
    params: refresh ? { refresh: true } : undefined,
  })
}
