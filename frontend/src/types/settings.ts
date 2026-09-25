export interface PublicSettings {
  open_access: boolean
  allow_registration: boolean
  site_name: string
  initialized: boolean
  search_hint_text: string
}

export interface SystemSettings {
  open_access: boolean
  allow_registration: boolean
  token_default_daily_limit: number
  anonymous_ip_rate_limit_per_min: number
  user_ip_rate_limit_per_min: number
  vocab_max_items_per_owner: number | null
  site_name: string
  search_hint_text: string
}

export type SystemSettingsUpdate = Partial<SystemSettings>

/** 发音实时转码的运行状态。available 为 false 说明容器里没挂 ffmpeg，开关设了也没用 */
