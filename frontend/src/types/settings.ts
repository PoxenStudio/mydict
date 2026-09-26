export interface PublicSettings {
  open_access: boolean
  allow_registration: boolean
  /** 在线词典总开关（管理后台默认禁用）；前台据此决定是否渲染【在线】标签 */
  online_dict_enabled: boolean
  site_name: string
  initialized: boolean
  search_hint_text: string
}

export interface SystemSettings {
  open_access: boolean
  allow_registration: boolean
  online_dict_enabled: boolean
  token_default_daily_limit: number
  anonymous_ip_rate_limit_per_min: number
  user_ip_rate_limit_per_min: number
  vocab_max_items_per_owner: number | null
  site_name: string
  search_hint_text: string
  /** 在线词典出站代理；空串表示直连 */
  online_dict_proxy: string
  /** 启用的在线词典源 CSV；空串表示全部启用 */
  online_dict_sources: string
}

export type SystemSettingsUpdate = Partial<SystemSettings>
