import { defineStore } from 'pinia'
import * as adminAuthApi from '../api/admin/auth'
import { clearTokens, isLoggedInRef, setAccessToken } from '../utils/authStorage'
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
      setAccessToken('admin', tokens.access_token)
      await this.loadProfile()
    },
    async login(username: string, password: string) {
      const tokens = await adminAuthApi.login(username, password)
      setAccessToken('admin', tokens.access_token)
      await this.loadProfile()
    },
    async loadProfile() {
      this.profile = await adminAuthApi.fetchMe()
    },
    logout() {
      // 先清本地（界面立刻退出），再通知服务端清掉 HttpOnly 会话 cookie；失败无所谓
      clearTokens('admin')
      this.profile = null
      void adminAuthApi.logout().catch(() => undefined)
    },
  },
})
