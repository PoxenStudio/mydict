import { defineStore } from 'pinia'
import * as authApi from '../api/auth'
import { clearTokens, isLoggedInRef, setAccessToken } from '../utils/authStorage'
import type { UserPublic } from '../types/auth'

export const useUserAuthStore = defineStore('userAuth', {
  state: () => ({
    profile: null as UserPublic | null,
  }),
  getters: {
    isLoggedIn: () => isLoggedInRef('user').value,
  },
  actions: {
    async login(username: string, password: string) {
      const tokens = await authApi.login(username, password)
      setAccessToken('user', tokens.access_token)
      await this.loadProfile()
    },
    async register(username: string, password: string, email?: string) {
      await authApi.register(username, password, email)
    },
    async loadProfile() {
      this.profile = await authApi.fetchMe()
    },
    logout() {
      // 先清本地（界面立刻退出），再通知服务端清掉 HttpOnly 会话 cookie；失败无所谓
      clearTokens('user')
      this.profile = null
      void authApi.logout().catch(() => undefined)
    },
  },
})
