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
  },
  actions: {
    async load() {
      this.settings = await getPublicSettings()
      this.loaded = true
    },
  },
})
