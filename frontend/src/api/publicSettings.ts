import request from './request'
import type { PublicSettings } from '../types/settings'

export function getPublicSettings() {
  return request.get<never, PublicSettings>('/public/settings')
}
