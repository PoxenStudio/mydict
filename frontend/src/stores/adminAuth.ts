import { defineStore } from 'pinia'
import * as adminAuthApi from '../api/admin/auth'
import { clearTokens, isLoggedInRef, setTokens } from '../utils/authStorage'
import type { AdminPublic } from '../types/auth'

export const useAdminAuthStore = defineStore('adminAuth', {
  state: () => ({
    profile: null as AdminPublic | null,
  }),
  getters: {
    isLoggedIn: () => isLoggedInRef('admin').value,
  },
  actions: {
    async setup(username: string, password: string) {
      const tokens = await adminAuthApi.setup(username, password)
      setTokens('admin', tokens.access_token, tokens.refresh_token)
      await this.loadProfile()
    },
    async login(username: string, password: string) {
      const tokens = await adminAuthApi.login(username, password)
      setTokens('admin', tokens.access_token, tokens.refresh_token)
      await this.loadProfile()
    },
    async loadProfile() {
      this.profile = await adminAuthApi.fetchMe()
    },
    logout() {
      clearTokens('admin')
      this.profile = null
    },
  },
})
