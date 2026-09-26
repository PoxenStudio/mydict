import { defineStore } from 'pinia'
import { getPublicSettings } from '../api/publicSettings'
import type { PublicSettings } from '../types/settings'

export const useSettingsStore = defineStore('settings', {
  state: () => ({
    settings: null as PublicSettings | null,
    loaded: false,
  }),
  getters: {
    siteName: (state) => state.settings?.site_name ?? 'MyDict',
    openAccess: (state) => state.settings?.open_access ?? false,
    allowRegistration: (state) => state.settings?.allow_registration ?? true,
    // 未加载完成前默认 false：在线词典总开关默认禁用，标签在确认开启前不出现
    onlineDictEnabled: (state) => state.settings?.online_dict_enabled ?? false,
    // 未加载完成前默认 true，避免请求返回前先闪现一次跳转
    initialized: (state) => state.settings?.initialized ?? true,
    searchHintText: (state) => state.settings?.search_hint_text ?? '小搜一下, 大进一步',
  },
  actions: {
    async load() {
      this.settings = await getPublicSettings()
      this.loaded = true
    },
  },
})
