import request from '../request'
import type { SystemSettings, SystemSettingsUpdate } from '../../types/settings'

export function getSettings() {
  return request.get<never, SystemSettings>('/admin/settings')
}

export function updateSettings(update: SystemSettingsUpdate) {
  return request.put<never, SystemSettings>('/admin/settings', update)
}
